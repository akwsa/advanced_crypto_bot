"""Quantitative trading modules for Advanced Crypto Bot.

Modules:
    - mean_reversion     : Z-Score mean reversion signal scoring
    - bayesian_kelly     : Adaptive position sizing with Bayesian Kelly Criterion
    - momentum_factor    : Multi-timeframe momentum factor scoring
    - performance_analytics: Sharpe, Sortino, Calmar, drawdown metrics
    - dynamic_correlation: Rolling correlation matrix & portfolio heat
    - stat_arb           : Statistical arbitrage (pair trading) engine
    - risk_metrics       : CAGR, VaR (Historical/Parametric/Monte Carlo), CVaR
    - volatility_models  : GARCH(1,1) volatility clustering & ARCH test
    - forecasting        : ARIMA price/return forecasting
    - efficient_frontier : Markowitz Efficient Frontier & portfolio optimization
"""

from quant.mean_reversion import MeanReversionEngine, MeanReversionResult
from quant.bayesian_kelly import BayesianKellyEngine, KellyResult
from quant.momentum_factor import MomentumFactorEngine, MomentumResult
from quant.performance_analytics import PerformanceAnalytics, PerformanceMetrics
from quant.dynamic_correlation import DynamicCorrelationEngine, CorrelationCheckResult
from quant.stat_arb import StatArbEngine, StatArbOpportunity
from quant.risk_metrics import RiskMetrics, RiskResult
from quant.volatility_models import GARCHModel, GARCHResult
from quant.forecasting import ARIMAModel, ARIMAResult
from quant.efficient_frontier import EfficientFrontier, FrontierResult, PortfolioWeights

__all__ = [
    # Existing modules
    "MeanReversionEngine", "MeanReversionResult",
    "BayesianKellyEngine", "KellyResult",
    "MomentumFactorEngine", "MomentumResult",
    "PerformanceAnalytics", "PerformanceMetrics",
    "DynamicCorrelationEngine", "CorrelationCheckResult",
    "StatArbEngine", "StatArbOpportunity",
    # New modules (2026-05-19)
    "RiskMetrics", "RiskResult",
    "GARCHModel", "GARCHResult",
    "ARIMAModel", "ARIMAResult",
    "EfficientFrontier", "FrontierResult", "PortfolioWeights",
]
