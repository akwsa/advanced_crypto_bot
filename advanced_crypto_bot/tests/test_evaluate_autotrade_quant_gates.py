from scripts.evaluate_autotrade_quant_gates import (
    GateThresholds,
    build_report,
    calibration_report,
    meta_label_probabilities,
    performance_metrics,
)


def _row(trade_id, pnl, conf=0.7, pair="testidr", rec="BUY"):
    return {
        "trade_id": trade_id,
        "pair": pair,
        "recommendation": rec,
        "ml_confidence": conf,
        "pnl_pct": pnl,
        "is_good": 1 if pnl > 0 else 0,
        "confidence_bucket": "0.7-0.8",
    }


def test_performance_metrics_include_profit_factor_expectancy_drawdown():
    rows = [_row(1, 2.0), _row(2, -1.0), _row(3, 3.0), _row(4, -2.0)]

    metrics = performance_metrics(rows)

    assert metrics["trades"] == 4
    assert metrics["wins"] == 2
    assert metrics["losses"] == 2
    assert metrics["profit_factor"] == 1.6667
    assert metrics["expectancy_pct"] == 0.5
    assert metrics["max_drawdown_pct"] == 2.0


def test_calibration_report_calculates_ece_and_brier():
    rows = [
        _row(1, 1.0, conf=0.8),
        _row(2, -1.0, conf=0.8),
        _row(3, 1.0, conf=0.6),
        _row(4, 1.0, conf=0.6),
    ]
    for row in rows:
        row["confidence_bucket"] = "0.8-0.9" if row["ml_confidence"] >= 0.8 else "0.6-0.7"

    report = calibration_report(rows)

    assert report["ece"] > 0
    assert report["brier_score"] is not None
    assert len(report["bins"]) == 2


def test_meta_label_probabilities_are_smoothed_by_group():
    rows = [_row(1, 1.0), _row(2, -1.0), _row(3, 1.0, pair="otheridr")]

    probs = meta_label_probabilities(rows, prior_strength=2)

    assert len(probs) == 2
    test_group = [p for p in probs if p["pair"] == "testidr"][0]
    assert 0 < test_group["prob_good_trade"] < 1


def test_build_report_blocks_promotion_on_weak_walk_forward_fold():
    rows = [
        _row(1, 2.0),
        _row(2, 1.0),
        _row(3, -3.0),
        _row(4, -2.0),
    ]

    report = build_report(
        rows,
        folds=2,
        thresholds=GateThresholds(
            min_trades=4,
            min_profit_factor=0.5,
            min_expectancy_pct=-10.0,
            max_drawdown_pct=20.0,
            max_ece=1.0,
        ),
    )

    assert report["promotion_gate"]["promote"] is False
    assert any("walk-forward" in reason for reason in report["promotion_gate"]["reasons"])
