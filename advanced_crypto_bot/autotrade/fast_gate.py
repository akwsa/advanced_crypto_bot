# Tujuan: TypeSafe pre-trade guardrail (System 1 fast gate, < 50ms, no LLM).
# Caller: autotrade/runtime.py _check_trading_opportunity_locked, bot.py signal queue worker.
# Dependensi: autotrade.contracts.TradeIntent (frozen dataclass), quant risk metrics (lazy).
# Main Functions: QuantSignalContext, validate_pre_trade_intent.
# Side Effects: none; pure validation only (no DB writes, no network).
"""TypeSafe pre-trade guardrail ("Jev Gate").

Implementasi Phase 1 dari docs/HERMES_HANDOVER.md: kontrak bertipe +
validasi deterministik sebelum order ditembakkan (< 50ms, no LLM).

Komponen:
- ``QuantSignalContext``  : frozen dataclass konteks kuantitatif sinyal
  (Z-score composite, Hurst, GARCH volatility, regime, VaR/CVaR).
- ``validate_pre_trade_intent`` : fungsi murni yang mengembalikan
  ``(allowed, reason_code, detail, confidence_adjusted)``.

Kontrak: TIDAK boleh memblokir trade pada mode error/kosong (fail-open).
Semua error dibungkus try/except dan dikembalikan sebagai ``True`` dengan
reason ``GATE_SKIP_*``. Bot tetap menggunakan gate existing-nya.
"""
from __future__ import annotations

import logging
import math
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, Optional, Tuple

logger = logging.getLogger(__name__)

CONTRACT_VERSION = 1

# ---------------------------------------------------------------------------
# Thresholds (dari blueprint Section 2: Komponen 1)
# ---------------------------------------------------------------------------
CVAR95_MAX_LOSS_PCT = -8.0     # Tolak jika CVaR95 < -8%
CORR_EXPOSURE_MAX = 0.80       # Tolak jika eksposur aset ber-korelasi > 0.8
SIGNAL_MAX_AGE_SECONDS = 900   # 15 menit staleness window
PRICE_DEVIATION_MAX_PCT = 25.0 # Harga sinyal vs harga pasar (anti spoof)
VAR95_MAX_LOSS_PCT = -12.0     # Tolak jika VaR95 < -12%


@dataclass(frozen=True)
class QuantSignalContext:
    """Konteks kuantitatif sinyal hasil perhitungan quant (immutable contract)."""
    z_score_composite: float = 0.0
    hurst_exponent: Optional[float] = None
    volatility_pct: Optional[float] = None       # GARCH(1,1) / ATR %
    market_regime: str = "UNKNOWN"
    var95_pct: Optional[float] = None            # historical VaR (%)
    cvar95_pct: Optional[float] = None           # historical CVaR (%)
    correlation_exposure: Optional[float] = None # portfolio heat 0..1
    mean_reversion_signal: str = "NEUTRAL"
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "z_score_composite": round(self.z_score_composite, 4),
            "hurst_exponent": None if self.hurst_exponent is None else round(self.hurst_exponent, 4),
            "volatility_pct": None if self.volatility_pct is None else round(self.volatility_pct, 4),
            "market_regime": self.market_regime,
            "var95_pct": None if self.var95_pct is None else round(self.var95_pct, 4),
            "cvar95_pct": None if self.cvar95_pct is None else round(self.cvar95_pct, 4),
            "correlation_exposure": None if self.correlation_exposure is None else round(self.correlation_exposure, 4),
            "mean_reversion_signal": self.mean_reversion_signal,
        }


def _is_finite(*values: Optional[float]) -> bool:
    return all(v is not None and math.isfinite(float(v)) for v in values)


def _to_float(value: Any) -> Optional[float]:
    """Best-effort float coercion; None on failure."""
    try:
        result = float(value)
        return result if math.isfinite(result) else None
    except (TypeError, ValueError):
        return None


