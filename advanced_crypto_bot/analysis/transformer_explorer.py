#!/usr/bin/env python3
"""Offline transformer-style feature explorer for future AutoTrade research.

This module deliberately does not place trades and is not used by runtime
execution. It builds deterministic sequence features from recent candles so the
project has a safe bridge toward transformer/orderbook sequence research without
introducing an unvalidated deep model into AutoTrade.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import pandas as pd


@dataclass
class TransformerFeatureSnapshot:
    pair: str
    sequence_length: int
    trend_slope_pct: float
    volatility_pct: float
    volume_zscore: float
    last_return_pct: float
    usable: bool
    reason: str = "ok"


def build_sequence_snapshot(df: pd.DataFrame, pair: str = "", sequence_length: int = 60) -> TransformerFeatureSnapshot:
    if df is None or getattr(df, "empty", True):
        return TransformerFeatureSnapshot(pair, sequence_length, 0.0, 0.0, 0.0, 0.0, False, "empty dataframe")
    if "close" not in df:
        return TransformerFeatureSnapshot(pair, sequence_length, 0.0, 0.0, 0.0, 0.0, False, "missing close column")
    window = df.tail(sequence_length).copy()
    if len(window) < max(10, sequence_length // 3):
        return TransformerFeatureSnapshot(pair, sequence_length, 0.0, 0.0, 0.0, 0.0, False, "insufficient sequence")

    close = pd.to_numeric(window["close"], errors="coerce").dropna()
    if len(close) < 2 or float(close.iloc[0]) <= 0:
        return TransformerFeatureSnapshot(pair, sequence_length, 0.0, 0.0, 0.0, 0.0, False, "invalid close values")

    returns = close.pct_change().dropna()
    trend_slope_pct = ((float(close.iloc[-1]) - float(close.iloc[0])) / float(close.iloc[0])) * 100
    volatility_pct = float(returns.std() * 100) if not returns.empty else 0.0
    last_return_pct = float(returns.iloc[-1] * 100) if not returns.empty else 0.0

    volume_zscore = 0.0
    if "volume" in window:
        volume = pd.to_numeric(window["volume"], errors="coerce").dropna()
        if len(volume) >= 5 and float(volume.std()) > 0:
            volume_zscore = float((volume.iloc[-1] - volume.mean()) / volume.std())

    return TransformerFeatureSnapshot(
        pair=pair,
        sequence_length=len(close),
        trend_slope_pct=round(trend_slope_pct, 4),
        volatility_pct=round(volatility_pct, 4),
        volume_zscore=round(volume_zscore, 4),
        last_return_pct=round(last_return_pct, 4),
        usable=True,
    )


def snapshot_to_features(snapshot: TransformerFeatureSnapshot) -> dict[str, Any]:
    return {
        "pair": snapshot.pair,
        "sequence_length": snapshot.sequence_length,
        "trend_slope_pct": snapshot.trend_slope_pct,
        "volatility_pct": snapshot.volatility_pct,
        "volume_zscore": snapshot.volume_zscore,
        "last_return_pct": snapshot.last_return_pct,
        "usable": snapshot.usable,
        "reason": snapshot.reason,
    }
