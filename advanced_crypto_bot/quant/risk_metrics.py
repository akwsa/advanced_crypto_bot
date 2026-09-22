#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# Tujuan: Risk metrics kuantitatif: CAGR, VaR (Historical/Parametric/Monte Carlo), CVaR.
# Caller: quant/quant_commands.py, bot.py /quant_risk command.
# Dependensi: numpy, scipy.stats.
# Main Functions: class RiskMetrics, RiskResult.
# Side Effects: none; pure computation only.
"""
Risk Metrics Engine
====================
Implementasi metrik risiko kuantitatif standar industri:

1. CAGR (Compound Annual Growth Rate)
   - Mengukur pertumbuhan tahunan majemuk dari equity curve
   - Formula: (end_value / start_value)^(1/years) - 1

2. Value at Risk — 3 metode:
   a. Historical VaR  : percentile dari distribusi return historis
   b. Parametric VaR  : asumsi distribusi normal (mean & std)
   c. Monte Carlo VaR : simulasi 10.000 path return acak

3. CVaR / Expected Shortfall (ES)
   - Rata-rata kerugian yang melebihi VaR threshold
   - Lebih konservatif dari VaR karena memperhitungkan tail risk

Confidence levels yang didukung: 90%, 95%, 99%

Usage:
    from quant.risk_metrics import RiskMetrics

    rm = RiskMetrics()
    result = rm.calculate(returns_pct=[3.5, -1.2, 2.1, -0.8, ...], confidence=0.95)

    result.cagr              # float, e.g. 0.18 = 18% per tahun
    result.var_historical    # float, e.g. -2.5 = kerugian 2.5%
    result.var_parametric    # float
    result.var_montecarlo    # float
    result.cvar              # float, e.g. -3.8 = expected loss jika VaR terlampaui
    result.summary_text()    # string untuk Telegram
"""

import logging
import math
from dataclasses import dataclass
from statistics import NormalDist
from typing import List, Optional

import numpy as np
try:
    from scipy import stats
except (ImportError, ModuleNotFoundError):
    stats = None

logger = logging.getLogger("crypto_bot")

# Minimum data untuk hasil yang reliable
MIN_RETURNS = 20
# Jumlah simulasi Monte Carlo
MC_SIMULATIONS = 10_000
# Periode trading per tahun (crypto 24/7, ~4 trade/hari)
TRADES_PER_YEAR = 365 * 4
STANDARD_NORMAL = NormalDist()


def _skew(values: np.ndarray) -> float:
    if stats is not None:
        return float(stats.skew(values))
    mean = float(np.mean(values))
    std = float(np.std(values, ddof=0))
    if std <= 0:
        return 0.0
    return float(np.mean(((values - mean) / std) ** 3))


def _kurtosis(values: np.ndarray) -> float:
    if stats is not None:
        return float(stats.kurtosis(values))
    mean = float(np.mean(values))
    std = float(np.std(values, ddof=0))
    if std <= 0:
        return 0.0
    return float(np.mean(((values - mean) / std) ** 4) - 3)


def _norm_ppf(probability: float) -> float:
    if stats is not None:
        return float(stats.norm.ppf(probability))
    return float(STANDARD_NORMAL.inv_cdf(probability))


def _norm_pdf(value: float) -> float:
    if stats is not None:
        return float(stats.norm.pdf(value))
    return float(math.exp(-0.5 * value * value) / math.sqrt(2 * math.pi))


