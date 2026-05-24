#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# Tujuan: Markowitz Efficient Frontier dan portfolio optimization.
# Caller: quant/quant_commands.py, bot.py /quant_frontier command.
# Dependensi: numpy, scipy.optimize.
# Main Functions: class EfficientFrontier, FrontierResult, PortfolioWeights.
# Side Effects: none; pure computation only.
"""
Efficient Frontier & Portfolio Optimization (Markowitz)
=========================================================
Implementasi Modern Portfolio Theory (MPT) — Harry Markowitz (1952).

Konsep utama:
  - Setiap portfolio dapat digambarkan sebagai titik di ruang (risk, return)
  - Efficient Frontier = kurva portfolio dengan return maksimal untuk setiap level risiko
  - Optimal portfolios:
      a. Max Sharpe Ratio (tangency portfolio) — return/risk terbaik
      b. Min Variance (minimum risk portfolio)
      c. Max Return (untuk risk tolerance tertentu)

Input: matrix return historis dari beberapa aset (pair crypto)
Output:
  - Bobot optimal untuk setiap aset
  - Expected return, volatilitas, Sharpe ratio portfolio
  - Kurva efficient frontier (N titik)
  - Correlation matrix antar aset

Constraints:
  - Sum bobot = 1 (fully invested)
  - Bobot >= 0 (no short selling — sesuai crypto spot trading)
  - Bobot per aset <= max_weight (diversifikasi)

Usage:
    from quant.efficient_frontier import EfficientFrontier

    ef = EfficientFrontier()
    result = ef.optimize(
        returns_matrix={
            'btcidr': [3.5, -1.2, 2.1, ...],
            'ethidr': [4.1, -2.0, 1.8, ...],
            'bnbidr': [2.8, -0.9, 3.2, ...],
        }
    )

    result.max_sharpe_weights    # {'btcidr': 0.45, 'ethidr': 0.35, 'bnbidr': 0.20}
    result.min_var_weights       # bobot minimum variance
    result.frontier_points       # list (vol, ret) untuk plot
    result.summary_text()        # string untuk Telegram
"""

import logging
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

import numpy as np
try:
    from scipy.optimize import minimize
except (ImportError, ModuleNotFoundError):
    minimize = None

logger = logging.getLogger("crypto_bot")

MIN_ASSETS = 2          # Minimum aset untuk frontier
MIN_RETURNS_PER_ASSET = 20  # Minimum return per aset
FRONTIER_POINTS = 50    # Jumlah titik di kurva frontier
RISK_FREE_RATE = 0.0    # Asumsi 0% untuk crypto
TRADES_PER_YEAR = 365 * 4  # Annualization factor


@dataclass
class PortfolioWeights:
    """Bobot portfolio optimal untuk satu titik di frontier."""
    weights: Dict[str, float]       # {'btcidr': 0.45, ...}
    expected_return: float          # Expected annual return (%)
    volatility: float               # Annual volatility (%)
    sharpe_ratio: float             # Sharpe ratio
    label: str = ""                 # 'Max Sharpe', 'Min Variance', dll

    def summary_text(self) -> str:
        weights_str = "\n".join(
            f"  {pair}: `{w*100:.1f}%`"
            for pair, w in sorted(self.weights.items(), key=lambda x: -x[1])
        )
        return (
            f"*{self.label}*\n"
            f"{weights_str}\n"
            f"  Return: `{self.expected_return:.2f}%/tahun`\n"
            f"  Volatilitas: `{self.volatility:.2f}%`\n"
            f"  Sharpe: `{self.sharpe_ratio:.3f}`\n"
        )


