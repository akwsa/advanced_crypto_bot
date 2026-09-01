"""Application command handlers for AutoTrade Next."""

from .settlement import (
    PrepareExecutionCommand,
    SettleLifecycleCommand,
    prepare_before_dispatch,
    settle_lifecycle_event,
)
from .exit import EvaluateExitCommand, ExitCommandResult, prepare_protective_exit
from .portfolio_allocation import (
    AllocatePortfolioCommand,
    AllocatePortfolioResult,
    allocate_portfolio,
)

__all__ = (
    "AllocatePortfolioCommand",
    "AllocatePortfolioResult",
    "EvaluateExitCommand",
    "ExitCommandResult",
    "PrepareExecutionCommand",
    "SettleLifecycleCommand",
    "prepare_before_dispatch",
    "allocate_portfolio",
    "prepare_protective_exit",
    "settle_lifecycle_event",
)
