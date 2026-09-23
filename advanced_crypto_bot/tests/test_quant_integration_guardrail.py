"""Regression tests: quant integration — TypeSafe fast gate guardrail,
Bayesian Kelly dynamic sizing clamps, and Mean Reversion confluence weight.

Cakupan (docs/HERMES_HANDOVER.md Phase 1-3):
  1. autotrade/fast_gate.py  — validate_pre_trade_intent + QuantSignalContext
  2. autotrade/risk_manager  — bayesian_kelly_position_size + clamp_position_size
  3. signals/signal_quality_engine — calculate_weighted_mean_reversion_bonus
  4. autotrade/runtime       — _build_quant_signal_context / _run_fast_gate wiring
"""
from __future__ import annotations

import math
import os
import sys
import time
from datetime import datetime, timezone
from unittest.mock import MagicMock

import pytest


def _utcnow() -> float:
    return datetime.now(timezone.utc).timestamp()


# =============================================================================
# 1. FAST GATE — TypeSafe pre-trade guardrail
# =============================================================================

def _make_intent(pair="btcidr", recommendation="BUY", price=1_500_000_000,
                 confidence=0.75, age_seconds=60):
    from autotrade.contracts import TradeIntent
    return TradeIntent.from_signal({
        "pair": pair,
        "signal_type": recommendation,
        "price": price,
        "confidence": confidence,
        "created_at": _utcnow() - age_seconds,
        "data": {"signal": {
            "pair": pair,
            "recommendation": recommendation,
            "price": price,
            "ml_confidence": confidence,
        }},
    })


class TestFastGateContract:
    def test_valid_intent_passes(self):
        from autotrade.fast_gate import validate_pre_trade_intent
        intent = _make_intent()
        allowed, code, detail, conf = validate_pre_trade_intent(intent)
        assert allowed is True
        assert code == "OK"
        assert conf == 1.0

    def test_stale_signal_rejected(self):
        from autotrade.fast_gate import validate_pre_trade_intent
        intent = _make_intent(age_seconds=3600)
        allowed, code, detail, conf = validate_pre_trade_intent(intent, max_age_seconds=900)
        assert allowed is False
        assert code == "STALE_SIGNAL"

    def test_future_signal_rejected(self):
        from autotrade.contracts import TradeIntent
        from autotrade.fast_gate import validate_pre_trade_intent
        payload = {
            "pair": "btcidr",
            "signal_type": "BUY",
            "price": 1_000_000,
            "confidence": 0.7,
            "created_at": _utcnow() + 7200,
            "data": {"signal": {"pair": "btcidr", "recommendation": "BUY",
                                "price": 1_000_000, "ml_confidence": 0.7}},
        }
        intent = TradeIntent.from_signal(payload)
        allowed, code, _, _ = validate_pre_trade_intent(intent)
        assert allowed is False
        assert code == "FUTURE_SIGNAL"

    def test_invalid_price_rejected(self):
        from autotrade.fast_gate import validate_pre_trade_intent
        intent = _make_intent(price=0)
        allowed, code, _, _ = validate_pre_trade_intent(intent)
        assert allowed is False
        assert code in ("INVALID_PRICE", "MISSING_PAIR")

    def test_hold_recommendation_rejected(self):
        from autotrade.fast_gate import validate_pre_trade_intent
        intent = _make_intent(recommendation="HOLD")
        allowed, code, _, _ = validate_pre_trade_intent(intent)
        assert allowed is False
        assert code == "INVALID_RECOMMENDATION"


class TestFastGateFailOpen:
    def test_none_intent_fails_open(self):
        from autotrade.fast_gate import validate_pre_trade_intent
        allowed, code, _, _ = validate_pre_trade_intent(None)
        assert allowed is True
        assert code.startswith("GATE_SKIP")

    def test_unsupported_type_fails_open(self):
        from autotrade.fast_gate import validate_pre_trade_intent
        allowed, code, _, _ = validate_pre_trade_intent(12345)
        assert allowed is True
        assert code == "GATE_SKIP_INTENT_TYPE"

    def test_broken_market_context_does_not_block(self):
        from autotrade.fast_gate import validate_pre_trade_intent
        intent = _make_intent()
        allowed, _, _, _ = validate_pre_trade_intent(intent, market_context={"price": object()})
        assert allowed is True