@dataclass
class RiskResult:
    """Hasil lengkap risk metrics calculation."""
    # CAGR
    cagr: float                  # Compound Annual Growth Rate (0.18 = 18%/tahun)
    total_return_pct: float      # Total return keseluruhan (%)
    n_trades: int                # Jumlah trade yang dianalisis
    years_equivalent: float      # Ekuivalen berapa tahun trading

    # VaR (semua dalam %, negatif = kerugian)
    confidence: float            # Confidence level (0.95 = 95%)
    var_historical: float        # Historical VaR
    var_parametric: float        # Parametric VaR (normal distribution)
    var_montecarlo: float        # Monte Carlo VaR

    # CVaR / Expected Shortfall
    cvar_historical: float       # CVaR dari historical distribution
    cvar_parametric: float       # CVaR dari parametric distribution

    # Distribusi return
    mean_return: float           # Rata-rata return per trade (%)
    std_return: float            # Standar deviasi return (%)
    skewness: float              # Skewness distribusi return
    kurtosis: float              # Excess kurtosis (0 = normal)

    def summary_text(self) -> str:
        """Format ringkas untuk Telegram."""
        conf_pct = int(self.confidence * 100)
        return (
            f"📊 *Risk Metrics*\n"
            f"━━━━━━━━━━━━━━━━━━━━━━\n"
            f"📈 CAGR: `{self.cagr*100:+.2f}%/tahun`\n"
            f"📉 Total Return: `{self.total_return_pct:+.2f}%`\n"
            f"🔢 Trades: `{self.n_trades}` (~{self.years_equivalent:.2f} tahun)\n"
            f"━━━━━━━━━━━━━━━━━━━━━━\n"
            f"⚠️ *VaR ({conf_pct}% confidence)*\n"
            f"  Historical : `{self.var_historical:.2f}%`\n"
            f"  Parametric : `{self.var_parametric:.2f}%`\n"
            f"  Monte Carlo: `{self.var_montecarlo:.2f}%`\n"
            f"━━━━━━━━━━━━━━━━━━━━━━\n"
            f"🔴 *CVaR / Expected Shortfall*\n"
            f"  Historical : `{self.cvar_historical:.2f}%`\n"
            f"  Parametric : `{self.cvar_parametric:.2f}%`\n"
            f"━━━━━━━━━━━━━━━━━━━━━━\n"
            f"📐 Distribusi Return\n"
            f"  Mean: `{self.mean_return:+.3f}%` | Std: `{self.std_return:.3f}%`\n"
            f"  Skew: `{self.skewness:+.2f}` | Kurt: `{self.kurtosis:+.2f}`\n"
        )

    def to_dict(self) -> dict:
        return {
            "cagr": round(self.cagr, 6),
            "total_return_pct": round(self.total_return_pct, 4),
            "n_trades": self.n_trades,
            "years_equivalent": round(self.years_equivalent, 4),
            "confidence": self.confidence,
            "var_historical": round(self.var_historical, 4),
            "var_parametric": round(self.var_parametric, 4),
            "var_montecarlo": round(self.var_montecarlo, 4),
            "cvar_historical": round(self.cvar_historical, 4),
            "cvar_parametric": round(self.cvar_parametric, 4),
            "mean_return": round(self.mean_return, 4),
            "std_return": round(self.std_return, 4),
            "skewness": round(self.skewness, 4),
            "kurtosis": round(self.kurtosis, 4),
        }


