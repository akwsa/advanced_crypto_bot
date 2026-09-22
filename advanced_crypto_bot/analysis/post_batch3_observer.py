#!/usr/bin/env python3
"""Post Batch signal observation report.

Tracks:
- HOLD caused by [PRICE_VALIDATION]
- HOLD caused by [FINAL_POLICY]
- BUY/SELL distribution shift
- Simple signal-noise proxies
"""

from __future__ import annotations

import argparse
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Dict, Tuple


@dataclass
class WindowMetrics:
    total: int
    hold: int
    buy: int
    strong_buy: int
    sell: int
    strong_sell: int
    actionable: int
    pv_hold: int
    fp_hold: int
    weak_actionable: int
    low_conf_actionable: int
    conflict_actionable: int

    def rec_distribution(self) -> Dict[str, float]:
        if self.total <= 0:
            return {k: 0.0 for k in ["HOLD", "BUY", "STRONG_BUY", "SELL", "STRONG_SELL"]}
        return {
            "HOLD": self.hold / self.total * 100,
            "BUY": self.buy / self.total * 100,
            "STRONG_BUY": self.strong_buy / self.total * 100,
            "SELL": self.sell / self.total * 100,
            "STRONG_SELL": self.strong_sell / self.total * 100,
        }

    def noise_proxy(self) -> Dict[str, float]:
        if self.actionable <= 0:
            return {
                "weak_actionable_pct": 0.0,
                "low_conf_actionable_pct": 0.0,
                "conflict_actionable_pct": 0.0,
            }
        return {
            "weak_actionable_pct": self.weak_actionable / self.actionable * 100,
            "low_conf_actionable_pct": self.low_conf_actionable / self.actionable * 100,
            "conflict_actionable_pct": self.conflict_actionable / self.actionable * 100,
        }


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Observe post-batch signal quality metrics.")
    parser.add_argument("--db", default="data/signals.db", help="Path to signals.db")
    parser.add_argument("--hours", type=int, default=24, help="Observation window in hours")
    parser.add_argument(
        "--compare-prev",
        action="store_true",
        help="Compare with previous equal-length window",
    )
    return parser.parse_args()


def _window_metrics(conn: sqlite3.Connection, start: str, end: str) -> WindowMetrics:
    q = """
    SELECT
      COUNT(*) AS total,
      SUM(CASE WHEN recommendation='HOLD' THEN 1 ELSE 0 END) AS hold,
      SUM(CASE WHEN recommendation='BUY' THEN 1 ELSE 0 END) AS buy,
      SUM(CASE WHEN recommendation='STRONG_BUY' THEN 1 ELSE 0 END) AS strong_buy,
      SUM(CASE WHEN recommendation='SELL' THEN 1 ELSE 0 END) AS sell,
      SUM(CASE WHEN recommendation='STRONG_SELL' THEN 1 ELSE 0 END) AS strong_sell,
      SUM(CASE WHEN recommendation IN ('BUY','STRONG_BUY','SELL','STRONG_SELL') THEN 1 ELSE 0 END) AS actionable,
      SUM(CASE WHEN recommendation='HOLD' AND (final_gate_source='PRICE_VALIDATION' OR analysis LIKE '[PRICE_VALIDATION]%') THEN 1 ELSE 0 END) AS pv_hold,
      SUM(CASE WHEN recommendation='HOLD' AND (final_gate_source='FINAL_POLICY' OR analysis LIKE '[FINAL_POLICY]%') THEN 1 ELSE 0 END) AS fp_hold,
      SUM(CASE WHEN recommendation IN ('BUY','STRONG_BUY','SELL','STRONG_SELL') AND ABS(COALESCE(combined_strength,0)) < 0.12 THEN 1 ELSE 0 END) AS weak_actionable,
      SUM(CASE WHEN recommendation IN ('BUY','STRONG_BUY','SELL','STRONG_SELL') AND COALESCE(ml_confidence,0) < 0.65 THEN 1 ELSE 0 END) AS low_conf_actionable,
      SUM(CASE WHEN (recommendation IN ('BUY','STRONG_BUY') AND COALESCE(combined_strength,0) < 0)
                OR (recommendation IN ('SELL','STRONG_SELL') AND COALESCE(combined_strength,0) > 0.3)
               THEN 1 ELSE 0 END) AS conflict_actionable
    FROM signals
    WHERE received_at >= ? AND received_at < ?
    """
    row = conn.execute(q, (start, end)).fetchone()
    return WindowMetrics(
        total=row["total"] or 0,
        hold=row["hold"] or 0,
        buy=row["buy"] or 0,
        strong_buy=row["strong_buy"] or 0,
        sell=row["sell"] or 0,
        strong_sell=row["strong_sell"] or 0,
        actionable=row["actionable"] or 0,
        pv_hold=row["pv_hold"] or 0,
        fp_hold=row["fp_hold"] or 0,
        weak_actionable=row["weak_actionable"] or 0,
        low_conf_actionable=row["low_conf_actionable"] or 0,
        conflict_actionable=row["conflict_actionable"] or 0,
    )