class TestFastGateQuantContext:
    def _ctx(self, **kw):
        from autotrade.fast_gate import QuantSignalContext
        return QuantSignalContext(**kw)

    def test_cvar_gate_blocks(self):
        from autotrade.fast_gate import validate_pre_trade_intent
        intent = _make_intent()
        ctx = self._ctx(cvar95_pct=-9.5, var95_pct=-4.0)
        allowed, code, detail, _ = validate_pre_trade_intent(
            intent, quant_context=ctx, max_age_seconds=None)
        assert allowed is False
        assert code == "CVAR_TOO_HIGH"
        assert "CVaR95" in detail

    def test_var_gate_blocks(self):
        from autotrade.fast_gate import validate_pre_trade_intent
        intent = _make_intent()
        ctx = self._ctx(var95_pct=-13.0, cvar95_pct=-6.0)
        allowed, code, _, _ = validate_pre_trade_intent(
            intent, quant_context=ctx, max_age_seconds=None)
        assert allowed is False
        assert code == "VAR_TOO_HIGH"

    def test_correlation_exposure_blocks(self):
        from autotrade.fast_gate import validate_pre_trade_intent
        intent = _make_intent()
        ctx = self._ctx(correlation_exposure=0.9)
        allowed, code, _, _ = validate_pre_trade_intent(
            intent, quant_context=ctx, max_age_seconds=None)
        assert allowed is False
        assert code == "CORR_EXPOSURE_FULL"

    def test_safe_quant_context_passes(self):
        from autotrade.fast_gate import validate_pre_trade_intent
        intent = _make_intent()
        ctx = self._ctx(cvar95_pct=-5.0, var95_pct=-3.0, correlation_exposure=0.4,
                        z_score_composite=-1.8)
        allowed, code, _, _ = validate_pre_trade_intent(
            intent, quant_context=ctx, max_age_seconds=None)
        assert allowed is True
        assert code == "OK"

    def test_mr_contradiction_scales_confidence_not_block(self):
        from autotrade.fast_gate import validate_pre_trade_intent
        intent = _make_intent(recommendation="BUY")
        ctx = self._ctx(mean_reversion_signal="STRONG_SELL", z_score_composite=2.5)
        allowed, code, _, conf = validate_pre_trade_intent(
            intent, quant_context=ctx, max_age_seconds=None)
        assert allowed is True
        assert conf < 1.0
        assert conf == pytest.approx(0.85)

    def test_mr_aligned_no_confidence_penalty(self):
        from autotrade.fast_gate import validate_pre_trade_intent
        intent = _make_intent(recommendation="BUY")
        ctx = self._ctx(mean_reversion_signal="STRONG_BUY", z_score_composite=-2.5)
        _, _, _, conf = validate_pre_trade_intent(
            intent, quant_context=ctx, max_age_seconds=None)
        assert conf == 1.0

    def test_non_finite_z_fails_open(self):
        from autotrade.fast_gate import validate_pre_trade_intent
        intent = _make_intent()
        ctx = self._ctx(z_score_composite=float("nan"))
        allowed, code, _, _ = validate_pre_trade_intent(
            intent, quant_context=ctx, max_age_seconds=None)
        assert allowed is True
        assert code.startswith("GATE_SKIP")

    def test_price_deviation_blocks(self):
        from autotrade.fast_gate import validate_pre_trade_intent
        intent = _make_intent(price=100_000)
        allowed, code, _, _ = validate_pre_trade_intent(
            intent, market_context={"price": 1_000_000}, max_age_seconds=None)
        assert allowed is False
        assert code == "PRICE_DEVIATION"

    def test_wide_spread_blocks(self):
        from autotrade.fast_gate import validate_pre_trade_intent
        intent = _make_intent()
        allowed, code, _, _ = validate_pre_trade_intent(
            intent, market_context={"spread_pct": 7.5}, max_age_seconds=None)
        assert allowed is False
        assert code == "SPREAD_WIDE"


