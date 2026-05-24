#!/usr/bin/env python3
"""Backfill profit feedback tables from closed trades history."""

from __future__ import annotations

import argparse
from collections import defaultdict
from pathlib import Path
import sys
from datetime import datetime

APP_ROOT = Path(__file__).resolve().parents[1]
if str(APP_ROOT) not in sys.path:
    sys.path.insert(0, str(APP_ROOT))

from core.database import Database

MIN_VALID_TOTAL_IDR = 10_000


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Backfill trading.db profit feedback tables from trade history.")
    parser.add_argument("--db", default="data/trading.db", help="Path to trading.db")
    parser.add_argument(
        "--no-reset",
        action="store_true",
        help="Do not clear feedback tables before rebuilding. Default clears feedback tables for idempotent results.",
    )
    parser.add_argument(
        "--adaptive-days",
        type=int,
        default=3650,
        help="Lookback window for rebuilding adaptive thresholds. Default: 3650 days.",
    )
    return parser.parse_args()


def _parse_dt(value):
    if isinstance(value, datetime):
        return value
    if not value:
        return None
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except Exception:
        return None


def _trade_total(row):
    total = row["total"] if "total" in row.keys() else None
    if total is not None:
        try:
            return float(total)
        except (TypeError, ValueError):
            pass
    return float(row["price"] or 0) * float(row["amount"] or 0)


def _valid_trade_amount(row):
    try:
        price = float(row["price"] or 0)
        amount = float(row["amount"] or 0)
        total = _trade_total(row)
    except (TypeError, ValueError):
        return False

    return price > 0 and amount > 0 and total >= MIN_VALID_TOTAL_IDR


def _clear_feedback_tables(conn):
    for table in [
        "performance",
        "pair_performance",
        "trade_reviews",
        "trade_outcomes",
        "adaptive_thresholds",
    ]:
        conn.execute(f"DELETE FROM {table}")


def _rebuild_legacy_sell_feedback(db: Database) -> dict:
    """Match historical SELL rows to previous BUY rows using FIFO lots.

    Older Indodax sync stored BUY rows as OPEN and SELL rows as CLOSED, without
    realized PnL. This rebuilds feedback for SELL rows that can be matched to
    earlier valid BUY lots. It does not alter BUY row status.
    """
    with db.get_connection() as conn:
        rows = conn.execute(
            """
            SELECT *
            FROM trades
            ORDER BY pair ASC, id ASC
            """
        ).fetchall()

        lots_by_pair = defaultdict(list)
        rebuilt = 0
        skipped_unmatched = 0
        skipped_invalid = 0
        pairs = set()

        for row in rows:
            trade_type = str(row["type"] or "").upper()
            pair = row["pair"]

            if trade_type == "BUY":
                if not _valid_trade_amount(row):
                    skipped_invalid += 1
                    continue
                lots_by_pair[pair].append({
                    "remaining": float(row["amount"] or 0),
                    "price": float(row["price"] or 0),
                    "opened_at": row["opened_at"],
                    "ml_confidence": row["ml_confidence"] if row["ml_confidence"] is not None else 0.5,
                })
                continue

            if trade_type != "SELL" or str(row["status"] or "").upper() != "CLOSED":
                continue

            if not _valid_trade_amount(row):
                skipped_invalid += 1
                continue

            sell_amount = float(row["amount"] or 0)
            sell_price = float(row["price"] or 0)
            remaining_to_match = sell_amount
            cost = 0.0
            matched_amount = 0.0
            first_opened_at = None
            weighted_confidence = 0.0

            lots = lots_by_pair[pair]
            while remaining_to_match > 1e-12 and lots:
                lot = lots[0]
                matched = min(remaining_to_match, lot["remaining"])
                cost += matched * lot["price"]
                matched_amount += matched
                weighted_confidence += matched * float(lot["ml_confidence"] or 0.5)
                if first_opened_at is None:
                    first_opened_at = lot["opened_at"]
                lot["remaining"] -= matched
                remaining_to_match -= matched
                if lot["remaining"] <= 1e-12:
                    lots.pop(0)

            if matched_amount <= 0:
                skipped_unmatched += 1
                continue

            proceeds = sell_price * matched_amount
            pnl = proceeds - cost
            pnl_pct = (pnl / cost * 100) if cost > 0 else 0.0
            avg_entry = cost / matched_amount if matched_amount > 0 else 0.0
            avg_confidence = weighted_confidence / matched_amount if matched_amount > 0 else 0.5
            closed_at = _parse_dt(row["opened_at"]) or datetime.now()

            conn.execute(
                """
                UPDATE trades
                SET profit_loss = ?,
                    profit_loss_pct = ?,
                    closed_at = COALESCE(closed_at, ?)
                WHERE id = ?
                """,
                (pnl, pnl_pct, closed_at, row["id"]),
            )

            if row["user_id"] is not None:
                db._upsert_performance_for_date(conn, row["user_id"], closed_at.date())

            db._update_pair_performance(conn, pair, pnl_pct)

            synthetic_trade = dict(row)
            synthetic_trade["price"] = avg_entry
            synthetic_trade["amount"] = matched_amount
            synthetic_trade["type"] = "BUY"
            synthetic_trade["opened_at"] = first_opened_at or row["opened_at"]
            synthetic_trade["ml_confidence"] = avg_confidence

            db.create_trade_review(
                conn,
                synthetic_trade,
                sell_price,
                pnl_pct,
                "Backfill FIFO matched SELL",
            )

            db._record_trade_outcome(
                conn,
                row["id"],
                pair,
                avg_entry,
                sell_price,
                avg_confidence,
                "BUY",
                pnl_pct,
                synthetic_trade["opened_at"],
                closed_at,
            )

            rebuilt += 1
            pairs.add(pair)

        return {
            "legacy_sell_rows_rebuilt": rebuilt,
            "legacy_pairs": sorted(pairs),
            "skipped_unmatched": skipped_unmatched,
            "skipped_invalid": skipped_invalid,
        }


