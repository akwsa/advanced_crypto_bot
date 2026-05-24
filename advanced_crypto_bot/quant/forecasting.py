#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# Tujuan: ARIMA forecasting untuk prediksi harga/return jangka pendek.
# Caller: quant/quant_commands.py, bot.py /quant_forecast command.
# Dependensi: numpy, scipy.linalg.
# Main Functions: class ARIMAModel, ARIMAResult.
# Side Effects: none; pure computation only.
"""
ARIMA Forecasting Engine
=========================
Implementasi ARIMA(p,d,q) pure numpy — tanpa statsmodels/pmdarima.

ARIMA = AutoRegressive Integrated Moving Average
  p = order AR (autoregressive): pengaruh nilai masa lalu
  d = order differencing: membuat series stasioner
  q = order MA (moving average): pengaruh error masa lalu

Default: ARIMA(1,1,1) — cocok untuk price series crypto yang non-stasioner.

Algoritma:
  1. Differencing d kali untuk stasionarisasi
  2. Estimasi parameter AR(p) via OLS (Yule-Walker equations)
  3. Estimasi parameter MA(q) via iterative residual fitting
  4. Forecast h langkah ke depan dengan confidence interval
  5. Inverse differencing untuk kembali ke skala harga asli

Auto-order selection (opsional):
  - AIC-based selection untuk p ∈ [0,3], q ∈ [0,2]
  - Pilih kombinasi dengan AIC terendah

Usage:
    from quant.forecasting import ARIMAModel

    arima = ARIMAModel(p=1, d=1, q=1)
    result = arima.fit_forecast(prices=[1500000, 1510000, 1505000, ...], steps=5)

    result.forecast          # list harga forecast [h1, h2, ..., h5]
    result.conf_lower        # confidence interval bawah
    result.conf_upper        # confidence interval atas
    result.direction         # 'UP', 'DOWN', 'FLAT'
    result.summary_text()    # string untuk Telegram
"""

import logging
from dataclasses import dataclass, field
from typing import List, Optional, Tuple

import numpy as np

logger = logging.getLogger("crypto_bot")

MIN_PRICES = 30       # Minimum data harga
MAX_AR_ORDER = 3      # Max p untuk auto-selection
MAX_MA_ORDER = 2      # Max q untuk auto-selection
CONF_LEVEL = 1.96     # 95% confidence interval (z-score)


@dataclass
class ARIMAResult:
    """Hasil ARIMA forecasting."""
    # Model spec
    p: int                          # AR order
    d: int                          # Differencing order
    q: int                          # MA order
    n_obs: int                      # Jumlah observasi

    # Forecast
    steps: int                      # Jumlah langkah forecast
    forecast: List[float] = field(default_factory=list)       # Harga forecast
    conf_lower: List[float] = field(default_factory=list)     # CI bawah (95%)
    conf_upper: List[float] = field(default_factory=list)     # CI atas (95%)

    # Arah prediksi
    last_price: float = 0.0
    forecast_price: float = 0.0     # Harga forecast terakhir
    expected_change_pct: float = 0.0  # Perubahan % dari harga terakhir
    direction: str = "FLAT"         # 'UP', 'DOWN', 'FLAT'

    # Fit quality
    aic: float = 0.0
    residual_std: float = 0.0
    converged: bool = False

    def summary_text(self) -> str:
        dir_emoji = "📈" if self.direction == "UP" else ("📉" if self.direction == "DOWN" else "➡️")
        forecast_str = "\n".join(
            f"  +{i+1}: `{self.forecast[i]:,.0f}` [{self.conf_lower[i]:,.0f} – {self.conf_upper[i]:,.0f}]"
            for i in range(min(len(self.forecast), 5))
        )
        return (
            f"🔮 *ARIMA({self.p},{self.d},{self.q}) Forecast*\n"
            f"━━━━━━━━━━━━━━━━━━━━━━\n"
            f"  Harga terakhir: `{self.last_price:,.0f}`\n"
            f"  Forecast +{self.steps}: `{self.forecast_price:,.0f}`\n"
            f"  Perubahan: `{self.expected_change_pct:+.2f}%` {dir_emoji}\n"
            f"━━━━━━━━━━━━━━━━━━━━━━\n"
            f"📋 *Detail Forecast (95% CI)*\n"
            f"{forecast_str}\n"
            f"━━━━━━━━━━━━━━━━━━━━━━\n"
            f"  AIC: `{self.aic:.2f}` | Res.Std: `{self.residual_std:.4f}`\n"
            f"  Obs: `{self.n_obs}` | Converged: {'✅' if self.converged else '⚠️'}\n"
        )

    def to_dict(self) -> dict:
        return {
            "p": self.p, "d": self.d, "q": self.q,
            "n_obs": self.n_obs,
            "steps": self.steps,
            "forecast": [round(f, 2) for f in self.forecast],
            "conf_lower": [round(f, 2) for f in self.conf_lower],
            "conf_upper": [round(f, 2) for f in self.conf_upper],
            "last_price": round(self.last_price, 2),
            "forecast_price": round(self.forecast_price, 2),
            "expected_change_pct": round(self.expected_change_pct, 4),
            "direction": self.direction,
            "aic": round(self.aic, 4),
            "residual_std": round(self.residual_std, 6),
            "converged": self.converged,
        }