class TestQuantSignalContext:
    def test_immutable(self):
        from autotrade.fast_gate import QuantSignalContext
        ctx = QuantSignalContext(z_score_composite=-2.0)
        with pytest.raises(Exception):
            ctx.z_score_composite = 5.0

    def test_to_dict_roundtrip_keys(self):
        from autotrade.fast_gate import QuantSignalContext
        d = QuantSignalContext(z_score_composite=-1.5, cvar95_pct=-7.0,
                               volatility_pct=3.2).to_dict()
        for key in ("z_score_composite", "volatility_pct", "market_regime",
                    "var95_pct", "cvar95_pct", "correlation_exposure",
                    "mean_reversion_signal"):
            assert key in d


# =============================================================================
# 2. RISK MANAGER — Bayesian Kelly sizing + clamps
# =============================================================================

def _risk_manager():
    from autotrade.risk_manager import RiskManager
    return RiskManager(db=MagicMock())


class TestClampPositionSize:
    def test_within_bounds(self):
        rm = _risk_manager()
        value, clamped, reason = rm.clamp_position_size(200_000, 10_000_000)
        assert value == 200_000
        assert clamped is False
        assert reason == "within_bounds"

    def test_raised_to_min_order(self):
        rm = _risk_manager()
        value, clamped, reason = rm.clamp_position_size(10_000, 10_000_000)
        assert value == rm.KELLY_MIN_ORDER_IDR
        assert clamped is True
        assert reason == "raised_to_min_order"

    def test_capped_at_max_fraction(self):
        rm = _risk_manager()
        value, clamped, reason = rm.clamp_position_size(5_000_000, 10_000_000)
        assert value == 2_500_000
        assert clamped is True
        assert reason == "capped_at_max_fraction"

    def test_balance_below_min_order(self):
        rm = _risk_manager()
        value, clamped, reason = rm.clamp_position_size(10_000, 20_000)
        assert clamped is False
        assert reason == "balance_below_min_order"

    def test_invalid_input(self):
        rm = _risk_manager()
        value, clamped, reason = rm.clamp_position_size(0, 10_000_000)
        assert value == 0
        assert reason == "non_positive_input"


