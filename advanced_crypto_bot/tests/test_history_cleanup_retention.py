import os
import sqlite3
from datetime import datetime, timedelta

from core.database import Database
from signals.signal_db import SignalDatabase


def _count(db_path, table):
    with sqlite3.connect(db_path) as conn:
        return conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]


def test_runtime_history_cleanup_removes_old_closed_history_but_preserves_open_and_recent(tmp_path):
    db_path = tmp_path / "trading.db"
    db = Database(str(db_path))
    db.add_user(1, "tester", "Tester")

    old_closed = db.add_trade(1, "oldidr", "BUY", 100, 1, 100, 0, "auto", 0.8)
    recent_closed = db.add_trade(1, "recentidr", "BUY", 100, 1, 100, 0, "auto", 0.8)
    open_old = db.add_trade(1, "openidr", "BUY", 100, 1, 100, 0, "auto", 0.8)

    old_dt = (datetime.now() - timedelta(days=45)).strftime("%Y-%m-%d %H:%M:%S")
    recent_dt = (datetime.now() - timedelta(days=3)).strftime("%Y-%m-%d %H:%M:%S")
    with db.get_connection() as conn:
        conn.execute(
            "UPDATE trades SET status='CLOSED', closed_at=?, profit_loss=10, profit_loss_pct=1 WHERE id=?",
            (old_dt, old_closed),
        )
        conn.execute(
            "UPDATE trades SET status='CLOSED', closed_at=?, profit_loss=20, profit_loss_pct=2 WHERE id=?",
            (recent_dt, recent_closed),
        )
        conn.execute(
            "UPDATE trades SET opened_at=? WHERE id=?",
            (old_dt, open_old),
        )
        conn.execute(
            "INSERT INTO performance (user_id, date, total_trades, winning_trades, losing_trades, total_profit_loss, win_rate) VALUES (1, ?, 1, 1, 0, 10, 100)",
            ((datetime.now() - timedelta(days=45)).date().isoformat(),),
        )
        conn.execute(
            "INSERT INTO pair_performance (pair, total_trades, win_count, loss_count, avg_profit_pct, avg_loss_pct, total_profit_pct, total_loss_pct, profit_factor, last_trade_at) VALUES ('oldidr', 1, 1, 0, 1, 0, 1, 0, 999, ?)",
            (old_dt,),
        )
        conn.execute(
            "INSERT INTO trade_reviews (trade_id, pair, entry_price, exit_price, pnl_pct, hold_duration_minutes, max_profit_pct, max_loss_pct, ml_confidence, exit_reason, lesson, created_at) VALUES (?, 'oldidr', 100, 101, 1, 1, 1, 0, 0.8, 'exit', 'old', ?)",
            (old_closed, old_dt),
        )
        conn.execute(
            "INSERT INTO trade_outcomes (trade_id, pair, entry_price, exit_price, ml_confidence, recommendation, pnl_pct, hold_duration_minutes, outcome_label, created_at) VALUES (?, 'oldidr', 100, 101, 0.8, 'BUY', 1, 1, 'GOOD_BUY', ?)",
            (old_closed, old_dt),
        )

    deleted = db.cleanup_old_runtime_history(days=30)

    assert deleted["trades"] == 1
    assert deleted["performance"] == 1
    assert deleted["pair_performance"] == 1
    assert deleted["trade_reviews"] == 1
    assert deleted["trade_outcomes"] == 1

    with db.get_connection() as conn:
        remaining = conn.execute("SELECT id, status FROM trades ORDER BY id").fetchall()
    assert [(row["id"], row["status"]) for row in remaining] == [
        (recent_closed, "CLOSED"),
        (open_old, "OPEN"),
    ]


def test_reset_runtime_history_clears_telegram_bot_trade_history_tables(tmp_path):
    db_path = tmp_path / "trading.db"
    db = Database(str(db_path))
    db.add_user(1, "tester", "Tester")
    trade_id = db.add_trade(1, "btcidr", "BUY", 100, 1, 100, 0, "auto", 0.8)
    with db.get_connection() as conn:
        conn.execute("INSERT INTO performance (user_id, date, total_trades, winning_trades, losing_trades, total_profit_loss, win_rate) VALUES (1, DATE('now'), 1, 1, 0, 10, 100)")
        conn.execute("INSERT INTO pair_performance (pair, total_trades, win_count, loss_count, avg_profit_pct, avg_loss_pct, total_profit_pct, total_loss_pct, profit_factor, last_trade_at) VALUES ('btcidr', 1, 1, 0, 1, 0, 1, 0, 999, CURRENT_TIMESTAMP)")
        conn.execute("INSERT INTO trade_reviews (trade_id, pair, entry_price, exit_price, pnl_pct, hold_duration_minutes, max_profit_pct, max_loss_pct, ml_confidence, exit_reason, lesson) VALUES (?, 'btcidr', 100, 101, 1, 1, 1, 0, 0.8, 'exit', 'lesson')", (trade_id,))
        conn.execute("INSERT INTO trade_outcomes (trade_id, pair, entry_price, exit_price, ml_confidence, recommendation, pnl_pct, hold_duration_minutes, outcome_label) VALUES (?, 'btcidr', 100, 101, 0.8, 'BUY', 1, 1, 'GOOD_BUY')", (trade_id,))
        conn.execute("INSERT INTO signals (pair, signal_type, price, confidence) VALUES ('btcidr', 'BUY', 100, 0.8)")

    deleted = db.reset_runtime_history(include_open=True)

    assert deleted["trades"] == 1
    assert deleted["performance"] == 1
    assert deleted["pair_performance"] == 1
    assert deleted["trade_reviews"] == 1
    assert deleted["trade_outcomes"] == 1
    assert deleted["signals"] == 1
    for table in ["trades", "performance", "pair_performance", "trade_reviews", "trade_outcomes", "signals"]:
        assert _count(db_path, table) == 0
    assert _count(db_path, "users") == 1


def test_signal_database_reset_and_retention_with_size_threshold(tmp_path):
    db_path = tmp_path / "signals.db"
    signal_db = SignalDatabase(str(db_path))
    old_date = (datetime.now() - timedelta(days=45)).strftime("%Y-%m-%d")
    new_date = datetime.now().strftime("%Y-%m-%d")
    old_at = f"{old_date} 10:00:00"
    new_at = f"{new_date} 10:00:00"

    with signal_db.get_connection(autocommit=True) as conn:
        conn.execute("INSERT INTO signals (symbol, price, recommendation, received_at, received_date) VALUES ('OLDIDR', 1, 'BUY', ?, ?)", (old_at, old_date))
        conn.execute("INSERT INTO signals (symbol, price, recommendation, received_at, received_date) VALUES ('NEWIDR', 1, 'BUY', ?, ?)", (new_at, new_date))
        conn.execute("INSERT INTO signal_metadata (key, value) VALUES ('last_export', 'x')")

    deleted_old = signal_db.delete_old_signals(days=30, max_db_size_gb=10)
    assert deleted_old == 1
    assert signal_db.get_total_count() == 1

    deleted_reset = signal_db.reset_history()
    assert deleted_reset["signals"] == 1
    assert deleted_reset["signal_metadata"] == 1
    assert signal_db.get_total_count() == 0
