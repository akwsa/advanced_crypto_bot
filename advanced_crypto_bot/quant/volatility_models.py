#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# Tujuan: Model volatilitas GARCH(1,1) dan ARCH test untuk volatility clustering.
# Caller: quant/quant_commands.py, bot.py /quant_volatility command.
# Dependensi: numpy, scipy.stats.
# Main Functions: class GARCHModel, GARCHResult, VolatilityResult.
# Side Effects: none; pure computation only.
"""
Volatility Models — GARCH(1,1) & ARCH Test
============================================
Implementasi model volatilitas tanpa dependensi library eksternal berat
(arch/statsmodels tidak wajib ada di venv).

1. GARCH(1,1) — Generalized AutoRegressive Conditional Heteroskedasticity
   - Model volatilitas paling populer di keuangan
   - sigma²_t = omega + alpha * epsilon²_(t-1) + beta * sigma²_(t-1)
   - Parameter diestimasi via MLE (Maximum Likelihood Estimation)
   - Menghasilkan: conditional volatility series, forecast, persistence

2. ARCH Test (Engle's LM Test)
   - Menguji apakah ada volatility clustering dalam return series
   - H0: tidak ada ARCH effect (volatilitas konstan)
   - H1: ada ARCH effect (volatilitas berkluster)
   - Output: test statistic, p-value, kesimpulan

Interpretasi GARCH:
   - alpha + beta < 1 → model stasioner (volatilitas mean-reverting)
   - alpha + beta ≈ 1 → IGARCH (volatilitas sangat persisten)
   - alpha tinggi → volatilitas reaktif terhadap shock baru
   - beta tinggi  → volatilitas persisten (ingatan panjang)

Usage:
    from quant.volatility_models import GARCHModel

    garch = GARCHModel()
    result = garch.fit(returns_pct=[3.5, -1.2, 2.1, -0.8, ...])

    result.conditional_vol      # array volatilitas kondisional
    result.forecast_vol_1d      # forecast volatilitas 1 periode ke depan
    result.persistence          # alpha + beta
    result.arch_test_pvalue     # p-value ARCH test
    result.has_clustering       # True jika ada volatility clustering
    result.summary_text()       # string untuk Telegram
"""

import logging
from statistics import NormalDist
from dataclasses import dataclass, field
from typing import List, Optional

import numpy as np
try:
    from scipy import stats
except (ImportError, ModuleNotFoundError):
    stats = None

try:
    from scipy.optimize import minimize
except (ImportError, ModuleNotFoundError):
    minimize = None

logger = logging.getLogger("crypto_bot")

MIN_RETURNS = 30  # Minimum data untuk GARCH yang reliable
ARCH_LAGS = 5     # Jumlah lag untuk ARCH test
STANDARD_NORMAL = NormalDist()


def _chi2_sf(value: float, df: int) -> float:
    """Chi-square survival function with a SciPy-free Wilson-Hilferty fallback."""
    if stats is not None:
        return float(1 - stats.chi2.cdf(value, df=df))
    if value <= 0 or df <= 0:
        return 1.0
    z = ((value / df) ** (1 / 3) - (1 - 2 / (9 * df))) / np.sqrt(2 / (9 * df))
    return float(max(0.0, min(1.0, 1 - STANDARD_NORMAL.cdf(z))))