def _dict_validate(payload: Dict[str, Any], max_age_seconds: Optional[float]) -> Optional[str]:
    """Validate a plain-dict intent (mirrors TradeIntent.validate).

    Sinyal dict dari runtime test/legacy sering tidak membawa ``created_at``.
    Bila timestamp tidak ada, pemeriksaan staleness/future di-skip (fail-open)
    daripada menolak sinyal yang sebenarnya valid — contract utama
    (pair/recommendation/price) tetap divalidasi penuh.
    """
    if not payload.get("pair"):
        return "MISSING_PAIR"
    rec = str(payload.get("recommendation") or "").upper()
    if rec not in {"BUY", "STRONG_BUY", "SELL", "STRONG_SELL"}:
        return "INVALID_RECOMMENDATION"
    price = _to_float(payload.get("price"))
    if price is None or price <= 0:
        return "INVALID_PRICE"
    # Konfidensi: utamakan ml_confidence (sama dengan TradeIntent.from_signal).
    confidence = _to_float(payload.get("ml_confidence")) or _to_float(payload.get("confidence"))
    if confidence is None:
        return "NON_FINITE_NUMERIC"
    created_at = _to_float(payload.get("created_at"))
    if created_at is None:
        # Tidak ada timestamp -> tidak bisa dinilai staleness-nya; fail-open.
        return None
    if created_at > datetime.now(timezone.utc).timestamp() + 60:
        return "FUTURE_SIGNAL"
    if max_age_seconds is not None:
        age = datetime.now(timezone.utc).timestamp() - created_at
        if age > max_age_seconds:
            return "STALE_SIGNAL"
    return None


