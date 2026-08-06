#!/usr/bin/env python3
"""Offline quant gate evaluator for AutoTrade outcomes.

Reads closed AutoTrade outcomes from SQLite and reports:
- walk-forward performance metrics;
- model-promotion pass/fail gate;
- meta-label probability (`prob_good_trade`) by pair/recommendation/confidence bucket;
- probability calibration bins for existing ML confidence.

This script is intentionally read-only. It does not retrain or promote runtime
models; use it as a preflight before enabling a new model/config in dry-run/live.
"""

from __future__ import annotations

import argparse
import json
import math
import sqlite3
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable


@dataclass
class GateThresholds:
    min_trades: int = 20
    min_profit_factor: float = 1.20
    min_expectancy_pct: float = 0.10
    max_drawdown_pct: float = 10.0
    max_ece: float = 0.20


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        if value is None:
            return default
        value = float(value)
        if math.isnan(value) or math.isinf(value):
            return default
        return value
    except (TypeError, ValueError):
        return default


def _confidence_bucket(confidence: float, step: float = 0.10) -> str:
    confidence = min(max(_safe_float(confidence, 0.0), 0.0), 1.0)
    low = math.floor(confidence / step) * step
    high = min(low + step, 1.0)
    return f"{low:.1f}-{high:.1f}"


def load_outcomes(db_path: Path) -> list[dict[str, Any]]:
    query = """
        SELECT
            t.id AS trade_id,
            COALESCE(o.pair, t.pair) AS pair,
            COALESCE(o.recommendation, t.type) AS recommendation,
            COALESCE(o.ml_confidence, t.ml_confidence, 0.5) AS ml_confidence,
            COALESCE(o.pnl_pct, t.profit_loss_pct, 0.0) AS pnl_pct,
            COALESCE(o.outcome_label,
                     CASE WHEN COALESCE(o.pnl_pct, t.profit_loss_pct, 0) > 0
                          THEN 'GOOD_BUY' ELSE 'BAD_BUY' END) AS outcome_label,
            COALESCE(o.created_at, t.closed_at, t.opened_at) AS event_time
        FROM trades t
        LEFT JOIN trade_outcomes o ON o.trade_id = t.id
        WHERE t.signal_source = 'auto'
          AND t.status = 'CLOSED'
          AND COALESCE(o.pnl_pct, t.profit_loss_pct) IS NOT NULL
        ORDER BY datetime(COALESCE(o.created_at, t.closed_at, t.opened_at)), t.id
    """
    with sqlite3.connect(str(db_path)) as conn:
        conn.row_factory = sqlite3.Row
        rows = [dict(row) for row in conn.execute(query)]
    for row in rows:
        row["pair"] = str(row.get("pair") or "").lower()
        row["recommendation"] = str(row.get("recommendation") or "").upper()
        row["ml_confidence"] = _safe_float(row.get("ml_confidence"), 0.5)
        row["pnl_pct"] = _safe_float(row.get("pnl_pct"), 0.0)
        row["is_good"] = 1 if row["pnl_pct"] > 0 else 0
        row["confidence_bucket"] = _confidence_bucket(row["ml_confidence"])
    return rows


def performance_metrics(rows: Iterable[dict[str, Any]]) -> dict[str, Any]:
    rows = list(rows)
    pnl = [_safe_float(row.get("pnl_pct"), 0.0) for row in rows]
    wins = [x for x in pnl if x > 0]
    losses = [x for x in pnl if x <= 0]
    gross_profit = sum(wins)
    gross_loss = abs(sum(losses))
    profit_factor = gross_profit / gross_loss if gross_loss > 0 else (999.0 if gross_profit > 0 else 0.0)
    equity = 0.0
    peak = 0.0
    max_drawdown = 0.0
    for value in pnl:
        equity += value
        peak = max(peak, equity)
        max_drawdown = max(max_drawdown, peak - equity)
    n = len(rows)
    return {
        "trades": n,
        "wins": len(wins),
        "losses": len(losses),
        "win_rate": (len(wins) / n) if n else 0.0,
        "gross_profit_pct": round(gross_profit, 4),
        "gross_loss_pct": round(gross_loss, 4),
        "net_pnl_pct": round(sum(pnl), 4),
        "profit_factor": round(profit_factor, 4),
        "expectancy_pct": round((sum(pnl) / n) if n else 0.0, 4),
        "max_drawdown_pct": round(max_drawdown, 4),
    }