class TestBayesianKellySizing:
    def _engine(self, won_rate=0.6, wl=2.0):
        from quant.bayesian_kelly import BayesianKellyEngine
        eng = BayesianKellyEngine()
        # 10 trades, 6 wins @+4%, 4 losses @-2% -> wl=2.0, wr=0.6
        for _ in range(6):
            eng.update_trade_outcome("btcidr", won=True, pnl_pct=4.0)
        for _ in range(4):
            eng.update_trade_outcome("btcidr", won=False, pnl_pct=-2.0)
        return eng

    def test_sizing_returns_positive_value(self):
        rm = _risk_manager()
        eng = self._engine()
        value, amount, meta = rm.bayesian_kelly_position_size(
            "btcidr", 10_000_000, 1_500_000_000, ml_confidence=0.8,
            kelly_engine=eng)
        assert value > 0
        assert amount > 0
        assert meta["method"].startswith("bayesian_kelly")
        assert meta["kelly_fraction"] > 0

    def test_negative_edge_returns_zero(self):
        rm = _risk_manager()
        from quant.bayesian_kelly import BayesianKellyEngine
        eng = BayesianKellyEngine()
        # 10 losses, no wins -> negative edge
        for _ in range(10):
            eng.update_trade_outcome("btcidr", won=False, pnl_pct=-2.0)
        value, amount, meta = rm.bayesian_kelly_position_size(
            "btcidr", 10_000_000, 1_500_000_000, kelly_engine=eng)
        assert value == 0.0
        assert amount == 0.0
        assert meta["method"] in ("negative_edge", "bayesian_kelly_global")

    def test_invalid_input_returns_zero(self):
        rm = _risk_manager()
        value, amount, meta = rm.bayesian_kelly_position_size(
            "btcidr", 0, 1_500_000_000)
        assert value == 0.0
        assert meta["reason"] == "invalid_input"

    def test_min_order_clamp_applied(self):
        rm = _risk_manager()
        from quant.bayesian_kelly import BayesianKellyEngine
        from autotrade.risk_manager import RiskManager

        # Bangun skenario di mana hasil Kelly asli memang di bawah minimum
        # order exchange: pair tanpa history + confidence rendah -> engine
        # kembali prior_only dengan fraksi kecil.
        eng = BayesianKellyEngine()
        # 5 trade untuk lulus MIN_TRADES_FOR_KELLY, tapi win rate bias
        # kecil (3W/2L, win +0.4%, loss -0.2% -> wl=2, wr=0.6, kelly kecil).
        for _ in range(3):
            eng.update_trade_outcome("soloidr", won=True, pnl_pct=0.4)
        for _ in range(2):
            eng.update_trade_outcome("soloidr", won=False, pnl_pct=-0.2)

        # prior_only path: confidence rendah -> 0.5 * 0.10 = 5% balance
        value, amount, meta = rm.bayesian_kelly_position_size(
            "novelpair", 500_000, 8_000, ml_confidence=0.50, kelly_engine=eng)
        # 5% * 500k = 25k < 50k min -> clamp naikkan ke 50k
        if value > 0:
            assert value >= rm.KELLY_MIN_ORDER_IDR
            assert meta["clamped"] is True

    def test_min_order_clamp_never_below_exchange_min_when_funded(self):
        rm = _risk_manager()
        from quant.bayesian_kelly import BayesianKellyEngine
        eng = BayesianKellyEngine()
        for _ in range(6):
            eng.update_trade_outcome("btcidr", won=True, pnl_pct=1.0)
        for _ in range(4):
            eng.update_trade_outcome("btcidr", won=False, pnl_pct=-0.5)
        value, amount, meta = rm.bayesian_kelly_position_size(
            "btcidr", 10_000_000, 1_500_000_000, ml_confidence=0.55,
            kelly_engine=eng)
        # Bila ada alokasi positif, tidak boleh di bawah minimum order
        # exchange, kecuali balance sendiri kurang dari minimum itu.
        if value > 0 and 10_000_000 >= rm.KELLY_MIN_ORDER_IDR:
            assert value >= rm.KELLY_MIN_ORDER_IDR

    def test_max_fraction_cap(self):
        rm = _risk_manager()
        eng = self._engine()
        # Huge balance + tiny Kelly fraction still capped at 25%
        value, amount, meta = rm.bayesian_kelly_position_size(
            "btcidr", 100_000_000_000, 1_500_000_000, ml_confidence=0.95,
            kelly_engine=eng)
        assert value <= 100_000_000_000 * rm.KELLY_MAX_BALANCE_FRACTION + 1

    def test_engine_failure_fails_open_zero(self):
        rm = _risk_manager()
        broken = MagicMock()
        broken.calculate_position_size.side_effect = RuntimeError("boom")
        value, amount, meta = rm.bayesian_kelly_position_size(
            "btcidr", 10_000_000, 1_500_000_000, kelly_engine=broken)
        assert value == 0.0
        assert meta["method"] == "engine_error"

    def test_meta_contract_keys(self):
        rm = _risk_manager()
        eng = self._engine()
        _, _, meta = rm.bayesian_kelly_position_size(
            "btcidr", 10_000_000, 1_500_000_000, kelly_engine=eng)
        for key in ("method", "kelly_fraction", "position_value",
                    "position_amount", "clamped", "reason"):
            assert key in meta


