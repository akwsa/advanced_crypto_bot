#!/usr/bin/env python3
"""
LightGBM Offline Experiment — Bandingkan dengan V2 RF+GB ensemble.
TIDAK mengubah model live. Script standalone untuk evaluasi offline.

Usage:
    cd advanced_crypto_bot
    source venv/bin/activate
    python -m analysis.experiment_lgbm_v2 --pair btcidr --limit 5000

Metrics yang dibandingkan:
    - Accuracy, Precision, Recall, F1
    - Win Rate, Profit Factor, Expectancy
    - Training time, Inference latency per sample
"""

import argparse
import time
import warnings
from datetime import datetime

import numpy as np
import pandas as pd
from sklearn.ensemble import GradientBoostingClassifier, RandomForestClassifier
from sklearn.metrics import (
    accuracy_score,
    confusion_matrix,
    f1_score,
    precision_score,
    recall_score,
)
from sklearn.preprocessing import StandardScaler
from sklearn.utils.class_weight import compute_sample_weight

warnings.filterwarnings("ignore", message="X does not have valid feature names")

try:
    import lightgbm as lgb

    HAS_LGBM = True
except ImportError:
    HAS_LGBM = False
    print("❌ lightgbm not installed. Run: pip install lightgbm")

from analysis.ml_model_v2 import MLTradingModelV2


def _load_pair_data(pair: str, limit: int = 5000) -> pd.DataFrame:
    """Load historical candle data for a pair from the bot's data directory."""
    import os
    from pathlib import Path

    data_dir = Path("data/historical")
    candidates = [
        data_dir / f"{pair.lower()}.csv",
        data_dir / f"{pair.lower().replace('/', '_')}.csv",
        data_dir / f"{pair.lower().replace('/', '')}.csv",
    ]
    for path in candidates:
        if path.exists():
            df = pd.read_csv(path)
            if len(df) > limit:
                df = df.tail(limit).reset_index(drop=True)
            return df

    # Fallback: generate synthetic data for offline experiment
    print(f"⚠️ No historical data for {pair}, generating synthetic OHLCV for experiment")
    np.random.seed(42)
    n = limit
    close = 100.0 + np.cumsum(np.random.randn(n) * 0.5)
    close = np.maximum(close, 10.0)
    high = close * (1 + np.abs(np.random.randn(n)) * 0.005)
    low = close * (1 - np.abs(np.random.randn(n)) * 0.005)
    open_ = close * (1 + np.random.randn(n) * 0.002)
    volume = np.abs(np.random.randn(n)) * 1000 + 500
    return pd.DataFrame({
        "open": open_, "high": high, "low": low, "close": close, "volume": volume,
        "timestamp": range(n),
    })


def _evaluate(y_true, y_pred, label: str) -> dict:
    """Compute trading-relevant metrics."""
    accuracy = accuracy_score(y_true, y_pred)
    precision = precision_score(y_true, y_pred, zero_division=0)
    recall = recall_score(y_true, y_pred, zero_division=0)
    f1 = f1_score(y_true, y_pred, zero_division=0)

    cm = confusion_matrix(y_true, y_pred)
    tn, fp, fn, tp = cm.ravel() if cm.size == 4 else (0, 0, 0, 0)

    win_rate = tp / (tp + fn) if (tp + fn) > 0 else 0
    loss_rate = fp / (fp + tn) if (fp + tn) > 0 else 0
    profit_factor = win_rate / (loss_rate + 1e-9)
    expectancy = (win_rate * 1.0) - (loss_rate * 1.0)  # simplified

    return {
        "label": label,
        "accuracy": accuracy,
        "precision": precision,
        "recall": recall,
        "f1": f1,
        "win_rate": win_rate,
        "profit_factor": profit_factor,
        "expectancy": expectancy,
        "tp": tp, "fp": fp, "fn": fn, "tn": tn,
    }