def walk_forward_metrics(rows: list[dict[str, Any]], folds: int = 4) -> list[dict[str, Any]]:
    rows = list(rows)
    if folds <= 0 or len(rows) < folds:
        return []
    fold_size = max(len(rows) // folds, 1)
    result = []
    for index in range(folds):
        start = index * fold_size
        end = len(rows) if index == folds - 1 else min((index + 1) * fold_size, len(rows))
        fold_rows = rows[start:end]
        if not fold_rows:
            continue
        metrics = performance_metrics(fold_rows)
        metrics["fold"] = index + 1
        metrics["start_trade_id"] = fold_rows[0].get("trade_id")
        metrics["end_trade_id"] = fold_rows[-1].get("trade_id")
        result.append(metrics)
    return result


def calibration_report(rows: list[dict[str, Any]]) -> dict[str, Any]:
    buckets: dict[str, list[dict[str, Any]]] = {}
    for row in rows:
        buckets.setdefault(row["confidence_bucket"], []).append(row)
    total = len(rows)
    ece = 0.0
    brier_terms = []
    bucket_rows = []
    for bucket, items in sorted(buckets.items()):
        avg_conf = sum(_safe_float(row.get("ml_confidence"), 0.5) for row in items) / len(items)
        observed = sum(int(row.get("is_good", 0)) for row in items) / len(items)
        ece += (len(items) / total) * abs(avg_conf - observed) if total else 0.0
        for row in items:
            brier_terms.append((_safe_float(row.get("ml_confidence"), 0.5) - int(row.get("is_good", 0))) ** 2)
        bucket_rows.append({
            "bucket": bucket,
            "trades": len(items),
            "avg_confidence": round(avg_conf, 4),
            "observed_good_rate": round(observed, 4),
            "gap": round(avg_conf - observed, 4),
        })
    return {
        "ece": round(ece, 4),
        "brier_score": round(sum(brier_terms) / len(brier_terms), 4) if brier_terms else None,
        "bins": bucket_rows,
    }


def meta_label_probabilities(rows: list[dict[str, Any]], prior_strength: int = 4) -> list[dict[str, Any]]:
    """Return smoothed prob_good_trade by pair/recommendation/confidence bucket."""
    global_good_rate = (sum(int(row.get("is_good", 0)) for row in rows) / len(rows)) if rows else 0.5
    groups: dict[tuple[str, str, str], list[dict[str, Any]]] = {}
    for row in rows:
        key = (row["pair"], row["recommendation"], row["confidence_bucket"])
        groups.setdefault(key, []).append(row)
    result = []
    for (pair, recommendation, bucket), items in sorted(groups.items()):
        wins = sum(int(row.get("is_good", 0)) for row in items)
        prob = (wins + global_good_rate * prior_strength) / (len(items) + prior_strength)
        result.append({
            "pair": pair,
            "recommendation": recommendation,
            "confidence_bucket": bucket,
            "trades": len(items),
            "wins": wins,
            "prob_good_trade": round(prob, 4),
        })
    return result


def promotion_gate(overall: dict[str, Any], folds: list[dict[str, Any]], calibration: dict[str, Any], thresholds: GateThresholds) -> dict[str, Any]:
    reasons = []
    if overall["trades"] < thresholds.min_trades:
        reasons.append(f"trades {overall['trades']} < {thresholds.min_trades}")
    if overall["profit_factor"] < thresholds.min_profit_factor:
        reasons.append(f"profit_factor {overall['profit_factor']:.2f} < {thresholds.min_profit_factor:.2f}")
    if overall["expectancy_pct"] < thresholds.min_expectancy_pct:
        reasons.append(f"expectancy_pct {overall['expectancy_pct']:.2f} < {thresholds.min_expectancy_pct:.2f}")
    if overall["max_drawdown_pct"] > thresholds.max_drawdown_pct:
        reasons.append(f"max_drawdown_pct {overall['max_drawdown_pct']:.2f} > {thresholds.max_drawdown_pct:.2f}")
    weak_folds = [f for f in folds if f["profit_factor"] < 1.0 or f["expectancy_pct"] <= 0]
    if weak_folds:
        reasons.append(f"{len(weak_folds)} walk-forward fold(s) have non-positive expectancy or PF < 1")
    ece = calibration.get("ece")
    if ece is not None and ece > thresholds.max_ece:
        reasons.append(f"calibration ECE {ece:.2f} > {thresholds.max_ece:.2f}")
    return {
        "promote": not reasons,
        "reasons": reasons,
        "thresholds": thresholds.__dict__,
    }


def build_report(rows: list[dict[str, Any]], folds: int, thresholds: GateThresholds) -> dict[str, Any]:
    overall = performance_metrics(rows)
    fold_metrics = walk_forward_metrics(rows, folds=folds)
    calibration = calibration_report(rows)
    meta_labels = meta_label_probabilities(rows)
    return {
        "overall": overall,
        "walk_forward": fold_metrics,
        "promotion_gate": promotion_gate(overall, fold_metrics, calibration, thresholds),
        "calibration": calibration,
        "meta_label_probabilities": meta_labels,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", default="data/trading.db", help="SQLite trading DB path")
    parser.add_argument("--folds", type=int, default=4, help="Chronological walk-forward folds")
    parser.add_argument("--min-trades", type=int, default=20)
    parser.add_argument("--min-profit-factor", type=float, default=1.20)
    parser.add_argument("--min-expectancy-pct", type=float, default=0.10)
    parser.add_argument("--max-drawdown-pct", type=float, default=10.0)
    parser.add_argument("--max-ece", type=float, default=0.20)
    parser.add_argument("--output", help="Optional JSON report path")
    args = parser.parse_args()

    thresholds = GateThresholds(
        min_trades=args.min_trades,
        min_profit_factor=args.min_profit_factor,
        min_expectancy_pct=args.min_expectancy_pct,
        max_drawdown_pct=args.max_drawdown_pct,
        max_ece=args.max_ece,
    )
    rows = load_outcomes(Path(args.db))
    report = build_report(rows, folds=args.folds, thresholds=thresholds)
    text = json.dumps(report, indent=2, ensure_ascii=False)
    if args.output:
        Path(args.output).write_text(text + "\n", encoding="utf-8")
    print(text)
    return 0 if report["promotion_gate"]["promote"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
