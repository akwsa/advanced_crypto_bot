"""Tests for Bug HIGH/MEDIUM #5, #6, #8, #10 fixes (audit 2026-06-07).

#5: Trade review idempotency guard.
#6: WAL checkpoint API on both DB classes.
#8: ADMIN_IDS test user filter + is_production_user_id.
#10: _quant_cache LRU cap + helper API.
"""
import os
import sqlite3
import tempfile

import pytest


# ============================================================================
# Bug #8 — ADMIN_IDS guard
# ============================================================================
class TestAdminIdsGuard:
    def test_known_test_ids_blocked(self):
        from core.config import is_production_user_id, KNOWN_TEST_USER_IDS
        for tid in KNOWN_TEST_USER_IDS:
            assert is_production_user_id(tid) is False, f"{tid} should be blocked"

    def test_real_admin_id_allowed(self):
        from core.config import is_production_user_id
        # Real Telegram user IDs are 9+ digits
        assert is_production_user_id(256024600) is True
        assert is_production_user_id(987654321) is True

    def test_handles_invalid_input(self):
        from core.config import is_production_user_id
        assert is_production_user_id(None) is False
        assert is_production_user_id("abc") is False
        assert is_production_user_id("") is False

    def test_filter_admin_ids_strips_test_users(self):
        from core.config import _filter_admin_ids
        result = _filter_admin_ids([42, 256024600, 123, 987654321])
        assert 42 not in result
        assert 123 not in result
        assert 256024600 in result
        assert 987654321 in result

    def test_filter_empty_list(self):
        from core.config import _filter_admin_ids
        assert _filter_admin_ids([]) == []
        assert _filter_admin_ids(None) is None


# ============================================================================
# Bug #10 — _quant_cache LRU
# ============================================================================
class TestQuantCacheLRU:
    def setup_method(self):
        from signals.signal_pipeline import _quant_cache_clear
        _quant_cache_clear()

    def test_basic_set_and_get(self):
        from signals.signal_pipeline import _quant_cache_get, _quant_cache_set
        _quant_cache_set("btcidr", {"ts": 1, "vol": 0.5})
        entry = _quant_cache_get("btcidr")
        assert entry == {"ts": 1, "vol": 0.5}

    def test_get_missing_returns_none(self):
        from signals.signal_pipeline import _quant_cache_get
        assert _quant_cache_get("nonexistent") is None

    def test_lru_eviction_when_cap_exceeded(self, monkeypatch):
        from signals.signal_pipeline import (
            _quant_cache_set,
            _quant_cache_get,
            _quant_cache,
        )
        # Force small cap for this test
        monkeypatch.setattr("signals.signal_pipeline.QUANT_CACHE_MAX_PAIRS", 3)
        _quant_cache_set("a", {"v": 1})
        _quant_cache_set("b", {"v": 2})
        _quant_cache_set("c", {"v": 3})
        _quant_cache_set("d", {"v": 4})  # should evict 'a'
        assert _quant_cache_get("a") is None
        assert _quant_cache_get("b") is not None
        assert _quant_cache_get("d") is not None

    def test_lru_get_promotes_to_mru(self, monkeypatch):
        from signals.signal_pipeline import _quant_cache_set, _quant_cache_get
        monkeypatch.setattr("signals.signal_pipeline.QUANT_CACHE_MAX_PAIRS", 3)
        _quant_cache_set("a", {"v": 1})
        _quant_cache_set("b", {"v": 2})
        _quant_cache_set("c", {"v": 3})
        # Access 'a' → moves it to MRU, so 'b' is now LRU
        _quant_cache_get("a")
        _quant_cache_set("d", {"v": 4})  # evicts 'b' (LRU), not 'a'
        assert _quant_cache_get("a") is not None
        assert _quant_cache_get("b") is None

    def test_clear_returns_count(self):
        from signals.signal_pipeline import _quant_cache_set, _quant_cache_clear
        _quant_cache_set("a", {})
        _quant_cache_set("b", {})
        n = _quant_cache_clear()
        assert n == 2


# ============================================================================
# Bug #6 — WAL checkpoint API
# ============================================================================
class TestWalCheckpoint:
    def test_database_has_checkpoint_wal_method(self):
        from core.database import Database
        assert hasattr(Database, "checkpoint_wal")
        assert callable(Database.checkpoint_wal)

    def test_signal_database_has_checkpoint_wal_method(self):
        from signals.signal_db import SignalDatabase
        assert hasattr(SignalDatabase, "checkpoint_wal")
        assert callable(SignalDatabase.checkpoint_wal)

    def test_checkpoint_works_on_real_sqlite(self):
        """End-to-end: real sqlite WAL DB, checkpoint succeeds."""
        from core.database import Database
        with tempfile.TemporaryDirectory() as tmp:
            db_path = os.path.join(tmp, "test.db")
            # Bootstrap a tiny WAL-mode DB
            conn = sqlite3.connect(db_path)
            conn.execute("PRAGMA journal_mode=WAL")
            conn.execute("CREATE TABLE x (id INTEGER)")
            conn.execute("INSERT INTO x VALUES (1)")
            conn.commit()
            conn.close()

            db = Database.__new__(Database)
            db.db_path = db_path
            assert db.checkpoint_wal(mode="PASSIVE") is True
            assert db.checkpoint_wal(mode="TRUNCATE") is True

    def test_checkpoint_handles_missing_db_gracefully(self):
        """checkpoint_wal must not raise even if DB is unreachable."""
        from core.database import Database
        db = Database.__new__(Database)
        db.db_path = "/nonexistent/path/to/db.sqlite"
        # Should NOT raise; returns True/False
        result = db.checkpoint_wal()
        assert isinstance(result, bool)


# ============================================================================
# Bug #5 — Trade review idempotency
# ============================================================================
class TestTradeReviewIdempotency:
    def _make_db(self, tmp_path):
        """Create a Database with full schema for trade_reviews testing."""
        from core.database import Database
        db_path = str(tmp_path / "test_trading.db")
        # Use real Database init — it creates all tables.
        db = Database(db_path)
        return db

    def test_create_trade_review_skips_when_exists(self, tmp_path):
        db = self._make_db(tmp_path)
        with db.get_connection() as conn:
            cursor = conn.cursor()
            # Insert a fake trade row
            cursor.execute(
                """INSERT INTO trades (id, user_id, pair, type, price, amount, total,
                   status, opened_at, ml_confidence)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, datetime('now'), ?)""",
                (9999, 256024600, "btcidr", "BUY", 1000000, 0.001, 1000, "closed", 0.75)
            )
            conn.commit()

            trade = dict(cursor.execute("SELECT * FROM trades WHERE id=9999").fetchone())

            # First call: creates review
            db.create_trade_review(conn, trade, exit_price=1010000, pnl_pct=1.0, exit_reason="TP1")
            count1 = cursor.execute(
                "SELECT COUNT(*) FROM trade_reviews WHERE trade_id=9999"
            ).fetchone()[0]
            assert count1 == 1

            # Second call: should be skipped (idempotent)
            db.create_trade_review(conn, trade, exit_price=1020000, pnl_pct=2.0, exit_reason="TP2")
            count2 = cursor.execute(
                "SELECT COUNT(*) FROM trade_reviews WHERE trade_id=9999"
            ).fetchone()[0]
            assert count2 == 1

            # Verify the review still has the FIRST exit_price (skip didn't overwrite).
            row = cursor.execute(
                "SELECT exit_price FROM trade_reviews WHERE trade_id=9999"
            ).fetchone()
            assert row[0] == 1010000  # first call's exit price preserved
