import math
import tempfile
import threading

import pytest

from autotrade.strategy2.repository import Strategy2Repository
from autotrade.strategy2.contracts import stable_idempotency_key
from autotrade.strategy2.state_machine import InvalidTransitionError
from autotrade.strategy2.taxonomy import DecisionStatus, PositionState, ReasonCode
from core.database import Database


@pytest.fixture
def ledger():
    tmp = tempfile.NamedTemporaryFile(suffix=".db")
    db = Database(tmp.name)
    repo = Strategy2Repository(
        db, strategy_version="patient-swing-v1", experiment_id="shadow-a", initial_cash=1_000
    )
    yield db, repo
    db.close()
    tmp.close()


def _transition(repo, key, state):
    return repo.transition(
        user_id=1, pair="btcidr", event_key=key, correlation_id="corr",
        snapshot_id=f"snap-{key}", to_state=state, reason_code=ReasonCode.ENTRY_APPROVED,
    )


def _pending(repo):
    _transition(repo, "candidate", PositionState.CANDIDATE)
    _transition(repo, "armed", PositionState.ARMED)
    _transition(repo, "pending", PositionState.PENDING)


def test_schema_creation_is_rerunnable_and_additive(ledger):
    db, _ = ledger
    db._create_tables()
    db._create_tables()
    with db.get_connection() as conn:
        tables = {row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    assert {"strategy2_decisions", "strategy2_state_events", "strategy2_portfolios", "strategy2_positions"} <= tables
    assert {"trades", "autotrade_intents", "users"} <= tables


def test_decision_and_transition_replay_are_idempotent(ledger):
    _, repo = ledger
    first = repo.record_decision(
        operation_identity="decision-1",
        idempotency_key=stable_idempotency_key("patient-swing-v1", "shadow-a", "decision-1"),
        correlation_id="corr", snapshot_id="snap",
        pair="btcidr", status=DecisionStatus.NO_ENTRY,
        reason_code=ReasonCode.TREND_NOT_HEALTHY,
    )
    replay = repo.record_decision(
        operation_identity="decision-1",
        idempotency_key=stable_idempotency_key("patient-swing-v1", "shadow-a", "decision-1"),
        correlation_id="corr", snapshot_id="snap",
        pair="btcidr", status=DecisionStatus.NO_ENTRY,
        reason_code=ReasonCode.TREND_NOT_HEALTHY,
    )
    assert first["id"] == replay["id"]
    assert _transition(repo, "candidate", PositionState.CANDIDATE)["id"] == _transition(
        repo, "candidate", PositionState.CANDIDATE
    )["id"]


def test_conflicting_replay_and_non_namespaced_identity_fail_closed(ledger):
    _, repo = ledger
    key = stable_idempotency_key("patient-swing-v1", "shadow-a", "decision")
    repo.record_decision(
        operation_identity="decision", idempotency_key=key, correlation_id="corr",
        snapshot_id="snap", pair="btc/idr", status=DecisionStatus.NO_ENTRY,
        reason_code=ReasonCode.TREND_NOT_HEALTHY,
    )
    with pytest.raises(ValueError, match="idempotency conflict"):
        repo.record_decision(
            operation_identity="decision", idempotency_key=key, correlation_id="other",
            snapshot_id="snap", pair="BTCIDR", status=DecisionStatus.NO_ENTRY,
            reason_code=ReasonCode.TREND_NOT_HEALTHY,
        )
    with pytest.raises(ValueError, match="namespace"):
        repo.record_decision(
            operation_identity="decision", idempotency_key="arbitrary", correlation_id="corr",
            snapshot_id="snap", pair="btcidr", status=DecisionStatus.NO_ENTRY,
            reason_code=ReasonCode.TREND_NOT_HEALTHY,
        )

    _transition(repo, "candidate", PositionState.CANDIDATE)
    with pytest.raises(ValueError, match="idempotency conflict"):
        repo.transition(
            user_id=2, pair="ethidr", event_key="candidate", correlation_id="corr",
            snapshot_id="snap-candidate", to_state=PositionState.CANDIDATE,
            reason_code=ReasonCode.ENTRY_APPROVED,
        )


def test_pair_aliases_share_one_projection_and_initial_cash_drift_is_rejected(ledger):
    db, repo = ledger
    repo.transition(
        user_id=1, pair="btc/idr", event_key="alias", correlation_id="corr",
        snapshot_id="snap", to_state=PositionState.CANDIDATE,
        reason_code=ReasonCode.PULLBACK_NOT_ARMED,
    )
    assert repo.get_position(1, "BTC_IDR")["pair"] == "BTCIDR"
    assert repo.get_portfolio(1)["initial_cash"] == 1_000
    drifted = Strategy2Repository(
        db, strategy_version="patient-swing-v1", experiment_id="shadow-a", initial_cash=2_000
    )
    with pytest.raises(ValueError, match="initial_cash"):
        drifted.get_portfolio(1)


def test_generic_terminal_transition_cannot_strand_quantity(ledger):
    _, repo = ledger
    _pending(repo)
    repo.open_position(
        user_id=1, pair="btcidr", event_key="buy", correlation_id="corr",
        snapshot_id="snap", price=100, quantity=1, fee=0,
        reason_code=ReasonCode.ENTRY_APPROVED,
    )
    with pytest.raises(ValueError, match="settlement"):
        repo.transition(
            user_id=1, pair="btcidr", event_key="invalidated", correlation_id="corr",
            snapshot_id="snap-2", to_state=PositionState.INVALIDATED,
            reason_code=ReasonCode.HARD_INVALIDATION,
        )
    assert repo.get_position(1, "btcidr")["state"] == PositionState.OPEN_RISK.value


def test_terminal_settlement_supports_invalidation_without_stranding_quantity(ledger):
    _, repo = ledger
    _pending(repo)
    repo.open_position(
        user_id=1, pair="btcidr", event_key="buy", correlation_id="corr",
        snapshot_id="snap", price=100, quantity=1, fee=0,
        reason_code=ReasonCode.ENTRY_APPROVED,
    )
    event = repo.settle_position(
        user_id=1, pair="btcidr", event_key="stop-out", correlation_id="corr",
        snapshot_id="snap-stop", price=95, quantity=1, fee=1,
        reason_code=ReasonCode.HARD_INVALIDATION, target_state=PositionState.INVALIDATED,
    )
    replay = repo.settle_position(
        user_id=1, pair="btcidr", event_key="stop-out", correlation_id="corr",
        snapshot_id="snap-stop", price=95, quantity=1, fee=1,
        reason_code=ReasonCode.HARD_INVALIDATION, target_state=PositionState.INVALIDATED,
    )
    assert event["id"] == replay["id"]
    assert repo.get_position(1, "btcidr")["state"] == PositionState.INVALIDATED.value
    assert repo.get_position(1, "btcidr")["quantity"] == 0
    assert repo.get_portfolio(1)["cash"] == 994


def test_virtual_entry_and_close_mutate_cash_once(ledger):
    _, repo = ledger
    _pending(repo)
    entry = dict(
        user_id=1, pair="btcidr", event_key="buy", correlation_id="corr",
        snapshot_id="buy-snap", price=100, quantity=2, fee=1,
        reason_code=ReasonCode.ENTRY_APPROVED,
    )
    assert repo.open_position(**entry)["event_key"] == "buy"
    repo.open_position(**entry)
    assert repo.get_portfolio(1)["cash"] == 799
    assert repo.get_position(1, "btcidr")["quantity"] == 2

    close = dict(
        user_id=1, pair="btcidr", event_key="sell", correlation_id="corr",
        snapshot_id="sell-snap", price=110, quantity=2, fee=1,
        reason_code=ReasonCode.NET_TARGET,
    )
    repo.close_position(**close)
    repo.close_position(**close)
    assert repo.get_portfolio(1)["cash"] == 1_018
    assert repo.get_position(1, "btcidr")["state"] == PositionState.CLOSED.value


@pytest.mark.parametrize(
    "field,value", [("price", 0), ("price", math.inf), ("quantity", math.nan), ("fee", -1)]
)
def test_invalid_entry_numeric_rolls_back(ledger, field, value):
    _, repo = ledger
    _pending(repo)
    values = dict(price=100, quantity=1, fee=0)
    values[field] = value
    with pytest.raises(ValueError):
        repo.open_position(
            user_id=1, pair="btcidr", event_key="bad", correlation_id="corr",
            snapshot_id="snap", reason_code=ReasonCode.ENTRY_APPROVED, **values,
        )
    assert repo.get_portfolio(1)["cash"] == 1_000
    assert repo.get_position(1, "btcidr")["quantity"] == 0


def test_illegal_transition_insufficient_cash_and_oversell_roll_back(ledger):
    _, repo = ledger
    _transition(repo, "candidate", PositionState.CANDIDATE)
    with pytest.raises(InvalidTransitionError):
        _transition(repo, "illegal", PositionState.OPEN_RISK)
    assert repo.get_position(1, "btcidr")["state"] == PositionState.CANDIDATE.value

    _transition(repo, "armed", PositionState.ARMED)
    _transition(repo, "pending", PositionState.PENDING)
    with pytest.raises(ValueError, match="insufficient"):
        repo.open_position(
            user_id=1, pair="btcidr", event_key="too-large", correlation_id="corr",
            snapshot_id="snap", price=1_000, quantity=2, fee=0,
            reason_code=ReasonCode.ENTRY_APPROVED,
        )
    assert repo.get_portfolio(1)["cash"] == 1_000
    assert repo.get_position(1, "btcidr")["quantity"] == 0

    repo.open_position(
        user_id=1, pair="btcidr", event_key="buy", correlation_id="corr",
        snapshot_id="buy-snap", price=100, quantity=2, fee=0,
        reason_code=ReasonCode.ENTRY_APPROVED,
    )
    cash_after_buy = repo.get_portfolio(1)["cash"]
    with pytest.raises(ValueError, match="exceeds"):
        repo.close_position(
            user_id=1, pair="btcidr", event_key="oversell", correlation_id="corr",
            snapshot_id="sell-snap", price=110, quantity=3, fee=0,
            reason_code=ReasonCode.NET_TARGET,
        )
    with pytest.raises(ValueError, match="fee cannot exceed"):
        repo.close_position(
            user_id=1, pair="btcidr", event_key="bad-fee", correlation_id="corr",
            snapshot_id="sell-snap", price=1, quantity=1, fee=2,
            reason_code=ReasonCode.NET_TARGET,
        )
    assert repo.get_portfolio(1)["cash"] == cash_after_buy
    assert repo.get_position(1, "btcidr")["quantity"] == 2


def test_same_state_transition_requires_replay_identity(ledger):
    _, repo = ledger
    _transition(repo, "candidate", PositionState.CANDIDATE)
    with pytest.raises(ValueError, match="same-state"):
        repo.transition(
            user_id=1, pair="btcidr", event_key="candidate-2", correlation_id="corr-2",
            snapshot_id="snap-2", to_state=PositionState.CANDIDATE,
            reason_code=ReasonCode.PULLBACK_NOT_ARMED,
        )


def test_partial_close_replay_succeeds_after_later_state_change(ledger):
    _, repo = ledger
    _pending(repo)
    repo.open_position(
        user_id=1, pair="btcidr", event_key="buy", correlation_id="corr",
        snapshot_id="buy-snap", price=100, quantity=2, fee=0,
        reason_code=ReasonCode.ENTRY_APPROVED,
    )
    first = repo.close_position(
        user_id=1, pair="btcidr", event_key="sell-1", correlation_id="corr",
        snapshot_id="sell-snap-1", price=110, quantity=1, fee=1,
        reason_code=ReasonCode.NET_TARGET,
    )
    repo.transition(
        user_id=1, pair="btcidr", event_key="protect", correlation_id="corr",
        snapshot_id="snap-protect", to_state=PositionState.BREAK_EVEN,
        reason_code=ReasonCode.BREAK_EVEN,
    )
    replay = repo.close_position(
        user_id=1, pair="btcidr", event_key="sell-1", correlation_id="corr",
        snapshot_id="sell-snap-1", price=110, quantity=1, fee=1,
        reason_code=ReasonCode.NET_TARGET,
    )
    assert replay["id"] == first["id"]


def test_close_replay_does_not_alias_entry_event(ledger):
    _, repo = ledger
    _pending(repo)
    repo.open_position(
        user_id=1, pair="btcidr", event_key="shared-key", correlation_id="corr",
        snapshot_id="buy-snap", price=100, quantity=1, fee=0,
        reason_code=ReasonCode.ENTRY_APPROVED,
    )
    with pytest.raises(ValueError, match="idempotency conflict"):
        repo.close_position(
            user_id=1, pair="btcidr", event_key="shared-key", correlation_id="corr",
            snapshot_id="buy-snap", price=110, quantity=1, fee=0,
            reason_code=ReasonCode.NET_TARGET,
        )


def test_underflow_notional_and_proceeds_fail_closed(ledger):
    _, repo = ledger
    _pending(repo)
    tiny = 1e-300
    with pytest.raises(ValueError, match="positive and finite"):
        repo.open_position(
            user_id=1, pair="btcidr", event_key="tiny-buy", correlation_id="corr",
            snapshot_id="snap", price=tiny, quantity=tiny, fee=0,
            reason_code=ReasonCode.ENTRY_APPROVED,
        )
    repo.open_position(
        user_id=1, pair="btcidr", event_key="buy", correlation_id="corr",
        snapshot_id="buy-snap", price=100, quantity=1, fee=0,
        reason_code=ReasonCode.ENTRY_APPROVED,
    )
    with pytest.raises(ValueError, match="finite proceeds"):
        repo.close_position(
            user_id=1, pair="btcidr", event_key="tiny-sell", correlation_id="corr",
            snapshot_id="sell-snap", price=tiny, quantity=tiny, fee=0,
            reason_code=ReasonCode.NET_TARGET,
        )


def test_terminal_epsilon_rounds_to_zero_quantity(ledger):
    _, repo = ledger
    _pending(repo)
    repo.open_position(
        user_id=1, pair="btcidr", event_key="buy", correlation_id="corr",
        snapshot_id="buy-snap", price=100, quantity=1, fee=0,
        reason_code=ReasonCode.ENTRY_APPROVED,
    )
    repo.close_position(
        user_id=1, pair="btcidr", event_key="sell-near-full", correlation_id="corr",
        snapshot_id="sell-snap", price=110, quantity=0.9999999999995, fee=0,
        reason_code=ReasonCode.NET_TARGET,
    )
    position = repo.get_position(1, "btcidr")
    assert position["state"] == PositionState.CLOSED.value
    assert position["quantity"] == 0


def test_portfolio_cash_must_remain_finite(ledger):
    _, repo = ledger
    _pending(repo)
    repo.open_position(
        user_id=1, pair="btcidr", event_key="buy", correlation_id="corr",
        snapshot_id="buy-snap", price=100, quantity=1, fee=0,
        reason_code=ReasonCode.ENTRY_APPROVED,
    )
    with repo.database.get_connection() as conn:
        conn.execute(
            "UPDATE strategy2_portfolios SET cash=? WHERE strategy_version=? AND experiment_id=? AND user_id=?",
            (1e308, "patient-swing-v1", "shadow-a", 1),
        )
    with pytest.raises(ValueError, match="remain finite"):
        repo.close_position(
            user_id=1, pair="btcidr", event_key="sell", correlation_id="corr",
            snapshot_id="sell-snap", price=1e308, quantity=1, fee=0,
            reason_code=ReasonCode.NET_TARGET,
        )


def test_concurrent_replay_debits_once(ledger):
    db, repo = ledger
    _pending(repo)
    barrier = threading.Barrier(2)
    errors = []

    def run():
        local = Database(db.db_path)
        worker = Strategy2Repository(
            local, strategy_version="patient-swing-v1", experiment_id="shadow-a", initial_cash=1_000
        )
        try:
            barrier.wait()
            worker.open_position(
                user_id=1, pair="btcidr", event_key="concurrent-buy", correlation_id="corr",
                snapshot_id="snap", price=100, quantity=1, fee=0,
                reason_code=ReasonCode.ENTRY_APPROVED,
            )
        except Exception as exc:  # pragma: no cover - asserted below
            errors.append(exc)
        finally:
            local.close()

    threads = [threading.Thread(target=run) for _ in range(2)]
    for thread in threads: thread.start()
    for thread in threads: thread.join()
    assert errors == []
    assert repo.get_portfolio(1)["cash"] == 900
