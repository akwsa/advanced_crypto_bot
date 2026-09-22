"""Tests untuk endpoint pair-scanner di dashboard_api/main.py:
- /api/v1/pairs/top-movers
- /api/v1/pairs/watchlist-recommendation

Pair scanner di-mock supaya test tidak butuh koneksi ke Indodax public API.
"""
from __future__ import annotations

import importlib
import sqlite3
from pathlib import Path

from fastapi.testclient import TestClient


def _create_client(monkeypatch, tmp_path):
    trading_db = tmp_path / "trading.db"
    signals_db = tmp_path / "signals.db"
    conn = sqlite3.connect(trading_db)
    conn.execute("CREATE TABLE trades (id INTEGER PRIMARY KEY, pair TEXT, status TEXT)")
    conn.execute("CREATE TABLE watchlist (id INTEGER PRIMARY KEY, pair TEXT, is_active INTEGER, added_at TIMESTAMP, user_id INTEGER)")
    conn.commit()
    conn.close()
    signals_db.touch()

    monkeypatch.setenv("DATABASE_PATH", str(trading_db))
    monkeypatch.setenv("SIGNALS_DATABASE_PATH", str(signals_db))
    monkeypatch.setenv("AUTO_TRADING_ENABLED", "true")
    monkeypatch.setenv("AUTO_TRADE_DRY_RUN", "true")

    import core.config as config
    import dashboard_api.config as dashboard_config
    import dashboard_api.main as dashboard_main

    importlib.reload(config)
    importlib.reload(dashboard_config)
    importlib.reload(dashboard_main)
    return TestClient(dashboard_main.app), dashboard_main


def _mock_snapshot(pair, last, change, volume, badges):
    """Build a minimal pair_scanner.PairSnapshot-like dict mimicking .to_dict()."""
    return {
        "pair": pair,
        "display_pair": pair.upper().replace("IDR", "/IDR"),
        "last": last,
        "high": last * 1.05,
        "low": last * 0.95,
        "bid": last * 0.999,
        "ask": last * 1.001,
        "volume_idr": volume,
        "change_percent": change,
        "spread_pct": 0.2,
        "distance_from_high_pct": 0.5,
        "distance_from_low_pct": 5.0,
        "score": change + 5.0,
        "rank": 1,
        "badges": badges,
    }


class _FakeSnapshot:
    """Minimal stand-in untuk PairSnapshot — cuma butuh `.to_dict()`."""

    def __init__(self, payload):
        self._payload = payload

    def to_dict(self):
        return dict(self._payload)


def test_top_movers_endpoint_returns_gainers_default(monkeypatch, tmp_path):
    client, dashboard_main = _create_client(monkeypatch, tmp_path)

    fake = [
        _FakeSnapshot(_mock_snapshot("dogeidr", 320, 14.3, 5e9, ["TOP_GAINER", "PUMPING"])),
        _FakeSnapshot(_mock_snapshot("solidr", 1e6, 8.0, 10e9, ["TOP_GAINER"])),
    ]

    def _mock_scan_top_movers(limit, min_volume_idr, direction):
        assert direction == "up"
        return fake

    import autohunter.pair_scanner as scanner
    monkeypatch.setattr(scanner, "scan_top_movers", _mock_scan_top_movers)

    response = client.get("/api/v1/pairs/top-movers?limit=2")
    assert response.status_code == 200
    body = response.json()
    assert body["success"] is True
    assert body["data"]["count"] == 2
    assert body["data"]["direction"] == "up"
    assert body["data"]["pairs"][0]["pair"] == "dogeidr"
    assert "PUMPING" in body["data"]["pairs"][0]["badges"]


def test_top_movers_endpoint_supports_direction_down(monkeypatch, tmp_path):
    client, dashboard_main = _create_client(monkeypatch, tmp_path)

    fake = [_FakeSnapshot(_mock_snapshot("xrpidr", 18000, -15.0, 8e9, ["TOP_LOSER"]))]

    def _mock_scan_top_movers(limit, min_volume_idr, direction):
        assert direction == "down"
        return fake

    import autohunter.pair_scanner as scanner
    monkeypatch.setattr(scanner, "scan_top_movers", _mock_scan_top_movers)

    response = client.get("/api/v1/pairs/top-movers?limit=5&direction=down")
    body = response.json()
    assert body["success"] is True
    assert body["data"]["direction"] == "down"
    assert body["data"]["pairs"][0]["pair"] == "xrpidr"
    assert "TOP_LOSER" in body["data"]["pairs"][0]["badges"]


def test_top_movers_endpoint_clamps_limit_to_50(monkeypatch, tmp_path):
    client, _ = _create_client(monkeypatch, tmp_path)

    captured = {}

    def _mock_scan_top_movers(limit, min_volume_idr, direction):
        captured["limit"] = limit
        return []

    import autohunter.pair_scanner as scanner
    monkeypatch.setattr(scanner, "scan_top_movers", _mock_scan_top_movers)

    client.get("/api/v1/pairs/top-movers?limit=999")
    assert captured["limit"] == 50

    client.get("/api/v1/pairs/top-movers?limit=0")
    assert captured["limit"] == 1


def test_top_movers_invalid_direction_falls_back_to_up(monkeypatch, tmp_path):
    client, _ = _create_client(monkeypatch, tmp_path)

    captured = {}

    def _mock_scan_top_movers(limit, min_volume_idr, direction):
        captured["direction"] = direction
        return []

    import autohunter.pair_scanner as scanner
    monkeypatch.setattr(scanner, "scan_top_movers", _mock_scan_top_movers)

    client.get("/api/v1/pairs/top-movers?direction=sideways")
    assert captured["direction"] == "up"


def test_watchlist_recommendation_endpoint_returns_merged_list(monkeypatch, tmp_path):
    client, _ = _create_client(monkeypatch, tmp_path)

    fake = [
        _FakeSnapshot(_mock_snapshot("btcidr", 1e9, 2.0, 100e9, ["TOP_VOLUME"])),
        _FakeSnapshot(_mock_snapshot("dogeidr", 320, 14.3, 5e9, ["TOP_GAINER", "PUMPING"])),
    ]

    def _mock_build(top_volume_limit, top_mover_limit):
        return fake

    import autohunter.pair_scanner as scanner
    monkeypatch.setattr(scanner, "build_watchlist_recommendation", _mock_build)

    response = client.get("/api/v1/pairs/watchlist-recommendation?top_volume=10&top_movers=5")
    body = response.json()
    assert body["success"] is True
    assert body["data"]["count"] == 2
    pairs = [p["pair"] for p in body["data"]["pairs"]]
    assert "btcidr" in pairs
    assert "dogeidr" in pairs
