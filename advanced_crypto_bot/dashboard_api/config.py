import os
from dataclasses import dataclass

from core.config import Config


@dataclass(frozen=True)
class DashboardSettings:
    trading_db_path: str
    signals_db_path: str
    dashboard_write_enabled: bool = False


def _bool_env(name: str, default: bool = False) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return str(raw).strip().lower() in {"1", "true", "yes", "on"}


def get_settings() -> DashboardSettings:
    return DashboardSettings(
        trading_db_path=os.getenv("DATABASE_PATH", Config.DATABASE_PATH),
        signals_db_path=os.getenv("SIGNALS_DATABASE_PATH", "data/signals.db"),
        dashboard_write_enabled=False,
    )


def safety_status() -> dict:
    dry_run = bool(Config.AUTO_TRADE_DRY_RUN)
    return {
        "auto_trading_enabled": bool(Config.AUTO_TRADING_ENABLED),
        "auto_trade_dry_run": dry_run,
        "manual_trading_enabled": bool(Config.MANUAL_TRADING_ENABLED),
        "cancel_trade_enabled": bool(Config.CANCEL_TRADE_ENABLED),
        "dashboard_write_enabled": False,
        "real_trading_locked": dry_run,
        "smart_hunter": {"running": None, "mode": "DRY_RUN" if dry_run else "REAL"},
        "auto_hunter": {"running": None, "mode": "DRY_RUN" if dry_run else "REAL"},
    }