def run_experiment(pair: str, limit: int = 5000):
    """Run LightGBM vs V2 RF+GB comparison."""
    if not HAS_LGBM:
        return

    print(f"\n{'='*60}")
    print(f"🔬 LightGBM Experiment — {pair.upper()}")
    print(f"   Data limit: {limit:,} candles")
    print(f"   Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"{'='*60}\n")

    # ---- Load & prepare features using V2 pipeline ----
    print("📊 Loading data & preparing features (V2 pipeline)...")
    v2 = MLTradingModelV2()
    df = _load_pair_data(pair, limit)

    t0 = time.time()
    features = v2.prepare_features(df)
    feature_prep_time = time.time() - t0

    if len(features) < 100:
        print("❌ Not enough data after feature engineering")
        return

    # Anti-lookahead: percentile thresholds from training portion only
    train_cutoff = int(len(features) * 0.8)
    train_returns = features["future_return_raw"].iloc[:train_cutoff].dropna()

    if len(train_returns) > 50:
        median = train_returns.quantile(0.50)
        dist_lower = median - train_returns.quantile(0.25)
        dist_upper = train_returns.quantile(0.75) - median
        sym_dist = min(dist_lower, dist_upper)
        sell_thr = median - sym_dist
        buy_thr = median + sym_dist

        if len(train_returns) > 100:
            dist_strong_lower = median - train_returns.quantile(0.10)
            dist_strong_upper = train_returns.quantile(0.90) - median
            sym_strong_dist = min(dist_strong_lower, dist_strong_upper)
        else:
            sym_strong_dist = sym_dist

        strong_sell_thr = median - sym_strong_dist
        strong_buy_thr = median + sym_strong_dist

        def _classify(ret):
            if pd.isna(ret):
                return 2
            if ret <= strong_sell_thr:
                return 0
            if ret <= sell_thr:
                return 1
            if ret >= strong_buy_thr:
                return 4
            if ret >= buy_thr:
                return 3
            return 2

        features["target_class"] = features["future_return_raw"].apply(_classify)
        features["target"] = (features["target_class"] >= 3).astype(int)
    else:
        features["target_class"] = features["future_return_raw"].apply(
            lambda r: 0 if r < -0.02 else (4 if r >= 0.03 else (3 if r >= 0.015 else (1 if r < 0 else 2)))
        )
        features["target"] = (features["target_class"] >= 3).astype(int)

    feature_names = v2.feature_names
    X = features[feature_names]
    y = features["target"]

    # Time-series split
    X_train, X_test = X.iloc[:train_cutoff], X.iloc[train_cutoff:]
    y_train, y_test = y.iloc[:train_cutoff], y.iloc[train_cutoff:]

    # Scale
    scaler = StandardScaler()
    X_train_scaled = scaler.fit_transform(X_train)
    X_test_scaled = scaler.transform(X_test)

    # Sample weights
    sample_weights = compute_sample_weight("balanced", y_train)

    print(f"   Features: {len(feature_names)}")
    print(f"   Train: {len(X_train):,} | Test: {len(X_test):,}")
    print(f"   Class dist train: {dict(y_train.value_counts())}")
    print(f"   Feature prep time: {feature_prep_time:.2f}s\n")

    results = []

    # ---- Model 1: V2 RF + GB Ensemble ----
    print("🤖 Training V2 RF+GB Ensemble...")
    rf = RandomForestClassifier(
        n_estimators=200, max_depth=8, min_samples_leaf=10,
        class_weight="balanced", n_jobs=1, random_state=42,
    )
    gb = GradientBoostingClassifier(
        n_estimators=150, max_depth=5, learning_rate=0.05,
        subsample=0.8, random_state=42,
    )

    t0 = time.time()
    rf.fit(X_train_scaled, y_train, sample_weight=sample_weights)
    gb.fit(X_train_scaled, y_train, sample_weight=sample_weights)
    v2_train_time = time.time() - t0

    t0 = time.time()
    rf_prob = rf.predict_proba(X_test_scaled)
    gb_prob = gb.predict_proba(X_test_scaled)
    rf_prob_class1 = rf_prob[:, 1] if rf_prob.shape[1] > 1 else rf_prob[:, 0]
    gb_prob_class1 = gb_prob[:, 1] if gb_prob.shape[1] > 1 else gb_prob[:, 0]
    ensemble_prob = (rf_prob_class1 + gb_prob_class1) / 2
    v2_pred = (ensemble_prob > 0.5).astype(int)
    v2_infer_time = time.time() - t0

    v2_metrics = _evaluate(y_test, v2_pred, "V2 RF+GB Ensemble")
    v2_metrics["train_time"] = v2_train_time
    v2_metrics["infer_time"] = v2_infer_time
    v2_metrics["infer_per_sample_ms"] = (v2_infer_time / len(X_test)) * 1000
    results.append(v2_metrics)

    # ---- Model 2: LightGBM Binary ----
    print("🤖 Training LightGBM (binary)...")
    lgbm_binary = lgb.LGBMClassifier(
        n_estimators=300,
        max_depth=6,
        learning_rate=0.05,
        num_leaves=31,
        subsample=0.8,
        colsample_bytree=0.8,
        class_weight="balanced",
        n_jobs=1,
        random_state=42,
        verbose=-1,
    )

    t0 = time.time()
    lgbm_binary.fit(X_train_scaled, y_train, sample_weight=sample_weights)
    lgbm_train_time = time.time() - t0

    t0 = time.time()
    lgbm_prob = lgbm_binary.predict_proba(X_test_scaled)
    lgbm_prob_class1 = lgbm_prob[:, 1] if lgbm_prob.shape[1] > 1 else lgbm_prob[:, 0]
    lgbm_pred = (lgbm_prob_class1 > 0.5).astype(int)
    lgbm_infer_time = time.time() - t0

    lgbm_metrics = _evaluate(y_test, lgbm_pred, "LightGBM Binary")
    lgbm_metrics["train_time"] = lgbm_train_time
    lgbm_metrics["infer_time"] = lgbm_infer_time
    lgbm_metrics["infer_per_sample_ms"] = (lgbm_infer_time / len(X_test)) * 1000
    results.append(lgbm_metrics)

    # ---- Model 3: LightGBM Multi-class ----
    print("🤖 Training LightGBM (multi-class)...")
    y_multi = features["target_class"]
    y_multi_train = y_multi.iloc[:train_cutoff]
    y_multi_test = y_multi.iloc[train_cutoff:]
    sample_weights_multi = compute_sample_weight("balanced", y_multi_train)

    lgbm_multi = lgb.LGBMClassifier(
        n_estimators=300,
        max_depth=6,
        learning_rate=0.05,
        num_leaves=31,
        subsample=0.8,
        colsample_bytree=0.8,
        class_weight="balanced",
        n_jobs=1,
        random_state=42,
        verbose=-1,
    )

    t0 = time.time()
    lgbm_multi.fit(X_train_scaled, y_multi_train, sample_weight=sample_weights_multi)
    lgbm_multi_train_time = time.time() - t0

    t0 = time.time()
    lgbm_multi_pred_raw = lgbm_multi.predict(X_test_scaled)
    lgbm_multi_infer_time = time.time() - t0

    # Convert multi-class to binary for comparison (class >= 3 = BUY)
    lgbm_multi_pred = (lgbm_multi_pred_raw >= 3).astype(int)
    lgbm_multi_metrics = _evaluate(y_test, lgbm_multi_pred, "LightGBM Multi→Binary")
    lgbm_multi_metrics["train_time"] = lgbm_multi_train_time
    lgbm_multi_metrics["infer_time"] = lgbm_multi_infer_time
    lgbm_multi_metrics["infer_per_sample_ms"] = (lgbm_multi_infer_time / len(X_test)) * 1000
    results.append(lgbm_multi_metrics)

    # ---- Print Comparison ----
    print(f"\n{'='*60}")
    print(f"📊 COMPARISON RESULTS")
    print(f"{'='*60}")

    header = f"{'Metric':<22} {'V2 RF+GB':>12} {'LGBM Bin':>12} {'LGBM Multi':>12}"
    print(header)
    print("-" * 60)

    for metric in ["accuracy", "precision", "recall", "f1", "win_rate", "profit_factor", "expectancy"]:
        vals = [r[metric] for r in results]
        fmt = ".2%" if metric in ("accuracy", "precision", "recall", "f1", "win_rate", "expectancy") else ".3f"
        print(f"{metric:<22} {vals[0]:>12{fmt}} {vals[1]:>12{fmt}} {vals[2]:>12{fmt}}")

    print("-" * 60)
    for metric in ["train_time", "infer_per_sample_ms"]:
        vals = [r[metric] for r in results]
        label = "train_time (s)" if metric == "train_time" else "infer/sample (ms)"
        print(f"{label:<22} {vals[0]:>12.3f} {vals[1]:>12.3f} {vals[2]:>12.3f}")

    print(f"\n{'='*60}")

    # ---- Feature Importance (LightGBM top 10) ----
    importances = lgbm_binary.feature_importances_
    top_idx = np.argsort(importances)[::-1][:10]
    print("\n📊 LightGBM Top-10 Feature Importance:")
    for i, idx in enumerate(top_idx):
        print(f"   {i+1:2d}. {feature_names[idx]:<30} {importances[idx]:>6.0f}")

    # ---- Verdict ----
    print(f"\n{'='*60}")
    print("📋 VERDICT:")
    best_f1 = max(results, key=lambda r: r["f1"])
    best_pf = max(results, key=lambda r: r["profit_factor"])
    fastest = min(results, key=lambda r: r["infer_per_sample_ms"])

    print(f"   Best F1:            {best_f1['label']} ({best_f1['f1']:.2%})")
    print(f"   Best Profit Factor: {best_pf['label']} ({best_pf['profit_factor']:.3f})")
    print(f"   Fastest Inference:  {fastest['label']} ({fastest['infer_per_sample_ms']:.3f} ms/sample)")

    lgbm_better = (
        results[1]["f1"] > results[0]["f1"]
        and results[1]["profit_factor"] > results[0]["profit_factor"]
    )
    if lgbm_better:
        print("\n   ✅ LightGBM outperforms V2 ensemble on F1 AND Profit Factor.")
        print("   → Consider promoting LightGBM as primary model after live validation.")
    else:
        print("\n   ⚠️ LightGBM does NOT clearly outperform V2 ensemble.")
        print("   → Keep V2 as primary. LightGBM can serve as additional ensemble member.")

    print(f"{'='*60}\n")

    return results


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="LightGBM vs V2 offline experiment")
    parser.add_argument("--pair", default="btcidr", help="Trading pair (default: btcidr)")
    parser.add_argument("--limit", type=int, default=5000, help="Max candles (default: 5000)")
    args = parser.parse_args()
    run_experiment(args.pair, args.limit)