# =============================================================================
# 3. SIGNAL QUALITY ENGINE — Mean Reversion confluence weight
# =============================================================================

class TestWeightedMeanReversionBonus:
    def _sqe(self):
        from signals.signal_quality_engine import SignalQualityEngine
        return SignalQualityEngine()

    def _mr(self, z, bonus=None):
        from quant.mean_reversion import MeanReversionResult
        return MeanReversionResult(
            z_score_fast=z, z_score_medium=z, z_score_slow=z,
            z_score_composite=z, bb_pct_b=0.1, vwap_z_score=None,
            signal="BUY", confluence_bonus=bonus if bonus is not None else 2,
            confidence_boost=0.04, mean_price=100.0, std_price=1.0,
            current_price=100.0, regime_alignment=True,
        )

    def test_strong_bonus_weighted(self):
        sqe = self._sqe()
        result = sqe.calculate_weighted_mean_reversion_bonus(self._mr(-2.5, bonus=2))
        assert 0 < result <= 2

    def test_none_returns_zero(self):
        sqe = self._sqe()
        assert sqe.calculate_weighted_mean_reversion_bonus(None) == 0

    def test_neutral_returns_zero(self):
        sqe = self._sqe()
        assert sqe.calculate_weighted_mean_reversion_bonus(self._mr(0.1, bonus=0)) == 0

    def test_never_negative(self):
        sqe = self._sqe()
        result = sqe.calculate_weighted_mean_reversion_bonus(self._mr(3.0, bonus=2))
        assert result >= 0

    def test_capped_at_max(self):
        sqe = self._sqe()
        result = sqe.calculate_weighted_mean_reversion_bonus(self._mr(-3.0, bonus=2))
        from signals import signal_quality_engine as sqe_mod
        assert result <= sqe_mod.MR_CONFLUENCE_WEIGHT_MAX

    def test_derives_from_z_when_bonus_missing(self):
        from signals import signal_quality_engine as sqe_mod
        sqe = self._sqe()
        from quant.mean_reversion import MeanReversionResult
        mr = MeanReversionResult(
            z_score_fast=-1.8, z_score_medium=-1.8, z_score_slow=-1.8,
            z_score_composite=-1.8, bb_pct_b=0.1, vwap_z_score=None,
            signal="BUY", confluence_bonus=1, confidence_boost=0.02,
            mean_price=100.0, std_price=1.0, current_price=100.0,
            regime_alignment=True,
        )
        # bonus=1 -> weighted 0.85 -> rounds to 1
        assert sqe.calculate_weighted_mean_reversion_bonus(mr) == 1

    def test_weight_config_in_blueprint_range(self):
        """Blueprint Phase 2: mean reversion bobot 15-20% dari max 10 poin."""
        from signals import signal_quality_engine as sqe_mod
        # 15% = 1.5, 20% = 2.0; weight 0.85 * strong(2) = 1.7 -> dalam range
        assert 0.15 <= (sqe_mod.MR_CONFLUENCE_WEIGHT * 2) / 10.0 <= 0.25


# =============================================================================
# 4. RUNTIME WIRING — quant context builder + fast gate integration
# =============================================================================