@dataclass
class GARCHResult:
    """Hasil fitting GARCH(1,1)."""
    # Parameter GARCH(1,1): sigma²_t = omega + alpha*eps²_(t-1) + beta*sigma²_(t-1)
    omega: float             # Konstanta (long-run variance component)
    alpha: float             # Koefisien ARCH (reaktivitas terhadap shock)
    beta: float              # Koefisien GARCH (persistensi volatilitas)
    persistence: float       # alpha + beta (< 1 = stasioner)
    long_run_vol: float      # Volatilitas jangka panjang (annualized %)

    # Conditional volatility series
    conditional_vol: List[float] = field(default_factory=list)  # Per-trade vol (%)
    current_vol: float = 0.0        # Volatilitas kondisional saat ini (%)
    forecast_vol_1d: float = 0.0    # Forecast 1 periode ke depan (%)
    forecast_vol_5d: float = 0.0    # Forecast 5 periode ke depan (%)

    # ARCH Test (Engle's LM Test)
    arch_test_stat: float = 0.0     # LM test statistic
    arch_test_pvalue: float = 1.0   # p-value (< 0.05 = ada clustering)
    has_clustering: bool = False    # True jika p-value < 0.05

    # Fit quality
    log_likelihood: float = 0.0
    n_obs: int = 0
    converged: bool = False

    @property
    def is_stationary(self) -> bool:
        return self.persistence < 1.0

    @property
    def regime(self) -> str:
        """Klasifikasi regime volatilitas."""
        if self.current_vol < 1.0:
            return "LOW"
        elif self.current_vol < 3.0:
            return "MEDIUM"
        elif self.current_vol < 6.0:
            return "HIGH"
        return "EXTREME"

    def summary_text(self) -> str:
        clustering_str = "✅ Ada (p={:.4f})".format(self.arch_test_pvalue) if self.has_clustering \
            else "❌ Tidak (p={:.4f})".format(self.arch_test_pvalue)
        stationary_str = "✅ Stasioner" if self.is_stationary else "⚠️ Non-stasioner (IGARCH)"
        return (
            f"📊 *GARCH(1,1) Volatility Model*\n"
            f"━━━━━━━━━━━━━━━━━━━━━━\n"
            f"🔧 *Parameter*\n"
            f"  ω (omega) : `{self.omega:.6f}`\n"
            f"  α (alpha) : `{self.alpha:.4f}` ← reaktivitas shock\n"
            f"  β (beta)  : `{self.beta:.4f}` ← persistensi\n"
            f"  α+β       : `{self.persistence:.4f}` — {stationary_str}\n"
            f"━━━━━━━━━━━━━━━━━━━━━━\n"
            f"📈 *Volatilitas*\n"
            f"  Saat ini  : `{self.current_vol:.3f}%` [{self.regime}]\n"
            f"  Forecast +1: `{self.forecast_vol_1d:.3f}%`\n"
            f"  Forecast +5: `{self.forecast_vol_5d:.3f}%`\n"
            f"  Long-run  : `{self.long_run_vol:.3f}%`\n"
            f"━━━━━━━━━━━━━━━━━━━━━━\n"
            f"🧪 *ARCH Test (Volatility Clustering)*\n"
            f"  {clustering_str}\n"
            f"  Observasi : `{self.n_obs}`\n"
            f"  Converged : {'✅' if self.converged else '⚠️'}\n"
        )

    def to_dict(self) -> dict:
        return {
            "omega": round(self.omega, 8),
            "alpha": round(self.alpha, 6),
            "beta": round(self.beta, 6),
            "persistence": round(self.persistence, 6),
            "long_run_vol": round(self.long_run_vol, 4),
            "current_vol": round(self.current_vol, 4),
            "forecast_vol_1d": round(self.forecast_vol_1d, 4),
            "forecast_vol_5d": round(self.forecast_vol_5d, 4),
            "arch_test_stat": round(self.arch_test_stat, 4),
            "arch_test_pvalue": round(self.arch_test_pvalue, 6),
            "has_clustering": self.has_clustering,
            "is_stationary": self.is_stationary,
            "regime": self.regime,
            "converged": self.converged,
            "n_obs": self.n_obs,
        }


