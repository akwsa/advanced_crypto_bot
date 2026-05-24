import importlib
import sqlite3
from pathlib import Path

from fastapi.testclient import TestClient


def _create_trading_db(path: Path):
    conn = sqlite3.connect(path)
    conn.execute(
        """
        CREATE TABLE trades (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            pair TEXT,
            type TEXT,
            price REAL,
            amount REAL,
            total REAL,
            fee REAL,
            signal_source TEXT,
            ml_confidence REAL,
            status TEXT DEFAULT 'OPEN',
            opened_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            closed_at TIMESTAMP,
            profit_loss REAL,
            profit_loss_pct REAL
        )
        """
    )
    conn.execute(
        """
        INSERT INTO trades (user_id, pair, type, price, amount, total, status, opened_at)
        VALUES (1, 'btcidr', 'BUY', 1000000000, 0.001, 1000000, 'OPEN', '2026-05-21 10:00:00')
        """
    )
    conn.execute(
        """
        INSERT INTO trades (user_id, pair, type, price, amount, total, status, opened_at, closed_at, profit_loss)
        VALUES (1, 'ethidr', 'BUY', 50000000, 0.02, 1000000, 'CLOSED', '2026-05-20 10:00:00', '2026-05-20 12:00:00', 50000)
        """
    )
    conn.commit()
    conn.close()


def _create_client(monkeypatch, tmp_path):
    trading_db = tmp_path / "trading.db"
    signals_db = tmp_path / "signals.db"
    _create_trading_db(trading_db)
    signals_db.touch()

    monkeypatch.setenv("DATABASE_PATH", str(trading_db))
    monkeypatch.setenv("SIGNALS_DATABASE_PATH", str(signals_db))
    monkeypatch.setenv("AUTO_TRADING_ENABLED", "true")
    monkeypatch.setenv("AUTO_TRADE_DRY_RUN", "true")
    monkeypatch.setenv("MANUAL_TRADING_ENABLED", "false")
    monkeypatch.setenv("CANCEL_TRADE_ENABLED", "false")

    import core.config as config
    import dashboard_api.config as dashboard_config
    import dashboard_api.main as dashboard_main

    importlib.reload(config)
    importlib.reload(dashboard_config)
    importlib.reload(dashboard_main)
    return TestClient(dashboard_main.app)


def test_safety_status_reports_dry_run_locked(monkeypatch, tmp_path):
    client = _create_client(monkeypatch, tmp_path)

    response = client.get("/api/v1/safety/status")

    assert response.status_code == 200
    body = response.json()
    assert body["success"] is True
    assert body["data"]["auto_trading_enabled"] is True
    assert body["data"]["auto_trade_dry_run"] is True
    assert body["data"]["manual_trading_enabled"] is False
    assert body["data"]["cancel_trade_enabled"] is False
    assert body["data"]["real_trading_locked"] is True
    assert body["data"]["dashboard_write_enabled"] is False
    assert body["data"]["smart_hunter"]["mode"] == "DRY_RUN"
    assert body["data"]["auto_hunter"]["mode"] == "DRY_RUN"


def test_open_positions_read_only_response_includes_tradingview_symbol(monkeypatch, tmp_path):
    client = _create_client(monkeypatch, tmp_path)

    response = client.get("/api/v1/positions/open")

    assert response.status_code == 200
    body = response.json()
    assert body["success"] is True
    positions = body["data"]["positions"]
    assert len(positions) == 1
    position = positions[0]
    assert position["pair"] == "btcidr"
    assert position["status"] == "OPEN"
    assert position["mode"] == "DRY_RUN"
    assert position["tradingview_symbol"] == "INDODAX:BTCIDR"
    assert position["entry_price"] == 1000000000
    assert position["total"] == 1000000

    # Endpoint must not mutate source table.
    db_path = Path(body["meta"]["source_path"])
    conn = sqlite3.connect(db_path)
    count = conn.execute("SELECT COUNT(*) FROM trades").fetchone()[0]
    conn.close()
    assert count == 2


def test_app_has_no_post_routes_for_phase1(monkeypatch, tmp_path):
    client = _create_client(monkeypatch, tmp_path)

    routes = client.get("/openapi.json").json()["paths"]

    for path, methods in routes.items():
        assert "post" not in methods, f"Phase 1 dashboard must stay read-only: {path} has POST"