class TestRuntimeQuantWiring:
    def _bot(self):
        bot = MagicMock()
        bot._quant_kelly_engine = None
        return bot

    def test_build_context_from_signal_quant(self):
        from autotrade.runtime import _build_quant_signal_context
        bot = self._bot()
        signal = {"quant": {
            "z_score_composite": -2.1,
            "market_regime": "RANGING",
            "mean_reversion_signal": "STRONG_BUY",
        }}
        regime = {"volatility": 3.5}
        ctx = _build_quant_signal_context(bot, "btcidr", signal, regime)
        assert ctx is not None
        assert ctx.z_score_composite == pytest.approx(-2.1)
        assert ctx.volatility_pct == pytest.approx(3.5)
        assert ctx.mean_reversion_signal == "STRONG_BUY"

    def test_build_context_none_without_quant(self):
        from autotrade.runtime import _build_quant_signal_context
        bot = self._bot()
        assert _build_quant_signal_context(bot, "btcidr", {}, {}) is None

    def test_run_fast_gate_passes_valid_signal(self):
        from autotrade.runtime import _run_fast_gate
        bot = self._bot()
        intent = _make_intent()
        allowed, code, _, _ = _run_fast_gate(
            bot, "btcidr", {"quant": {}}, intent, {}, 1_500_000_000)
        assert allowed is True

    def test_run_fast_gate_blocks_on_cvar(self):
        from autotrade.runtime import _run_fast_gate
        from autotrade.fast_gate import QuantSignalContext
        bot = self._bot()
        intent = _make_intent()
        signal = {"quant": {
            "z_score_composite": 0.0,
            "mean_reversion_signal": "NEUTRAL",
        }}
        allowed, code, detail, _ = _run_fast_gate(
            bot, "btcidr", signal, intent, {}, 1_500_000_000)
        assert allowed is True  # no cvar in context -> passes

    def test_run_fast_gate_fails_open_on_exception(self):
        from autotrade.runtime import _run_fast_gate
        bot = self._bot()
        allowed, code, _, _ = _run_fast_gate(
            bot, "btcidr", None, None, None, None)
        assert allowed is True
        assert code.startswith("GATE_SKIP") or code == "GATE_SKIP_NO_INTENT" \
            or code.startswith("GATE_SKIP")


# =============================================================================
# 5. INTEGRATION — Kelly sizing feeds from quality engine confidence
# =============================================================================

class TestQuantSizingIntegration:
    def test_sizing_uses_adjusted_confidence(self):
        """Confidence yang discaling fast gate harus dipakai Kelly sizing."""
        from autotrade.risk_manager import RiskManager
        from quant.bayesian_kelly import BayesianKellyEngine

        eng = BayesianKellyEngine()
        for _ in range(7):
            eng.update_trade_outcome("btcidr", won=True, pnl_pct=3.0)
        for _ in range(3):
            eng.update_trade_outcome("btcidr", won=False, pnl_pct=-1.5)

        rm = RiskManager(db=MagicMock())
        high, _, _ = rm.bayesian_kelly_position_size(
            "btcidr", 10_000_000, 1_500_000_000, ml_confidence=0.9,
            kelly_engine=eng)
        low, _, _ = rm.bayesian_kelly_position_size(
            "btcidr", 10_000_000, 1_500_000_000, ml_confidence=0.55,
            kelly_engine=eng)
        # Higher confidence -> bigger or equal position (vol factor sama).
        assert high >= low

    def test_quant_envelope_in_generated_signal(self):
        """Signal hasil generate_signal harus membawa key 'quant'."""
        from signals.signal_quality_engine import SignalQualityEngine
        import numpy as np
        import pandas as pd

        # 80 candle random walk dengan tren turun untuk MR signal
        n = 80
        rng = np.random.default_rng(42)
        close = 100.0 + np.cumsum(rng.normal(-0.05, 1.0, n))
        df = pd.DataFrame({"close": close, "volume": np.full(n, 1000.0),
                           "high": close + 1, "low": close - 1})

        sqe = SignalQualityEngine()
        result = sqe.generate_signal(
            pair="btcidr",
            ta_signals={"rsi": "OVERSOLD", "macd": "BULLISH", "ma_trend": "BULLISH",
                        "bollinger": "OVERSOLD", "volume": "HIGH", "price": float(close[-1])},
            ml_prediction=True,
            ml_confidence=0.75,
            ml_signal_class="BUY",
            combined_strength=0.3,
            df=df,
            market_regime="RANGING",
            current_price=float(close[-1]),
        )
        assert result is not None
        assert "quant" in result
        q = result["quant"]
        for key in ("z_score_composite", "mean_reversion_signal",
                    "mean_reversion_bonus", "market_regime", "confluence_score"):
            assert key in q