class ARIMAModel:
    """
    ARIMA(p,d,q) model — pure numpy implementation.
    Cocok untuk price series crypto (non-stasioner, volatile).
    """

    def __init__(self, p: int = 1, d: int = 1, q: int = 1, auto_order: bool = False):
        """
        Args:
            p: AR order (default 1)
            d: Differencing order (default 1 — harga biasanya I(1))
            q: MA order (default 1)
            auto_order: Jika True, pilih p,q terbaik via AIC
        """
        self.p = p
        self.d = d
        self.q = q
        self.auto_order = auto_order
        logger.info(f"✅ ARIMA({p},{d},{q}) Model initialized (auto_order={auto_order})")

    def fit_forecast(
        self,
        prices: List[float],
        steps: int = 5,
    ) -> Optional[ARIMAResult]:
        """
        Fit ARIMA dan forecast h langkah ke depan.

        Args:
            prices: List harga historis (close price)
            steps : Jumlah langkah forecast ke depan

        Returns:
            ARIMAResult atau None jika data tidak cukup
        """
        if not prices or len(prices) < MIN_PRICES:
            logger.debug(f"[ARIMA] Insufficient data: {len(prices) if prices else 0}")
            return None

        prices_arr = np.array(prices, dtype=float)
        last_price = float(prices_arr[-1])
        n = len(prices_arr)

        # ── Differencing ──────────────────────────────────────────────────
        diff_series, orig_tail = self._difference(prices_arr, self.d)

        # ── Auto order selection ──────────────────────────────────────────
        p, q = self.p, self.q
        if self.auto_order:
            p, q = self._select_order(diff_series)

        # ── Fit AR(p) + MA(q) ─────────────────────────────────────────────
        ar_params, ma_params, residuals, converged = self._fit_arma(diff_series, p, q)

        # ── Residual std untuk confidence interval ────────────────────────
        res_std = float(np.std(residuals, ddof=1)) if len(residuals) > 1 else 0.01

        # ── AIC ───────────────────────────────────────────────────────────
        n_diff = len(diff_series)
        k = p + q + 1  # jumlah parameter
        if res_std > 0:
            aic = n_diff * np.log(res_std ** 2) + 2 * k
        else:
            aic = 0.0

        # ── Forecast pada differenced series ─────────────────────────────
        diff_forecast, diff_std = self._forecast_arma(
            diff_series, ar_params, ma_params, residuals, steps
        )

        # ── Inverse differencing → kembali ke skala harga asli ───────────
        forecast_prices = self._inverse_difference(diff_forecast, orig_tail, self.d)

        # ── Confidence intervals ──────────────────────────────────────────
        # CI melebar seiring langkah forecast (uncertainty propagation)
        conf_lower = []
        conf_upper = []
        for h, fp in enumerate(forecast_prices):
            margin = CONF_LEVEL * diff_std * np.sqrt(h + 1)
            conf_lower.append(fp - margin)
            conf_upper.append(fp + margin)

        # ── Arah prediksi ─────────────────────────────────────────────────
        forecast_final = float(forecast_prices[-1]) if len(forecast_prices) > 0 else last_price
        change_pct = (forecast_final / last_price - 1) * 100 if last_price > 0 else 0.0

        if change_pct > 0.5:
            direction = "UP"
        elif change_pct < -0.5:
            direction = "DOWN"
        else:
            direction = "FLAT"

        result = ARIMAResult(
            p=p, d=self.d, q=q,
            n_obs=n,
            steps=steps,
            forecast=[float(f) for f in forecast_prices],
            conf_lower=[float(f) for f in conf_lower],
            conf_upper=[float(f) for f in conf_upper],
            last_price=last_price,
            forecast_price=forecast_final,
            expected_change_pct=change_pct,
            direction=direction,
            aic=float(aic),
            residual_std=res_std,
            converged=converged,
        )

        logger.info(
            f"🔮 [ARIMA] ({p},{self.d},{q}) | "
            f"last={last_price:,.0f} → forecast={forecast_final:,.0f} "
            f"({change_pct:+.2f}%) [{direction}] | AIC={aic:.2f}"
        )
        return result

    def _difference(self, series: np.ndarray, d: int) -> Tuple[np.ndarray, List[float]]:
        """
        Differencing d kali. Simpan tail untuk inverse differencing.
        Returns: (differenced_series, original_tail_values)
        """
        orig_tail = []
        s = series.copy()
        for _ in range(d):
            orig_tail.append(float(s[-1]))
            s = np.diff(s)
        return s, orig_tail

    def _inverse_difference(
        self, diff_forecast: np.ndarray, orig_tail: List[float], d: int
    ) -> np.ndarray:
        """Kembalikan differenced forecast ke skala asli."""
        result = diff_forecast.copy()
        for i in range(d - 1, -1, -1):
            last_val = orig_tail[i]
            # Cumulative sum dari last observed value
            result = np.cumsum(np.concatenate([[last_val], result]))[1:]
        return result

    def _fit_arma(
        self, series: np.ndarray, p: int, q: int
    ) -> Tuple[np.ndarray, np.ndarray, np.ndarray, bool]:
        """
        Fit ARMA(p,q) via OLS untuk AR, iterative untuk MA.
        Returns: (ar_params, ma_params, residuals, converged)
        """
        n = len(series)
        max_lag = max(p, q, 1)

        if n <= max_lag + 1:
            return np.zeros(p), np.zeros(q), series, False

        # ── Fit AR(p) via OLS (Yule-Walker style) ────────────────────────
        ar_params = np.zeros(p)
        if p > 0:
            # Build lagged matrix
            y = series[p:]
            X = np.column_stack([series[p - i - 1: n - i - 1] for i in range(p)])
            try:
                ar_params = np.linalg.lstsq(X, y, rcond=None)[0]
            except Exception:
                ar_params = np.zeros(p)

        # ── Compute AR residuals ──────────────────────────────────────────
        ar_residuals = series.copy()
        if p > 0:
            for t in range(p, n):
                ar_hat = sum(ar_params[i] * series[t - i - 1] for i in range(p))
                ar_residuals[t] = series[t] - ar_hat

        # ── Fit MA(q) via iterative OLS on residuals ──────────────────────
        ma_params = np.zeros(q)
        residuals = ar_residuals.copy()
        converged = True

        if q > 0:
            for _ in range(10):  # iterasi konvergensi
                y_ma = residuals[q:]
                X_ma = np.column_stack([residuals[q - i - 1: n - i - 1] for i in range(q)])
                try:
                    new_ma = np.linalg.lstsq(X_ma, y_ma, rcond=None)[0]
                except Exception:
                    converged = False
                    break

                # Update residuals
                new_residuals = residuals.copy()
                for t in range(q, n):
                    ma_hat = sum(new_ma[i] * residuals[t - i - 1] for i in range(q))
                    new_residuals[t] = residuals[t] - ma_hat

                # Check convergence
                if np.max(np.abs(new_ma - ma_params)) < 1e-6:
                    ma_params = new_ma
                    residuals = new_residuals
                    break
                ma_params = new_ma
                residuals = new_residuals

        return ar_params, ma_params, residuals, converged

    def _forecast_arma(
        self,
        series: np.ndarray,
        ar_params: np.ndarray,
        ma_params: np.ndarray,
        residuals: np.ndarray,
        steps: int,
    ) -> Tuple[np.ndarray, float]:
        """
        Forecast h langkah ke depan dari ARMA model.
        Returns: (forecast_array, residual_std)
        """
        p = len(ar_params)
        q = len(ma_params)
        n = len(series)

        # Extend series dengan forecast
        extended = list(series)
        extended_res = list(residuals)
        res_std = float(np.std(residuals, ddof=1)) if len(residuals) > 1 else 0.01

        forecasts = []
        for h in range(steps):
            # AR component
            ar_val = 0.0
            for i in range(p):
                idx = len(extended) - i - 1
                if idx >= 0:
                    ar_val += ar_params[i] * extended[idx]

            # MA component (residuals = 0 untuk future steps)
            ma_val = 0.0
            for i in range(q):
                idx = len(extended_res) - i - 1
                if idx >= 0 and h == 0:  # Hanya gunakan residual historis untuk step pertama
                    ma_val += ma_params[i] * extended_res[idx]

            forecast_val = ar_val + ma_val
            forecasts.append(forecast_val)
            extended.append(forecast_val)
            extended_res.append(0.0)  # Future residuals = 0 (expected value)

        return np.array(forecasts), res_std

    def _select_order(self, series: np.ndarray) -> Tuple[int, int]:
        """
        Pilih p, q terbaik berdasarkan AIC.
        Grid search: p ∈ [0, MAX_AR_ORDER], q ∈ [0, MAX_MA_ORDER]
        """
        best_aic = np.inf
        best_p, best_q = 1, 1

        for p in range(0, MAX_AR_ORDER + 1):
            for q in range(0, MAX_MA_ORDER + 1):
                if p == 0 and q == 0:
                    continue
                try:
                    _, _, residuals, _ = self._fit_arma(series, p, q)
                    n = len(series)
                    k = p + q + 1
                    res_var = np.var(residuals, ddof=1)
                    if res_var > 0:
                        aic = n * np.log(res_var) + 2 * k
                        if aic < best_aic:
                            best_aic = aic
                            best_p, best_q = p, q
                except Exception:
                    continue

        logger.debug(f"[ARIMA] Auto-selected order: p={best_p}, q={best_q} (AIC={best_aic:.2f})")
        return best_p, best_q
