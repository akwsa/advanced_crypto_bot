import os
import sqlite3
import subprocess
import sys
import tempfile
from types import SimpleNamespace

from autotrade.contracts import TradeIntent
from autotrade.strategy2.repository import Strategy2Repository
from autotrade.strategy2.shadow_runtime import observe_intent_safely
from autotrade.strategy2.taxonomy import PositionState, ReasonCode
from core.database import Database


def _load_config(env):
    code = (
        "from core.config import Config; "
        "print(Config.AUTOTRADE_STRATEGY2_ENABLED, Config.AUTOTRADE_STRATEGY2_MODE)"
    )
    result = subprocess.run(
        [sys.executable, "-c", code], cwd=os.path.dirname(os.path.dirname(__file__)),
        env={**os.environ, **env}, check=True, capture_output=True, text=True,
    )
    return result.stdout.strip()


def test_config_defaults_off_and_invalid_mode_fails_closed():
    env = {"AUTOTRADE_STRATEGY2_ENABLED": "", "AUTOTRADE_STRATEGY2_MODE": ""}
    assert _load_config(env) == "False off"
    assert _load_config({"AUTOTRADE_STRATEGY2_ENABLED": "true", "AUTOTRADE_STRATEGY2_MODE": "live"}) == "False off"
    assert _load_config({"AUTOTRADE_STRATEGY2_ENABLED": "true", "AUTOTRADE_STRATEGY2_MODE": "shadow"}) == "True shadow"
    assert _load_config({
        "AUTOTRADE_STRATEGY2_ENABLED": "true",
        "AUTOTRADE_STRATEGY2_MODE": "shadow",
        "AUTOTRADE_STRATEGY2_INITIAL_CASH_IDR": "NaN",
    }) == "False shadow"


def test_strategy2_never_mutates_strategy1_tables():
    with tempfile.NamedTemporaryFile(suffix=".db") as tmp:
        db = Database(tmp.name)
        db.add_user(1, "baseline", "Baseline")
        initial_balance = db.get_balance(1)
        with db.get_connection() as conn:
            before = {
                table: conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
                for table in ("trades", "autotrade_intents", "autotrade_orders", "autotrade_fills")
            }
        repo = Strategy2Repository(
            db, strategy_version="patient-swing-v1", experiment_id="shadow-a", initial_cash=1_000
        )
        repo.transition(
            user_id=1, pair="btcidr", event_key="candidate", correlation_id="corr",
            snapshot_id="snap", to_state=PositionState.CANDIDATE,
            reason_code=ReasonCode.PULLBACK_NOT_ARMED,
        )
        with db.get_connection() as conn:
            after = {
                table: conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
                for table in before
            }
        assert after == before
        assert db.get_balance(1) == initial_balance
        db.close()


def test_versions_and_experiments_have_separate_cash_and_positions():
    with tempfile.NamedTemporaryFile(suffix=".db") as tmp:
        db = Database(tmp.name)
        first = Strategy2Repository(db, strategy_version="v1", experiment_id="a", initial_cash=100)
        second = Strategy2Repository(db, strategy_version="v1", experiment_id="b", initial_cash=200)
        assert first.get_portfolio(1)["cash"] == 100
        assert second.get_portfolio(1)["cash"] == 200
        assert first.get_position(1, "btcidr") is None
        assert second.get_position(1, "btcidr") is None
        db.close()