def _fmt_pct(x: float) -> str:
    return f"{x:.2f}%"


def _print_window(label: str, m: WindowMetrics) -> None:
    dist = m.rec_distribution()
    noise = m.noise_proxy()
    print(f"\n=== {label} ===")
    print(f"total_signals: {m.total}")
    print(f"actionable_signals: {m.actionable}")
    print(f"price_validation_hold: {m.pv_hold} ({_fmt_pct((m.pv_hold / m.total * 100) if m.total else 0.0)})")
    print(f"final_policy_hold: {m.fp_hold} ({_fmt_pct((m.fp_hold / m.total * 100) if m.total else 0.0)})")
    print(
        "distribution:"
        f" HOLD={_fmt_pct(dist['HOLD'])},"
        f" BUY={_fmt_pct(dist['BUY'])},"
        f" STRONG_BUY={_fmt_pct(dist['STRONG_BUY'])},"
        f" SELL={_fmt_pct(dist['SELL'])},"
        f" STRONG_SELL={_fmt_pct(dist['STRONG_SELL'])}"
    )
    print(
        "noise_proxy_on_actionable:"
        f" weak={_fmt_pct(noise['weak_actionable_pct'])},"
        f" low_conf={_fmt_pct(noise['low_conf_actionable_pct'])},"
        f" conflict={_fmt_pct(noise['conflict_actionable_pct'])}"
    )


def _deltas(curr: WindowMetrics, prev: WindowMetrics) -> Dict[str, float]:
    cdist, pdist = curr.rec_distribution(), prev.rec_distribution()
    cnoise, pnoise = curr.noise_proxy(), prev.noise_proxy()
    return {
        "delta_hold_pct": cdist["HOLD"] - pdist["HOLD"],
        "delta_buy_like_pct": (cdist["BUY"] + cdist["STRONG_BUY"]) - (pdist["BUY"] + pdist["STRONG_BUY"]),
        "delta_sell_like_pct": (cdist["SELL"] + cdist["STRONG_SELL"]) - (pdist["SELL"] + pdist["STRONG_SELL"]),
        "delta_price_validation_hold_pct": ((curr.pv_hold / curr.total * 100) if curr.total else 0.0) - ((prev.pv_hold / prev.total * 100) if prev.total else 0.0),
        "delta_final_policy_hold_pct": ((curr.fp_hold / curr.total * 100) if curr.total else 0.0) - ((prev.fp_hold / prev.total * 100) if prev.total else 0.0),
        "delta_weak_actionable_pct": cnoise["weak_actionable_pct"] - pnoise["weak_actionable_pct"],
        "delta_low_conf_actionable_pct": cnoise["low_conf_actionable_pct"] - pnoise["low_conf_actionable_pct"],
        "delta_conflict_actionable_pct": cnoise["conflict_actionable_pct"] - pnoise["conflict_actionable_pct"],
    }


def main() -> None:
    args = _parse_args()
    conn = sqlite3.connect(args.db)
    conn.row_factory = sqlite3.Row

    now = datetime.now()
    start = now - timedelta(hours=args.hours)
    prev_start = start - timedelta(hours=args.hours)

    s_now = now.strftime("%Y-%m-%d %H:%M:%S")
    s_start = start.strftime("%Y-%m-%d %H:%M:%S")
    s_prev = prev_start.strftime("%Y-%m-%d %H:%M:%S")

    print("Post-Batch Observation")
    print(f"now: {s_now}")
    print(f"window_hours: {args.hours}")
    print(f"current_window: [{s_start} .. {s_now})")

    curr = _window_metrics(conn, s_start, s_now)
    _print_window("CURRENT", curr)

    if args.compare_prev:
        print(f"previous_window: [{s_prev} .. {s_start})")
        prev = _window_metrics(conn, s_prev, s_start)
        _print_window("PREVIOUS", prev)
        d = _deltas(curr, prev)
        print("\n=== DELTA (CURRENT - PREVIOUS) ===")
        for k, v in d.items():
            print(f"{k}: {v:+.2f}pp")

    conn.close()


if __name__ == "__main__":
    main()