@dataclass
class FrontierResult:
    """Hasil lengkap Efficient Frontier optimization."""
    assets: List[str]               # Nama aset
    n_assets: int                   # Jumlah aset

    # Optimal portfolios
    max_sharpe: PortfolioWeights    # Tangency portfolio (max Sharpe)
    min_variance: PortfolioWeights  # Minimum variance portfolio

    # Frontier curve: list of (volatility, return) tuples
    frontier_vols: List[float] = field(default_factory=list)
    frontier_rets: List[float] = field(default_factory=list)

    # Correlation matrix
    correlation_matrix: List[List[float]] = field(default_factory=list)

    # Individual asset stats
    asset_returns: Dict[str, float] = field(default_factory=dict)   # Annual return %
    asset_vols: Dict[str, float] = field(default_factory=dict)      # Annual vol %
    asset_sharpes: Dict[str, float] = field(default_factory=dict)   # Sharpe per aset

    # Equal weight benchmark
    equal_weight: Optional[PortfolioWeights] = None

    def summary_text(self) -> str:
        assets_str = ", ".join(f"`{a}`" for a in self.assets)
        individual_str = "\n".join(
            f"  {a}: ret=`{self.asset_returns.get(a, 0):.2f}%` "
            f"vol=`{self.asset_vols.get(a, 0):.2f}%` "
            f"sharpe=`{self.asset_sharpes.get(a, 0):.2f}`"
            for a in self.assets
        )
        return (
            f"📊 *Efficient Frontier — Markowitz MPT*\n"
            f"━━━━━━━━━━━━━━━━━━━━━━\n"
            f"Aset: {assets_str}\n"
            f"━━━━━━━━━━━━━━━━━━━━━━\n"
            f"📈 *Individual Asset Stats*\n"
            f"{individual_str}\n"
            f"━━━━━━━━━━━━━━━━━━━━━━\n"
            f"🏆 *{self.max_sharpe.label}*\n"
            + "\n".join(f"  {p}: `{w*100:.1f}%`" for p, w in sorted(self.max_sharpe.weights.items(), key=lambda x: -x[1]))
            + f"\n  Return: `{self.max_sharpe.expected_return:.2f}%` | "
            f"Vol: `{self.max_sharpe.volatility:.2f}%` | "
            f"Sharpe: `{self.max_sharpe.sharpe_ratio:.3f}`\n"
            f"━━━━━━━━━━━━━━━━━━━━━━\n"
            f"🛡️ *{self.min_variance.label}*\n"
            + "\n".join(f"  {p}: `{w*100:.1f}%`" for p, w in sorted(self.min_variance.weights.items(), key=lambda x: -x[1]))
            + f"\n  Return: `{self.min_variance.expected_return:.2f}%` | "
            f"Vol: `{self.min_variance.volatility:.2f}%` | "
            f"Sharpe: `{self.min_variance.sharpe_ratio:.3f}`\n"
        )

    def to_dict(self) -> dict:
        return {
            "assets": self.assets,
            "n_assets": self.n_assets,
            "max_sharpe": {
                "weights": self.max_sharpe.weights,
                "expected_return": round(self.max_sharpe.expected_return, 4),
                "volatility": round(self.max_sharpe.volatility, 4),
                "sharpe_ratio": round(self.max_sharpe.sharpe_ratio, 4),
            },
            "min_variance": {
                "weights": self.min_variance.weights,
                "expected_return": round(self.min_variance.expected_return, 4),
                "volatility": round(self.min_variance.volatility, 4),
                "sharpe_ratio": round(self.min_variance.sharpe_ratio, 4),
            },
            "asset_returns": {k: round(v, 4) for k, v in self.asset_returns.items()},
            "asset_vols": {k: round(v, 4) for k, v in self.asset_vols.items()},
            "asset_sharpes": {k: round(v, 4) for k, v in self.asset_sharpes.items()},
            "frontier_points": list(zip(
                [round(v, 4) for v in self.frontier_vols],
                [round(r, 4) for r in self.frontier_rets],
            )),
        }