def test_strategy2_schema_repairs_missing_columns_on_rerun():
    with tempfile.NamedTemporaryFile(suffix=".db") as tmp:
        conn = sqlite3.connect(tmp.name)
        conn.execute("CREATE TABLE strategy2_decisions (id INTEGER PRIMARY KEY AUTOINCREMENT)")
        conn.execute("CREATE TABLE strategy2_state_events (id INTEGER PRIMARY KEY AUTOINCREMENT)")
        conn.execute(
            "CREATE TABLE strategy2_portfolios (strategy_version TEXT, experiment_id TEXT, user_id INTEGER)"
        )
        conn.execute("CREATE TABLE strategy2_positions (id INTEGER PRIMARY KEY AUTOINCREMENT)")
        conn.commit()
        conn.close()

        db = Database(tmp.name)
        with db.get_connection() as conn2:
            decision_cols = {
                row[1] for row in conn2.execute("PRAGMA table_info(strategy2_decisions)")
            }
            event_cols = {
                row[1] for row in conn2.execute("PRAGMA table_info(strategy2_state_events)")
            }
            portfolio_cols = {
                row[1] for row in conn2.execute("PRAGMA table_info(strategy2_portfolios)")
            }
            position_cols = {
                row[1] for row in conn2.execute("PRAGMA table_info(strategy2_positions)")
            }
        assert {"strategy_version", "experiment_id", "idempotency_key", "evidence_json"} <= decision_cols
        assert {"event_key", "to_state", "event_json"} <= event_cols
        assert {"cash", "initial_cash", "updated_at"} <= portfolio_cols
        assert {"pair", "state", "quantity", "cost_basis", "fees"} <= position_cols
        db.close()


def test_shadow_hook_off_mode_is_noop_and_writes_nothing():
    with tempfile.NamedTemporaryFile(suffix=".db") as tmp:
        db = Database(tmp.name)
        intent = TradeIntent.from_signal({
            "pair": "btcidr",
            "signal_type": "BUY",
            "price": 100.0,
            "confidence": 0.9,
            "created_at": 1_000.0,
            "user_id": 1,
            "data": {"signal": {"pair": "btcidr", "recommendation": "BUY", "price": 100.0, "ml_confidence": 0.9}},
        })
        runtime_signal = dict(intent.signal)
        runtime_signal["_intent"] = intent.to_dict()
        config = SimpleNamespace(
            AUTOTRADE_STRATEGY2_ENABLED=False,
            AUTOTRADE_STRATEGY2_MODE="off",
            AUTOTRADE_STRATEGY2_VERSION="patient-swing-v1",
            AUTOTRADE_STRATEGY2_INITIAL_CASH_IDR=1_000.0,
        )
        assert observe_intent_safely(
            database=db, intent=intent, signal=runtime_signal, config=config
        ) is None
        with db.get_connection() as conn:
            assert conn.execute("SELECT COUNT(*) FROM strategy2_decisions").fetchone()[0] == 0
            assert conn.execute("SELECT COUNT(*) FROM strategy2_state_events").fetchone()[0] == 0
        db.close()


def test_shadow_hook_failure_is_fail_closed_for_strategy1():
    intent = TradeIntent.from_signal({
        "pair": "btcidr",
        "signal_type": "BUY",
        "price": 100.0,
        "confidence": 0.9,
        "created_at": 1_000.0,
        "data": {"signal": {"pair": "btcidr", "recommendation": "BUY", "price": 100.0, "ml_confidence": 0.9}},
    })
    runtime_signal = dict(intent.signal)
    runtime_signal["_intent"] = intent.to_dict()
    class _BoomLogger:
        def __init__(self):
            self.messages = []

        def warning(self, message, *args):
            self.messages.append(message % args if args else message)

    class _BrokenDatabase:
        def get_connection(self):
            raise RuntimeError("boom")

    logger = _BoomLogger()
    config = SimpleNamespace(
        AUTOTRADE_STRATEGY2_ENABLED=True,
        AUTOTRADE_STRATEGY2_MODE="shadow",
        AUTOTRADE_STRATEGY2_VERSION="patient-swing-v1",
        AUTOTRADE_STRATEGY2_INITIAL_CASH_IDR=1_000.0,
    )
    assert observe_intent_safely(
        database=_BrokenDatabase(), intent=intent, signal=runtime_signal, config=config, logger=logger
    ) is None
    assert logger.messages
