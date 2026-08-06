#!/usr/bin/env python3
"""Export offline transformer-style sequence feature snapshots from price_history."""

from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from analysis.transformer_explorer import build_sequence_snapshot, snapshot_to_features  # noqa: E402


def load_pair_frame(conn: sqlite3.Connection, pair: str, limit: int) -> pd.DataFrame:
    rows = conn.execute(
        """
        SELECT timestamp, close, volume
        FROM price_history
        WHERE pair = ?
        ORDER BY datetime(timestamp) DESC
        LIMIT ?
        """,
        (pair, int(limit)),
    ).fetchall()
    df = pd.DataFrame(rows, columns=["timestamp", "close", "volume"])
    if df.empty:
        return df
    return df.iloc[::-1].reset_index(drop=True)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", default="data/trading.db")
    parser.add_argument("--pairs", default="", help="Comma-separated pairs; default=top pairs in price_history")
    parser.add_argument("--limit", type=int, default=240)
    parser.add_argument("--sequence-length", type=int, default=60)
    parser.add_argument("--output", default="")
    args = parser.parse_args()

    with sqlite3.connect(args.db) as conn:
        if args.pairs:
            pairs = [p.strip().lower() for p in args.pairs.split(",") if p.strip()]
        else:
            pairs = [
                row[0] for row in conn.execute(
                    "SELECT pair FROM price_history GROUP BY pair ORDER BY MAX(timestamp) DESC LIMIT 20"
                ).fetchall()
            ]
        snapshots = []
        for pair in pairs:
            df = load_pair_frame(conn, pair, args.limit)
            snapshots.append(snapshot_to_features(build_sequence_snapshot(df, pair, args.sequence_length)))

    text = json.dumps({"snapshots": snapshots}, indent=2, ensure_ascii=False)
    if args.output:
        Path(args.output).write_text(text + "\n", encoding="utf-8")
    print(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