class GARCHModel:
    """
    GARCH(1,1) model dengan MLE estimation dan ARCH test.
    Implementasi pure numpy — tidak butuh library arch/statsmodels.
    """

    def __init__(self):
        logger.info("✅ GARCH(1,1) Model initialized")

    def fit(self, returns_pct: List[float]) -> Optional[GARCHResult]:
        """
        Fit GARCH(1,1) ke data return dan jalankan ARCH test.

        Args:
            returns_pct: List return per trade dalam persen

        Returns:
            GARCHResult atau None jika data tidak cukup
        """
        if not returns_pct or len(returns_pct) < MIN_RETURNS:
            logger.debug(f"[GARCH] Insufficient data: {len(returns_pct) if returns_pct else 0}")
            return None

        r = np.array(returns_pct, dtype=float)
        n = len(r)

        # Demeaned returns (GARCH bekerja pada residual)
        eps = r - np.mean(r)

        # ── ARCH Test (Engle's LM Test) ───────────────────────────────────
        arch_stat, arch_pval = self._arch_test(eps, lags=ARCH_LAGS)
        has_clustering = arch_pval < 0.05

        # ── Fit GARCH(1,1) via MLE ────────────────────────────────────────
        omega, alpha, beta, log_lik, converged = self._fit_garch(eps)

        # ── Compute conditional variance series ───────────────────────────
        sigma2 = self._compute_conditional_variance(eps, omega, alpha, beta)
        cond_vol = np.sqrt(np.maximum(sigma2, 1e-10))  # dalam satuan return (%)

        # ── Forecast ──────────────────────────────────────────────────────
        # 1-step ahead: sigma²_(T+1) = omega + alpha*eps²_T + beta*sigma²_T
        sigma2_next = omega + alpha * eps[-1] ** 2 + beta * sigma2[-1]
        forecast_1d = float(np.sqrt(max(sigma2_next, 1e-10)))

        # h-step ahead: sigma²_(T+h) = long_run_var + (alpha+beta)^(h-1) * (sigma²_(T+1) - long_run_var)
        persistence = alpha + beta
        long_run_var = omega / max(1 - persistence, 1e-8) if persistence < 1 else float(np.var(eps))
        sigma2_5d = long_run_var + (persistence ** 4) * (sigma2_next - long_run_var)
        forecast_5d = float(np.sqrt(max(sigma2_5d, 1e-10)))

        long_run_vol = float(np.sqrt(max(long_run_var, 1e-10)))

        result = GARCHResult(
            omega=float(omega),
            alpha=float(alpha),
            beta=float(beta),
            persistence=float(persistence),
            long_run_vol=long_run_vol,
            conditional_vol=cond_vol.tolist(),
            current_vol=float(cond_vol[-1]),
            forecast_vol_1d=forecast_1d,
            forecast_vol_5d=forecast_5d,
            arch_test_stat=float(arch_stat),
            arch_test_pvalue=float(arch_pval),
            has_clustering=has_clustering,
            log_likelihood=float(log_lik),
            n_obs=n,
            converged=converged,
        )

        logger.info(
            f"📊 [GARCH] α={alpha:.4f} β={beta:.4f} persist={persistence:.4f} | "
            f"cur_vol={result.current_vol:.3f}% | "
            f"ARCH_p={arch_pval:.4f} clustering={'YES' if has_clustering else 'NO'}"
        )
        return result

    def _arch_test(self, residuals: np.ndarray, lags: int = 5):
        """
        Engle's ARCH LM Test.
        Regress squared residuals on lagged squared residuals.
        LM = n * R² ~ chi²(lags)
        """
        n = len(residuals)
        eps2 = residuals ** 2

        if n <= lags + 1:
            return 0.0, 1.0

        # Build regression matrix: eps²_t ~ const + eps²_(t-1) + ... + eps²_(t-lags)
        y = eps2[lags:]
        X = np.column_stack([np.ones(n - lags)] + [eps2[lags - i - 1: n - i - 1] for i in range(lags)])

        try:
            # OLS: beta = (X'X)^-1 X'y
            XtX = X.T @ X
            Xty = X.T @ y
            beta_ols = np.linalg.lstsq(XtX, Xty, rcond=None)[0]
            y_hat = X @ beta_ols
            ss_res = np.sum((y - y_hat) ** 2)
            ss_tot = np.sum((y - np.mean(y)) ** 2)
            r2 = 1 - ss_res / ss_tot if ss_tot > 0 else 0.0
            lm_stat = (n - lags) * r2
            p_value = _chi2_sf(lm_stat, df=lags)
            return float(lm_stat), float(p_value)
        except Exception:
            return 0.0, 1.0

    def _fit_garch(self, eps: np.ndarray):
        """
        Fit GARCH(1,1) via MLE.
        Minimisasi negative log-likelihood Gaussian.
        """
        var_eps = float(np.var(eps))
        if var_eps <= 0:
            var_eps = 1e-6

        # Initial params: [omega, alpha, beta]
        x0 = np.array([var_eps * 0.05, 0.10, 0.85])

        def neg_log_likelihood(params):
            omega, alpha, beta = params
            if omega <= 0 or alpha < 0 or beta < 0 or alpha + beta >= 1:
                return 1e10
            sigma2 = self._compute_conditional_variance(eps, omega, alpha, beta)
            # Gaussian log-likelihood: -0.5 * sum(log(sigma²) + eps²/sigma²)
            sigma2_safe = np.maximum(sigma2, 1e-10)
            ll = -0.5 * np.sum(np.log(sigma2_safe) + eps ** 2 / sigma2_safe)
            return -ll  # minimize negative

        # Constraints: omega > 0, alpha >= 0, beta >= 0, alpha+beta < 1
        bounds = [(1e-8, None), (1e-6, 0.999), (1e-6, 0.999)]
        constraints = [{"type": "ineq", "fun": lambda p: 0.9999 - p[1] - p[2]}]

        try:
            if minimize is None:
                raise RuntimeError("scipy.optimize unavailable")
            res = minimize(
                neg_log_likelihood,
                x0,
                method="SLSQP",
                bounds=bounds,
                constraints=constraints,
                options={"maxiter": 500, "ftol": 1e-9},
            )
            if res.success and res.x[1] + res.x[2] < 1:
                omega, alpha, beta = res.x
                return omega, alpha, beta, -res.fun, True
        except Exception as e:
            logger.debug(f"[GARCH] MLE optimization failed: {e}")

        # Fallback: method of moments estimate
        omega_fb = var_eps * 0.05
        alpha_fb = 0.10
        beta_fb = 0.85
        sigma2_fb = self._compute_conditional_variance(eps, omega_fb, alpha_fb, beta_fb)
        sigma2_safe = np.maximum(sigma2_fb, 1e-10)
        ll_fb = float(-0.5 * np.sum(np.log(sigma2_safe) + eps ** 2 / sigma2_safe))
        return omega_fb, alpha_fb, beta_fb, ll_fb, False

    def _compute_conditional_variance(
        self, eps: np.ndarray, omega: float, alpha: float, beta: float
    ) -> np.ndarray:
        """Hitung conditional variance series sigma²_t secara rekursif."""
        n = len(eps)
        sigma2 = np.empty(n)
        sigma2[0] = np.var(eps)  # Inisialisasi dengan unconditional variance

        for t in range(1, n):
            sigma2[t] = omega + alpha * eps[t - 1] ** 2 + beta * sigma2[t - 1]
            sigma2[t] = max(sigma2[t], 1e-10)  # Pastikan positif

        return sigma2