class RiskMetrics:
    """
    Engine untuk menghitung CAGR, VaR (3 metode), dan CVaR
    dari riwayat return trading.
    """

    def __init__(self, mc_simulations: int = MC_SIMULATIONS, random_seed: int = 42):
        self.mc_simulations = mc_simulations
        self.rng = np.random.default_rng(random_seed)
        logger.info("✅ RiskMetrics Engine initialized")

    def calculate(
        self,
        returns_pct: List[float],
        confidence: float = 0.95,
        initial_balance: float = 10_000_000,
    ) -> Optional["RiskResult"]:
        """
        Hitung semua risk metrics dari list return per trade.

        Args:
            returns_pct : List return per trade dalam persen, e.g. [3.5, -1.2, 2.1]
            confidence  : Confidence level VaR/CVaR, default 0.95 (95%)
            initial_balance: Modal awal untuk CAGR calculation

        Returns:
            RiskResult atau None jika data tidak cukup
        """
        if not returns_pct or len(returns_pct) < MIN_RETURNS:
            logger.debug(f"[RISK] Insufficient data: {len(returns_pct) if returns_pct else 0} < {MIN_RETURNS}")
            return None

        r = np.array(returns_pct, dtype=float)
        n = len(r)

        # ── Distribusi dasar ──────────────────────────────────────────────
        mean_r = float(np.mean(r))
        std_r = float(np.std(r, ddof=1))
        skew = _skew(r)
        kurt = _kurtosis(r)  # excess kurtosis

        # ── CAGR ─────────────────────────────────────────────────────────
        # Bangun equity curve dari return
        equity = initial_balance
        for ret in r:
            equity *= (1 + ret / 100)

        total_return_pct = (equity / initial_balance - 1) * 100
        years_equiv = n / TRADES_PER_YEAR

        if years_equiv > 0 and equity > 0:
            cagr = (equity / initial_balance) ** (1 / years_equiv) - 1
        else:
            cagr = 0.0

        # ── VaR Historical ───────────────────────────────────────────────
        # Percentile ke-(1-confidence) dari distribusi return historis
        var_hist = float(np.percentile(r, (1 - confidence) * 100))

        # ── VaR Parametric ───────────────────────────────────────────────
        # Asumsi distribusi normal: mean - z * std
        z_score = _norm_ppf(1 - confidence)
        var_param = float(mean_r + z_score * std_r)

        # ── VaR Monte Carlo ──────────────────────────────────────────────
        # Simulasi return berdasarkan distribusi empiris (bootstrap)
        mc_returns = self.rng.choice(r, size=self.mc_simulations, replace=True)
        var_mc = float(np.percentile(mc_returns, (1 - confidence) * 100))

        # ── CVaR Historical ──────────────────────────────────────────────
        # Rata-rata return yang lebih buruk dari VaR historical
        tail_hist = r[r <= var_hist]
        cvar_hist = float(np.mean(tail_hist)) if len(tail_hist) > 0 else var_hist

        # ── CVaR Parametric ──────────────────────────────────────────────
        # E[X | X <= VaR] untuk distribusi normal
        # = mean - std * phi(z) / (1 - confidence)
        phi_z = _norm_pdf(z_score)
        cvar_param = float(mean_r - std_r * phi_z / (1 - confidence))

        result = RiskResult(
            cagr=cagr,
            total_return_pct=total_return_pct,
            n_trades=n,
            years_equivalent=years_equiv,
            confidence=confidence,
            var_historical=var_hist,
            var_parametric=var_param,
            var_montecarlo=var_mc,
            cvar_historical=cvar_hist,
            cvar_parametric=cvar_param,
            mean_return=mean_r,
            std_return=std_r,
            skewness=skew,
            kurtosis=kurt,
        )

        logger.info(
            f"📊 [RISK] CAGR={cagr*100:+.2f}% | "
            f"VaR({int(confidence*100)}%)=hist:{var_hist:.2f}% "
            f"param:{var_param:.2f}% mc:{var_mc:.2f}% | "
            f"CVaR={cvar_hist:.2f}%"
        )
        return result

    def calculate_from_trades(
        self,
        trade_history: List[dict],
        confidence: float = 0.95,
    ) -> Optional[RiskResult]:
        """
        Hitung dari list trade dict (format database bot).
        Expects key 'profit_loss_pct' atau ('profit_loss' + 'total').
        """
        returns = []
        for t in trade_history:
            pct = t.get("profit_loss_pct")
            if pct is not None:
                returns.append(float(pct))
            elif t.get("profit_loss") is not None and t.get("total"):
                total = t["total"]
                if total > 0:
                    returns.append(float(t["profit_loss"] / total * 100))

        initial = trade_history[0].get("total", 10_000_000) if trade_history else 10_000_000
        return self.calculate(returns, confidence=confidence, initial_balance=initial)