def validate_pre_trade_intent(
    intent: Any,
    market_context: Optional[Dict[str, Any]] = None,
    quant_context: Optional[QuantSignalContext] = None,
    max_age_seconds: Optional[float] = SIGNAL_MAX_AGE_SECONDS,
) -> Tuple[bool, str, str, float]:
    """Validate a TradeIntent against market + quant context (pure function).

    Args:
        intent: ``autotrade.contracts.TradeIntent`` (frozen dataclass). A plain
            dict is accepted for convenience and normalised here.
        market_context: dict pasar bebas: ``{"price": float, "spread_pct": float,
            "best_bid": float, "best_ask": float, "balance": float}``.
        quant_context: ``QuantSignalContext`` (opsional; VaR/CVaR & correlation
            gate hanya aktif bila disertakan).
        max_age_seconds: staleness window. ``None`` = skip staleness check.

    Returns:
        ``(allowed, reason_code, detail, confidence_adjusted)``

        - ``allowed``          : bool — True = lanjut, False = tolak.
        - ``reason_code``      : kode machine-readable (mis. ``OK``,
          ``INVALID_PRICE``, ``CVAR_TOO_HIGH``).
        - ``detail``           : pesan human-readable untuk log/Telegram.
        - ``confidence_adjusted``: faktor skala 0.0-1.0 untuk konfidensi sinyal
          (mean reversion confluence alignment). 1.0 = tidak ada perubahan.
    """
    # ---------------------------------------------------------- fail-open
    try:
        if intent is None:
            return True, "GATE_SKIP_NO_INTENT", "Fast gate skipped: no intent", 1.0

        # Normalisasi input: TradeIntent dataclass atau dict polos.
        if hasattr(intent, "validate") and hasattr(intent, "to_dict"):
            payload = intent.to_dict()
        elif isinstance(intent, dict):
            payload = dict(intent)
        else:
            return True, "GATE_SKIP_INTENT_TYPE", "Fast gate skipped: unsupported intent type", 1.0

        ctx = dict(market_context or {})
        qtx = quant_context

        # -------------------------------------------------- 1. contract validate
        validator = getattr(intent, "validate", None)
        if callable(validator):
            invalid = validator(max_age_seconds=max_age_seconds)
        else:
            invalid = _dict_validate(payload, max_age_seconds)
        # Legacy/test sinyal sering tidak membawa created_at; TradeIntent
        # mengisi 0.0 -> terbaca sebagai sinyal sangat lama (STALE_SIGNAL).
        # Bila timestamp benar-benar tidak ada, staleness tidak dapat dinilai
        # -> fail-open (hanya contract utama yang mengikat).
        if invalid == "STALE_SIGNAL" and (float(payload.get("created_at") or 0.0) or 0.0) <= 0.0:
            invalid = None
        if invalid:
            return False, invalid, f"Contract validation failed: {invalid}", 1.0

        pair = str(payload.get("pair") or "?")
        rec = str(payload.get("recommendation") or "").upper()
        signal_price = float(payload.get("price") or 0.0)

        # -------------------------------------------------- 2. price sanity
        market_price = _to_float(ctx.get("price"))
        if market_price and market_price > 0 and signal_price > 0:
            dev_pct = abs(market_price - signal_price) / market_price * 100.0
            if dev_pct > PRICE_DEVIATION_MAX_PCT:
                detail = (f"{pair}: signal price {signal_price:,.0f} deviates "
                          f"{dev_pct:.1f}% from market price {market_price:,.0f}")
                logger.warning(f"🛡️ [FAST GATE] PRICE_DEVIATION {detail}")
                return False, "PRICE_DEVIATION", detail, 1.0

        # -------------------------------------------------- 3. spread sanity
        spread_pct = _to_float(ctx.get("spread_pct"))
        if spread_pct is not None and spread_pct > 5.0:
            detail = f"{pair}: spread {spread_pct:.2f}% terlalu lebar untuk eksekusi"
            logger.warning(f"🛡️ [FAST GATE] SPREAD_WIDE {detail}")
            return False, "SPREAD_WIDE", detail, 1.0

        # -------------------------------------------------- 4. quant gates
        confidence_adjusted = 1.0
        if qtx is not None:
            # 4a. NaN / non-finite guard pada konteks quant itu sendiri
            if not _is_finite(qtx.z_score_composite):
                return True, "GATE_SKIP_NON_FINITE", "Fast gate skipped: non-finite quant context", 1.0

            # 4b. VaR/CVaR gate (blueprint: tolak jika CVaR95 < -8%)
            if _is_finite(qtx.cvar95_pct) and float(qtx.cvar95_pct) < CVAR95_MAX_LOSS_PCT:
                detail = (f"{pair}: CVaR95={float(qtx.cvar95_pct):.2f}% < "
                          f"batas {CVAR95_MAX_LOSS_PCT:.1f}% — tail risk terlalu tinggi")
                logger.warning(f"🛡️ [FAST GATE] CVAR_TOO_HIGH {detail}")
                return False, "CVAR_TOO_HIGH", detail, 1.0

            if _is_finite(qtx.var95_pct) and float(qtx.var95_pct) < VAR95_MAX_LOSS_PCT:
                detail = (f"{pair}: VaR95={float(qtx.var95_pct):.2f}% < batas "
                          f"{VAR95_MAX_LOSS_PCT:.1f}% — risiko historis terlalu tinggi")
                logger.warning(f"🛡️ [FAST GATE] VAR_TOO_HIGH {detail}")
                return False, "VAR_TOO_HIGH", detail, 1.0

            # 4c. Portfolio heat / correlation gate (> 0.8 sudah penuh)
            if _is_finite(qtx.correlation_exposure) and float(qtx.correlation_exposure) > CORR_EXPOSURE_MAX:
                detail = (f"{pair}: correlation exposure={float(qtx.correlation_exposure):.2f} > "
                          f"{CORR_EXPOSURE_MAX:.2f} — eksposur aset ber-korelasi sudah penuh")
                logger.warning(f"🛡️ [FAST GATE] CORR_EXPOSURE_FULL {detail}")
                return False, "CORR_EXPOSURE_FULL", detail, 1.0

            # 4d. Mean reversion confluence alignment (non-blocking, adjust confidence)
            # Buy-side signal dengan MR SELL/STRONG_SELL = kontradiksi z-score.
            mr_sig = str(qtx.mean_reversion_signal or "NEUTRAL").upper()
            is_buy = rec in ("BUY", "STRONG_BUY")
            is_sell = rec in ("SELL", "STRONG_SELL")
            if (is_buy and mr_sig in ("SELL", "STRONG_SELL")) or \
               (is_sell and mr_sig in ("BUY", "STRONG_BUY")):
                confidence_adjusted = 0.85
                logger.info(
                    f"📉 [FAST GATE] {pair}: MR confluence kontradiksi "
                    f"(trade={rec}, mr={mr_sig}) → confidence x{confidence_adjusted:.2f}"
                )

        detail = f"{pair}: OK (rec={rec}, price={signal_price:,.0f})"
        return True, "OK", detail, confidence_adjusted

    except Exception as exc:  # fail-open: never block on gate error
        logger.debug(f"[FAST GATE] Validation error (fail-open): {exc}")
        return True, "GATE_SKIP_ERROR", f"Fast gate skipped: {exc}", 1.0
