import importlib
import sqlite3
from pathlib import Path

from fastapi.testclient import TestClient


def _create_phase1_dbs(tmp_path: Path) -> tuple[Path, Path]:
    trading_db = tmp_path / "trading.db"
    signals_db = tmp_path / "signals.db"

    conn = sqlite3.connect(trading_db)
    conn.execute(
        """
        CREATE TABLE watchlist (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            pair TEXT NOT NULL,
            added_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            is_active INTEGER DEFAULT 1
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE price_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            pair TEXT NOT NULL,
            timestamp TIMESTAMP NOT NULL,
            open REAL,
            high REAL,
            low REAL,
            close REAL,
            volume REAL
        )
        """
    )
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
    conn.executemany(
        "INSERT INTO watchlist (user_id, pair, is_active, added_at) VALUES (?, ?, ?, ?)",
        [
            (1, "btcidr", 1, "2026-05-21 09:00:00"),
            (1, "ethidr", 0, "2026-05-21 09:01:00"),
            (1, "xrp/idr", 1, "2026-05-21 09:02:00"),
        ],
    )
    conn.executemany(
        """
        INSERT INTO price_history (pair, timestamp, open, high, low, close, volume)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        [
            ("btcidr", "2026-05-21 10:00:00", 100, 110, 95, 105, 10),
            ("btcidr", "2026-05-21 10:01:00", 105, 112, 101, 109, 11),
            ("xrp/idr", "2026-05-21 10:00:00", 5000, 5100, 4950, 5060, 99),
        ],
    )
    conn.executemany(
        """
        INSERT INTO trades (user_id, pair, type, price, amount, total, status, opened_at, closed_at, profit_loss)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        [
            (1, "btcidr", "BUY", 1000000000, 0.001, 1000000, "OPEN", "2026-05-21 10:00:00", None, None),
            (1, "ethidr", "SELL", 50000000, 0.02, 1000000, "CLOSED", "2026-05-20 10:00:00", "2026-05-20 12:00:00", 50000),
        ],
    )
    conn.commit()
    conn.close()

    conn = sqlite3.connect(signals_db)
    conn.execute(
        """
        CREATE TABLE signals (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            symbol TEXT NOT NULL,
            price REAL NOT NULL,
            recommendation TEXT NOT NULL,
            rsi TEXT,
            macd TEXT,
            ma_trend TEXT,
            bollinger TEXT,
            volume TEXT,
            ml_confidence REAL,
            combined_strength REAL,
            analysis TEXT,
            signal_time TEXT,
            received_at TEXT NOT NULL,
            received_date TEXT NOT NULL,
            source TEXT DEFAULT 'telegram',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        """
    )
    conn.executemany(
        """
        INSERT INTO signals (symbol, price, recommendation, ml_confidence, combined_strength, analysis, signal_time, received_at, received_date, source)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        [
            ("BTCIDR", 1000000000, "BUY", 0.91, 0.7, "Bullish", "10:00:00", "2026-05-21 10:00:00", "2026-05-21", "telegram"),
            ("ETHIDR", 50000000, "HOLD", 0.55, 0.1, "Wait", "09:00:00", "2026-05-21 09:00:00", "2026-05-21", "telegram"),
        ],
    )
    conn.commit()
    conn.close()
    return trading_db, signals_db


def _create_client(monkeypatch, tmp_path):
    trading_db, signals_db = _create_phase1_dbs(tmp_path)
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


def test_system_data_sources_reports_read_only_sources(monkeypatch, tmp_path):
    client = _create_client(monkeypatch, tmp_path)

    response = client.get("/api/v1/system/data-sources")

    assert response.status_code == 200
    body = response.json()
    assert body["success"] is True
    assert body["data"]["trading_db"]["read_only"] is True
    assert body["data"]["trading_db"]["status"] == "online"
    assert body["data"]["signals_db"]["read_only"] is True
    assert body["data"]["signals_db"]["status"] == "online"
    assert body["data"]["redis"]["status"] in {"online", "offline", "unknown"}


def test_active_pairs_reads_only_active_watchlist_and_adds_tradingview_symbol(monkeypatch, tmp_path):
    client = _create_client(monkeypatch, tmp_path)

    response = client.get("/api/v1/pairs/active")

    assert response.status_code == 200
    body = response.json()
    pairs = body["data"]["pairs"]
    assert [p["pair"] for p in pairs] == ["btcidr", "xrpidr"]
    assert pairs[0]["tradingview_symbol"] == "INDODAX:BTCIDR"
    assert pairs[0]["is_active"] is True
    assert body["meta"]["source"] == "sqlite"


def test_top_volume_pairs_reads_indodax_public_summaries_without_33_pair_cap(monkeypatch, tmp_path):
    client = _create_client(monkeypatch, tmp_path)

    import dashboard_api.main as dashboard_main

    tickers = [
        {
            "pair": f"coin{i:02d}_idr",
            "last": 1000 + i,
            "high": 1100 + i,
            "low": 900 + i,
            "volume": 1_000_000_000 - i,
            "volume_coin": 100 + i,
            "bid": 990 + i,
            "ask": 1010 + i,
            "change_percent": i / 10,
        }
        for i in range(40)
    ]
    tickers.append({"pair": "usdt_usd", "last": 1, "volume": 999_999_999})
    monkeypatch.setattr(dashboard_main, "_fetch_indodax_tickers", lambda: list(reversed(tickers)))

    response = client.get("/api/v1/pairs/top-volume")

    assert response.status_code == 200
    body = response.json()
    pairs = body["data"]["pairs"]
    assert body["success"] is True
    assert body["data"]["count"] == 40
    assert len(pairs) == 40
    assert pairs[0]["pair"] == "coin00idr"
    assert pairs[0]["top_volume_rank"] == 1
    assert pairs[0]["volume_idr"] == 1_000_000_000
    assert pairs[-1]["pair"] == "coin39idr"
    assert pairs[-1]["top_volume_rank"] == 40
    assert all(pair["pair"].endswith("idr") for pair in pairs)
    assert all(pair["volume_idr"] > 500_000_000 for pair in pairs)
    assert body["data"]["limit"] is None
    assert body["data"]["min_volume_idr"] == 500_000_000
    assert body["meta"]["source"] == "indodax_public_summaries"


def test_top_volume_pairs_adds_read_only_wallet_readiness_markers(monkeypatch, tmp_path):
    client = _create_client(monkeypatch, tmp_path)

    import dashboard_api.main as dashboard_main

    tickers = [
        {"pair": "btc_idr", "last": 1_000_000_000, "volume": 900_000_000},
        {"pair": "eth_idr", "last": 50_000_000, "volume": 800_000_000},
    ]
    monkeypatch.setattr(dashboard_main, "_fetch_indodax_tickers", lambda: tickers)
    monkeypatch.setattr(
        dashboard_main,
        "_fetch_indodax_balance",
        lambda: {"funds": {"idr": "750000", "btc": "0.0015", "eth": "0"}},
    )

    response = client.get("/api/v1/pairs/top-volume")

    assert response.status_code == 200
    body = response.json()
    pairs = {pair["pair"]: pair for pair in body["data"]["pairs"]}
    assert body["data"]["wallet"]["available"] is True
    assert body["data"]["wallet"]["idr_balance"] == 750_000
    assert pairs["btcidr"]["wallet_status"] == {
        "asset": "btc",
        "asset_balance": 0.0015,
        "asset_value_idr": 1_500_000,
        "idr_balance": 750_000,
        "sell_ready": True,
        "buy_ready": True,
        "status": "sell_and_buy_ready",
        "label": "SIAP JUAL & BELI",
    }
    assert pairs["ethidr"]["wallet_status"]["sell_ready"] is False
    assert pairs["ethidr"]["wallet_status"]["buy_ready"] is True
    assert pairs["ethidr"]["wallet_status"]["label"] == "SIAP BELI"


def test_top_volume_pairs_understands_indodax_getinfo_balance_shape_for_trollsol(monkeypatch, tmp_path):
    client = _create_client(monkeypatch, tmp_path)

    import dashboard_api.main as dashboard_main

    monkeypatch.setattr(
        dashboard_main,
        "_fetch_indodax_tickers",
        lambda: [{"pair": "trollsol_idr", "last": 2_000, "volume": 900_000_000}],
    )
    monkeypatch.setattr(
        dashboard_main,
        "_fetch_indodax_balance",
        lambda: {"balance": {"idr": "0", "trollsol": "123.45"}, "balance_hold": {"trollsol": "0"}},
    )

    response = client.get("/api/v1/pairs/top-volume")

    assert response.status_code == 200
    pair = response.json()["data"]["pairs"][0]
    assert pair["pair"] == "trollsolidr"
    assert pair["wallet_status"]["asset"] == "trollsol"
    assert pair["wallet_status"]["asset_balance"] == 123.45
    assert pair["wallet_status"]["sell_ready"] is True
    assert pair["wallet_status"]["buy_ready"] is False
    assert pair["wallet_status"]["label"] == "SIAP JUAL"


def test_top_volume_pairs_only_returns_markets_above_500m_idr_volume(monkeypatch, tmp_path):
    client = _create_client(monkeypatch, tmp_path)

    import dashboard_api.main as dashboard_main

    tickers = [
        {"pair": "btc_idr", "last": 1_000_000_000, "volume": 900_000_000},
        {"pair": "eth_idr", "last": 50_000_000, "volume": 500_000_001},
        {"pair": "xrp_idr", "last": 5_000, "volume": 500_000_000},
        {"pair": "doge_idr", "last": 2_000, "volume": 499_999_999},
        {"pair": "usdt_usd", "last": 1, "volume": 9_000_000_000},
    ]
    monkeypatch.setattr(dashboard_main, "_fetch_indodax_tickers", lambda: tickers)

    response = client.get("/api/v1/pairs/top-volume")

    assert response.status_code == 200
    body = response.json()
    pairs = body["data"]["pairs"]
    assert [pair["pair"] for pair in pairs] == ["btcidr", "ethidr"]
    assert all(pair["volume_idr"] > 500_000_000 for pair in pairs)
    assert body["data"]["min_volume_idr"] == 500_000_000
    assert body["data"]["count"] == 2


def test_latest_signals_reads_signal_db_without_mutation(monkeypatch, tmp_path):
    client = _create_client(monkeypatch, tmp_path)

    response = client.get("/api/v1/signals/latest?limit=1")

    assert response.status_code == 200
    body = response.json()
    signals = body["data"]["signals"]
    assert len(signals) == 1
    assert signals[0]["pair"] == "btcidr"
    assert signals[0]["recommendation"] == "BUY"
    assert signals[0]["tradingview_symbol"] == "INDODAX:BTCIDR"

    db_path = Path(body["meta"]["source_path"])
    conn = sqlite3.connect(db_path)
    count = conn.execute("SELECT COUNT(*) FROM signals").fetchone()[0]
    conn.close()
    assert count == 2


def test_trade_history_can_filter_closed_status(monkeypatch, tmp_path):
    client = _create_client(monkeypatch, tmp_path)

    response = client.get("/api/v1/trades/history?status=closed")

    assert response.status_code == 200
    body = response.json()
    trades = body["data"]["trades"]
    assert len(trades) == 1
    assert trades[0]["pair"] == "ethidr"
    assert trades[0]["status"] == "CLOSED"
    assert trades[0]["tradingview_symbol"] == "INDODAX:ETHIDR"


def test_pair_chart_returns_ohlcv_points(monkeypatch, tmp_path):
    client = _create_client(monkeypatch, tmp_path)

    response = client.get("/api/v1/pairs/btcidr/chart?limit=2")

    assert response.status_code == 200
    body = response.json()
    candles = body["data"]["candles"]
    assert len(candles) == 2
    assert candles[0]["open"] == 100
    assert candles[1]["close"] == 109
    assert body["data"]["tradingview_symbol"] == "INDODAX:BTCIDR"


def test_pair_chart_uses_bot_chart_history_rules_and_rejects_inactive_pairs(monkeypatch, tmp_path):
    client = _create_client(monkeypatch, tmp_path)

    import dashboard_api.main as dashboard_main

    monkeypatch.setattr(dashboard_main, "_fetch_indodax_tickers", lambda: [])

    active_response = client.get("/api/v1/pairs/xrpidr/chart?limit=10")
    inactive_response = client.get("/api/v1/pairs/ethidr/chart?limit=10")

    assert active_response.status_code == 200
    active_body = active_response.json()
    assert active_body["data"]["pair"] == "xrpidr"
    assert active_body["data"]["selected_from_active_pairs"] is True
    assert active_body["data"]["chart_renderer"] == "lightweight-charts"
    assert active_body["data"]["chart_method"] == "bot._get_chart_history_for_pair/db.get_price_history"
    assert active_body["data"]["candles"][0]["time"] == "2026-05-21 10:00:00"
    assert active_body["data"]["candles"][0]["value"] == 5060

    assert inactive_response.status_code == 404
    inactive_body = inactive_response.json()
    assert inactive_body["detail"]["code"] == "pair_not_active"
    assert inactive_body["detail"]["pair"] == "ethidr"


def test_pair_chart_allows_indodax_top_volume_pair_even_when_not_watchlist_active(monkeypatch, tmp_path):
    client = _create_client(monkeypatch, tmp_path)

    import dashboard_api.main as dashboard_main

    monkeypatch.setattr(
        dashboard_main,
        "_fetch_indodax_tickers",
        lambda: [
            {"pair": "eth_idr", "last": 50_000_000, "volume": 9_000_000_000},
            {"pair": "btc_idr", "last": 1_000_000_000, "volume": 8_000_000_000},
        ],
    )

    top_volume_response = client.get("/api/v1/pairs/top-volume?limit=33")
    assert top_volume_response.status_code == 200

    response = client.get("/api/v1/pairs/ethidr/chart?limit=10")

    assert response.status_code == 200
    body = response.json()
    assert body["data"]["pair"] == "ethidr"
    assert body["data"]["selected_from_active_pairs"] is False
    assert body["data"]["selected_from_top_volume"] is True


def test_sse_stream_emits_read_only_heartbeat(monkeypatch, tmp_path):
    client = _create_client(monkeypatch, tmp_path)

    with client.stream("GET", "/api/v1/events/stream?once=true") as response:
        body = response.read().decode("utf-8")

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/event-stream")
    assert "event: heartbeat" in body
    assert '"read_only": true' in body


def test_phase1_openapi_exposes_only_get_api_routes(monkeypatch, tmp_path):
    client = _create_client(monkeypatch, tmp_path)

    paths = client.get("/openapi.json").json()["paths"]
    api_paths = {path: methods for path, methods in paths.items() if path.startswith("/api/v1/")}

    assert set(api_paths) >= {
        "/api/v1/health",
        "/api/v1/system/data-sources",
        "/api/v1/pairs/active",
        "/api/v1/pairs/{pair}/chart",
        "/api/v1/signals/latest",
        "/api/v1/trades/history",
        "/api/v1/positions/open",
        "/api/v1/events/stream",
        "/api/v1/safety/status",
    }
    for path, methods in api_paths.items():
        assert set(methods) == {"get"}, f"Phase 1 API route must be GET-only: {path}"
