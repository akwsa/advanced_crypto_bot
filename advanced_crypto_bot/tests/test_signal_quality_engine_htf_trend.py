"""Regression test untuk Higher-Timeframe (HTF) trend filter di SignalQualityEngine.

Konteks (Phase B, 2026-06-12):
Data tick di-resample ke 1h candles, lalu SMA fast/slow dipakai untuk vonis
trend UP/DOWN/SIDEWAYS. Hasilnya jadi confluence bonus/penalty:
  - aligned (BUY+UP atau SELL+DOWN) → +1
  - counter-trend (BUY+DOWN atau SELL+UP) → -1
  - sideways atau data kurang → 0
"""
import sys
import os
from datetime import datetime, timedelta

import pandas as pd
import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from signals.signal_quality_engine import SignalQualityEngine


def _make_tick_df(prices, start=None, step_minutes=5):
    """Bangun DataFrame tick (open=high=low=close=last_price) dengan timestamp
    increment per `step_minutes`.
    """
    if start is None:
        start = datetime(2026, 6, 12, 0, 0, 0)
    rows = []
    for i, p in enumerate(prices):
        ts = start + timedelta(minutes=step_minutes * i)
        rows.append({
            'timestamp': ts,
            'open': p, 'high': p, 'low': p, 'close': p,
            'volume': 1000.0,
        })
    return pd.DataFrame(rows)


def test_htf_trend_uptrend():
    """Harga naik linear dari 100 → 130 di 12 jam → HTF SMA fast > slow → UP."""
    engine = SignalQualityEngine()
    # 144 tick × 5 menit = 12 jam
    prices = [100 + i * 0.2 for i in range(144)]
    df = _make_tick_df(prices)

    res = engine.compute_higher_tf_trend(df, target_minutes=60, sma_fast=3, sma_slow=6)
    assert res['trend'] == 'UP', f"Expected UP, got {res}"
    assert res['htf_candles'] >= 7  # min(sma_slow)+1
    assert res['spread_pct'] > 0


def test_htf_trend_downtrend():
    """Harga turun → HTF DOWN."""
    engine = SignalQualityEngine()
    prices = [130 - i * 0.2 for i in range(144)]
    df = _make_tick_df(prices)

    res = engine.compute_higher_tf_trend(df, target_minutes=60, sma_fast=3, sma_slow=6)
    assert res['trend'] == 'DOWN'
    assert res['spread_pct'] < 0


def test_htf_trend_sideways():
    """Harga oscillate di range sempit → SIDEWAYS (spread di bawah threshold)."""
    engine = SignalQualityEngine()
    # alternate ±0.1 dari 100, jadi SMA fast ≈ SMA slow
    prices = [100 + (0.1 if i % 2 == 0 else -0.1) for i in range(144)]
    df = _make_tick_df(prices)

    res = engine.compute_higher_tf_trend(
        df, target_minutes=60, sma_fast=3, sma_slow=6, trend_threshold_pct=1.0
    )
    assert res['trend'] == 'SIDEWAYS'
    assert abs(res['spread_pct']) < 1.0


def test_htf_trend_insufficient_data():
    """Cuma 2 jam tick → HTF candle < min, balikin INSUFFICIENT_DATA."""
    engine = SignalQualityEngine()
    prices = [100 + i * 0.5 for i in range(24)]  # 2 jam
    df = _make_tick_df(prices)

    res = engine.compute_higher_tf_trend(df, target_minutes=60, sma_fast=5, sma_slow=10)
    assert res['trend'] == 'INSUFFICIENT_DATA'
    assert res['sma_fast'] is None


def test_htf_trend_handles_empty_df():
    """Empty df: graceful insufficient, no crash."""
    engine = SignalQualityEngine()
    df = pd.DataFrame()
    res = engine.compute_higher_tf_trend(df)
    assert res['trend'] == 'INSUFFICIENT_DATA'
    assert res['htf_candles'] == 0


def test_htf_trend_handles_missing_timestamp():
    """DataFrame tanpa timestamp dan tanpa DatetimeIndex → INSUFFICIENT_DATA."""
    engine = SignalQualityEngine()
    df = pd.DataFrame({'close': [100, 101, 102]})
    res = engine.compute_higher_tf_trend(df)
    assert res['trend'] == 'INSUFFICIENT_DATA'


def test_htf_alignment_buy_uptrend_positive():
    engine = SignalQualityEngine()
    assert engine.htf_alignment_score('BUY', 'UP') == 1
    assert engine.htf_alignment_score('BUY', 'DOWN') == -1
    assert engine.htf_alignment_score('BUY', 'SIDEWAYS') == 0
    assert engine.htf_alignment_score('BUY', 'INSUFFICIENT_DATA') == 0


def test_htf_alignment_sell_downtrend_positive():
    engine = SignalQualityEngine()
    assert engine.htf_alignment_score('SELL', 'DOWN') == 1
    assert engine.htf_alignment_score('SELL', 'UP') == -1
    assert engine.htf_alignment_score('SELL', 'SIDEWAYS') == 0


def test_confluence_score_includes_htf_bonus():
    """Score akhir naik +1 saat htf_alignment_bonus=+1, turun saat -1 (floor 0)."""
    engine = SignalQualityEngine()
    base_kwargs = dict(
        rsi='NEUTRAL', macd='BULLISH', ma_trend='BULLISH',
        bollinger='NEUTRAL', volume='NORMAL',
        ml_confidence=0.6, ta_strength=0.0,
        signal_direction='BUY',
        mean_reversion_bonus=0,
    )

    base = engine._calculate_confluence_score(htf_alignment_bonus=0, **base_kwargs)
    aligned = engine._calculate_confluence_score(htf_alignment_bonus=1, **base_kwargs)
    counter = engine._calculate_confluence_score(htf_alignment_bonus=-1, **base_kwargs)

    assert aligned == base + 1
    assert counter == max(0, base - 1)


def test_confluence_score_floor_zero_with_negative_htf():
    """Scenario all-bad: base=0, HTF=-1 → score floor di 0 (bukan negative)."""
    engine = SignalQualityEngine()
    score = engine._calculate_confluence_score(
        rsi='OVERBOUGHT',  # bad for BUY
        macd='BEARISH',    # bad for BUY
        ma_trend='BEARISH',
        bollinger='UPPER_BAND',
        volume='LOW',
        ml_confidence=0.4,
        ta_strength=-0.2,
        signal_direction='BUY',
        mean_reversion_bonus=0,
        htf_alignment_bonus=-1,
    )
    assert score == 0


if __name__ == '__main__':
    sys.exit(pytest.main([__file__, '-v']))