def _rebuild_closed_trade_feedback(db: Database) -> dict:
    """Rebuild feedback for already closed trades that have explicit PnL."""
    with db.get_connection() as conn:
        rows = conn.execute(
            """
            SELECT *
            FROM trades
            WHERE status = 'CLOSED'
              AND type != 'SELL'
              AND profit_loss_pct IS NOT NULL
            ORDER BY datetime(COALESCE(closed_at, opened_at)) ASC, id ASC
            """
        ).fetchall()

        rebuilt = 0
        for row in rows:
            closed_at = _parse_dt(row["closed_at"]) or _parse_dt(row["opened_at"]) or datetime.now()
            pnl_pct = float(row["profit_loss_pct"] or 0)
            exit_price = float(row["price"] or 0) * (1 + pnl_pct / 100)

            if row["user_id"] is not None:
                db._upsert_performance_for_date(conn, row["user_id"], closed_at.date())
            db._update_pair_performance(conn, row["pair"], pnl_pct)
            db.create_trade_review(conn, row, exit_price, pnl_pct, "Backfill explicit closed trade")
            db._record_trade_outcome(
                conn,
                row["id"],
                row["pair"],
                row["price"],
                exit_price,
                row["ml_confidence"] if row["ml_confidence"] is not None else 0.5,
                row["type"],
                pnl_pct,
                row["opened_at"],
                closed_at,
            )
            rebuilt += 1

        return {"explicit_closed_rows_rebuilt": rebuilt}


def _rebuild_adaptive_thresholds(db: Database, days: int = 3650) -> dict:
    try:
        from analysis.adaptive_learning import AdaptiveLearningEngine

        engine = AdaptiveLearningEngine(db)
        with db.get_connection() as conn:
            pairs = [
                row["pair"]
                for row in conn.execute(
                    """
                    SELECT pair
                    FROM pair_performance
                    WHERE total_trades > 0
                    ORDER BY total_trades DESC, pair ASC
                    """
                ).fetchall()
            ]

        rebuilt = 0
        skipped = 0
        for pair in pairs:
            metrics = engine.analyze_pair_performance(pair, days=days)
            if metrics:
                engine.update_adaptive_thresholds(metrics)
                rebuilt += 1
            else:
                skipped += 1

        return {
            "adaptive_thresholds_rebuilt": rebuilt,
            "adaptive_thresholds_skipped": skipped,
            "adaptive_days": days,
        }
    except Exception as exc:
        return {
            "adaptive_thresholds_rebuilt": 0,
            "adaptive_thresholds_skipped": 0,
            "adaptive_days": days,
            "adaptive_error": str(exc),
        }


def run_backfill(
    db_path: str = "data/trading.db",
    reset_feedback: bool = True,
    adaptive_days: int = 3650,
) -> dict:
    db = Database(db_path)
    if reset_feedback:
        with db.get_connection() as conn:
            _clear_feedback_tables(conn)

    explicit_result = _rebuild_closed_trade_feedback(db)
    legacy_result = _rebuild_legacy_sell_feedback(db)
    adaptive_result = _rebuild_adaptive_thresholds(db, days=adaptive_days)

    with db.get_connection() as conn:
        rows = conn.execute(
            """
            SELECT DISTINCT user_id, DATE(closed_at) AS closed_date
            FROM trades
            WHERE status = 'CLOSED' AND user_id IS NOT NULL AND closed_at IS NOT NULL
            ORDER BY closed_date ASC, user_id ASC
            """
        ).fetchall()

    rebuilt = 0
    per_user = defaultdict(int)
    for row in rows:
        db.update_performance(row["user_id"], row["closed_date"])
        rebuilt += 1
        per_user[row["user_id"]] += 1

    result = {
        "db_path": db_path,
        "reset_feedback": reset_feedback,
        "daily_rows_rebuilt": rebuilt,
        "users": dict(sorted(per_user.items())),
        **explicit_result,
        **legacy_result,
        **adaptive_result,
    }

    db.close_thread_connection()
    return result


def main() -> None:
    args = _parse_args()
    result = run_backfill(
        args.db,
        reset_feedback=not args.no_reset,
        adaptive_days=args.adaptive_days,
    )

    print("Profit feedback backfill complete")
    print(f"db_path: {result['db_path']}")
    print(f"reset_feedback: {result['reset_feedback']}")
    print(f"explicit_closed_rows_rebuilt: {result['explicit_closed_rows_rebuilt']}")
    print(f"legacy_sell_rows_rebuilt: {result['legacy_sell_rows_rebuilt']}")
    print(f"adaptive_thresholds_rebuilt: {result['adaptive_thresholds_rebuilt']}")
    print(f"adaptive_thresholds_skipped: {result['adaptive_thresholds_skipped']}")
    print(f"adaptive_days: {result['adaptive_days']}")
    if result.get("adaptive_error"):
        print(f"adaptive_error: {result['adaptive_error']}")
    print(f"daily_rows_rebuilt: {result['daily_rows_rebuilt']}")
    print(f"skipped_unmatched: {result['skipped_unmatched']}")
    print(f"skipped_invalid: {result['skipped_invalid']}")
    if result["legacy_pairs"]:
        print(f"legacy_pairs: {', '.join(result['legacy_pairs'])}")
    if result["users"]:
        print("users:")
        for user_id, count in result["users"].items():
            print(f"  - {user_id}: {count} day(s)")
    else:
        print("users: none (no closed trades found)")


if __name__ == "__main__":
    main()