class EfficientFrontier:
    """
    Markowitz Efficient Frontier optimizer.
    Menggunakan scipy.optimize untuk portfolio optimization.
    """

    def __init__(self, max_weight: float = 0.60, risk_free_rate: float = RISK_FREE_RATE):
        """
        Args:
            max_weight    : Bobot maksimal per aset (default 60% — diversifikasi)
            risk_free_rate: Risk-free rate untuk Sharpe ratio
        """
        self.max_weight = max_weight
        self.risk_free_rate = risk_free_rate
        logger.info(f"✅ EfficientFrontier initialized (max_weight={max_weight:.0%})")

    def optimize(
        self,
        returns_matrix: Dict[str, List[float]],
    ) -> Optional[FrontierResult]:
        """
        Hitung efficient frontier dari matrix return historis.

        Args:
            returns_matrix: Dict {pair_name: [return_pct, ...]}
                           Semua list harus punya panjang yang sama (atau akan di-trim)

        Returns:
            FrontierResult atau None jika data tidak cukup
        """
        # ── Validasi dan alignment data ───────────────────────────────────
        assets = [a for a, r in returns_matrix.items() if len(r) >= MIN_RETURNS_PER_ASSET]
        if len(assets) < MIN_ASSETS:
            logger.debug(f"[FRONTIER] Insufficient assets: {len(assets)} < {MIN_ASSETS}")
            return None

        # Trim ke panjang minimum
        min_len = min(len(returns_matrix[a]) for a in assets)
        R = np.array([returns_matrix[a][-min_len:] for a in assets], dtype=float)  # shape: (n_assets, n_obs)
        n_assets = len(assets)

        # ── Mean returns dan covariance matrix ────────────────────────────
        mean_returns = np.mean(R, axis=1)           # Per-trade mean return
        cov_matrix = np.cov(R)                      # Covariance matrix
        if n_assets == 1:
            cov_matrix = cov_matrix.reshape(1, 1)

        # Annualize
        ann_mean = mean_returns * TRADES_PER_YEAR   # Annual return
        ann_cov = cov_matrix * TRADES_PER_YEAR      # Annual covariance

        # ── Individual asset stats ────────────────────────────────────────
        asset_returns = {a: float(ann_mean[i]) for i, a in enumerate(assets)}
        asset_vols = {a: float(np.sqrt(ann_cov[i, i])) for i, a in enumerate(assets)}
        asset_sharpes = {
            a: float((ann_mean[i] - self.risk_free_rate) / np.sqrt(ann_cov[i, i]))
            if ann_cov[i, i] > 0 else 0.0
            for i, a in enumerate(assets)
        }

        # ── Correlation matrix ────────────────────────────────────────────
        std_devs = np.sqrt(np.diag(ann_cov))
        std_outer = np.outer(std_devs, std_devs)
        corr_matrix = np.where(std_outer > 0, ann_cov / std_outer, 0.0)

        # ── Constraints & bounds ──────────────────────────────────────────
        constraints = [{"type": "eq", "fun": lambda w: np.sum(w) - 1}]
        bounds = [(0.0, self.max_weight)] * n_assets

        # ── Max Sharpe Portfolio ──────────────────────────────────────────
        max_sharpe_w = self._optimize_max_sharpe(ann_mean, ann_cov, bounds, constraints, n_assets)
        ms_ret, ms_vol, ms_sharpe = self._portfolio_stats(max_sharpe_w, ann_mean, ann_cov)
        max_sharpe_port = PortfolioWeights(
            weights={assets[i]: round(float(max_sharpe_w[i]), 4) for i in range(n_assets)},
            expected_return=ms_ret,
            volatility=ms_vol,
            sharpe_ratio=ms_sharpe,
            label="Max Sharpe Ratio (Tangency Portfolio)",
        )

        # ── Min Variance Portfolio ────────────────────────────────────────
        min_var_w = self._optimize_min_variance(ann_cov, bounds, constraints, n_assets)
        mv_ret, mv_vol, mv_sharpe = self._portfolio_stats(min_var_w, ann_mean, ann_cov)
        min_var_port = PortfolioWeights(
            weights={assets[i]: round(float(min_var_w[i]), 4) for i in range(n_assets)},
            expected_return=mv_ret,
            volatility=mv_vol,
            sharpe_ratio=mv_sharpe,
            label="Minimum Variance Portfolio",
        )

        # ── Equal Weight Benchmark ────────────────────────────────────────
        eq_w = np.ones(n_assets) / n_assets
        eq_ret, eq_vol, eq_sharpe = self._portfolio_stats(eq_w, ann_mean, ann_cov)
        equal_weight_port = PortfolioWeights(
            weights={assets[i]: round(float(eq_w[i]), 4) for i in range(n_assets)},
            expected_return=eq_ret,
            volatility=eq_vol,
            sharpe_ratio=eq_sharpe,
            label="Equal Weight Benchmark",
        )

        # ── Efficient Frontier Curve ──────────────────────────────────────
        frontier_vols, frontier_rets = self._compute_frontier(
            ann_mean, ann_cov, bounds, n_assets
        )

        result = FrontierResult(
            assets=assets,
            n_assets=n_assets,
            max_sharpe=max_sharpe_port,
            min_variance=min_var_port,
            frontier_vols=frontier_vols,
            frontier_rets=frontier_rets,
            correlation_matrix=corr_matrix.tolist(),
            asset_returns=asset_returns,
            asset_vols=asset_vols,
            asset_sharpes=asset_sharpes,
            equal_weight=equal_weight_port,
        )

        logger.info(
            f"📊 [FRONTIER] {n_assets} assets | "
            f"MaxSharpe={ms_sharpe:.3f} (ret={ms_ret:.2f}% vol={ms_vol:.2f}%) | "
            f"MinVar vol={mv_vol:.2f}%"
        )
        return result

    def _portfolio_stats(
        self, weights: np.ndarray, ann_mean: np.ndarray, ann_cov: np.ndarray
    ) -> Tuple[float, float, float]:
        """Hitung return, volatilitas, dan Sharpe ratio portfolio."""
        ret = float(weights @ ann_mean)
        var = float(weights @ ann_cov @ weights)
        vol = float(np.sqrt(max(var, 1e-10)))
        sharpe = (ret - self.risk_free_rate) / vol if vol > 0 else 0.0
        return ret, vol, sharpe

    def _candidate_weights(self, n_assets: int, samples: int = 5000) -> np.ndarray:
        """Deterministic fallback candidate portfolios when scipy.optimize is unavailable."""
        rng = np.random.default_rng(42 + n_assets)
        equal = np.ones(n_assets) / n_assets
        candidates = [equal]

        random_weights = rng.dirichlet(np.ones(n_assets), size=samples)
        feasible = random_weights[np.all(random_weights <= self.max_weight + 1e-12, axis=1)]
        if len(feasible) > 0:
            candidates.extend(feasible)

        # Add simple capped tilts so small asset universes still have edge candidates.
        if self.max_weight * n_assets >= 1:
            for i in range(n_assets):
                w = np.full(n_assets, (1 - self.max_weight) / max(n_assets - 1, 1))
                w[i] = self.max_weight
                if np.all(w >= -1e-12) and np.all(w <= self.max_weight + 1e-12):
                    candidates.append(w)

        return np.array(candidates, dtype=float)

    def _optimize_max_sharpe(
        self, ann_mean, ann_cov, bounds, constraints, n_assets
    ) -> np.ndarray:
        """Cari bobot yang memaksimalkan Sharpe ratio."""
        def neg_sharpe(w):
            ret, vol, _ = self._portfolio_stats(w, ann_mean, ann_cov)
            return -(ret - self.risk_free_rate) / vol if vol > 0 else 1e10

        w0 = np.ones(n_assets) / n_assets
        try:
            if minimize is None:
                raise RuntimeError("scipy.optimize unavailable")
            res = minimize(neg_sharpe, w0, method="SLSQP", bounds=bounds,
                           constraints=constraints, options={"maxiter": 500})
            if res.success:
                return np.clip(res.x, 0, self.max_weight)
        except Exception as e:
            logger.debug(f"[FRONTIER] Max Sharpe optimization failed: {e}")

        candidates = self._candidate_weights(n_assets)
        scores = [self._portfolio_stats(w, ann_mean, ann_cov)[2] for w in candidates]
        return candidates[int(np.argmax(scores))]

    def _optimize_min_variance(
        self, ann_cov, bounds, constraints, n_assets
    ) -> np.ndarray:
        """Cari bobot yang meminimalkan variance portfolio."""
        def portfolio_var(w):
            return float(w @ ann_cov @ w)

        w0 = np.ones(n_assets) / n_assets
        try:
            if minimize is None:
                raise RuntimeError("scipy.optimize unavailable")
            res = minimize(portfolio_var, w0, method="SLSQP", bounds=bounds,
                           constraints=constraints, options={"maxiter": 500})
            if res.success:
                return np.clip(res.x, 0, self.max_weight)
        except Exception as e:
            logger.debug(f"[FRONTIER] Min Variance optimization failed: {e}")

        candidates = self._candidate_weights(n_assets)
        variances = [portfolio_var(w) for w in candidates]
        return candidates[int(np.argmin(variances))]

    def _compute_frontier(
        self, ann_mean, ann_cov, bounds, n_assets
    ) -> Tuple[List[float], List[float]]:
        """
        Hitung kurva efficient frontier dengan target return sweep.
        Returns: (list_volatilities, list_returns)
        """
        min_ret = float(np.min(ann_mean))
        max_ret = float(np.max(ann_mean))
        target_returns = np.linspace(min_ret, max_ret, FRONTIER_POINTS)

        frontier_vols = []
        frontier_rets = []

        if minimize is None:
            candidates = self._candidate_weights(n_assets)
            stats = [self._portfolio_stats(w, ann_mean, ann_cov) for w in candidates]
            for target in target_returns:
                idx = int(np.argmin([abs(ret - target) for ret, _, _ in stats]))
                ret, vol, _ = stats[idx]
                frontier_vols.append(float(vol))
                frontier_rets.append(float(ret))
            return frontier_vols, frontier_rets

        for target in target_returns:
            constraints = [
                {"type": "eq", "fun": lambda w: np.sum(w) - 1},
                {"type": "eq", "fun": lambda w, t=target: w @ ann_mean - t},
            ]

            def portfolio_var(w):
                return float(w @ ann_cov @ w)

            w0 = np.ones(n_assets) / n_assets
            try:
                res = minimize(portfolio_var, w0, method="SLSQP", bounds=bounds,
                               constraints=constraints, options={"maxiter": 300, "ftol": 1e-8})
                if res.success:
                    vol = float(np.sqrt(max(res.fun, 0)))
                    frontier_vols.append(vol)
                    frontier_rets.append(float(target))
            except Exception:
                continue

        return frontier_vols, frontier_rets
