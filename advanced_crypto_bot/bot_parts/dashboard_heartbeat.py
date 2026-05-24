#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# Tujuan: Best-effort Redis heartbeat publisher untuk dashboard web.
# Caller: bot.py saat runtime bot aktif.
# Dependensi: threading/time, Redis client dari cache.redis_state_manager.
# Side Effects: Redis SETEX dashboard:bot:heartbeat.
"""Dashboard heartbeat helpers.

The dashboard intentionally runs as a companion process.  This tiny publisher
lets the dashboard distinguish "bot process alive" from "dashboard/API alive"
without coupling dashboard code to ``bot.py`` internals.
"""

from __future__ import annotations

import logging
import threading
import time
from typing import Callable, Optional

DASHBOARD_BOT_HEARTBEAT_KEY = "dashboard:bot:heartbeat"
DASHBOARD_BOT_HEARTBEAT_TTL_SECONDS = 30
DASHBOARD_BOT_HEARTBEAT_INTERVAL_SECONDS = 10

logger = logging.getLogger("crypto_bot")


def publish_bot_heartbeat(redis_client, now: Optional[float] = None) -> bool:
    """Publish a best-effort bot heartbeat to Redis.

    Returns ``True`` when Redis accepted the write and ``False`` otherwise.
    Exceptions are intentionally swallowed so dashboard observability can never
    crash or slow the trading bot.
    """

    if redis_client is None:
        return False

    timestamp = int(now if now is not None else time.time())
    try:
        redis_client.setex(
            DASHBOARD_BOT_HEARTBEAT_KEY,
            DASHBOARD_BOT_HEARTBEAT_TTL_SECONDS,
            str(timestamp),
        )
        return True
    except Exception as exc:  # pragma: no cover - exact Redis failures vary
        logger.debug("Dashboard heartbeat publish failed: %s", exc)
        return False


def publish_bot_heartbeat_via_state_manager(state_manager, now: Optional[float] = None) -> bool:
    """Publish heartbeat using the existing RedisStateManager connection."""

    if state_manager is None:
        return False

    try:
        is_available = getattr(state_manager, "is_available", lambda: False)
        if not is_available():
            return False
        return publish_bot_heartbeat(getattr(state_manager, "_redis", None), now=now)
    except Exception as exc:  # defensive: state manager must not crash bot
        logger.debug("Dashboard heartbeat state-manager check failed: %s", exc)
        return False


def start_bot_heartbeat_thread(
    state_manager,
    *,
    stop_event: threading.Event,
    interval_seconds: float = DASHBOARD_BOT_HEARTBEAT_INTERVAL_SECONDS,
    now_func: Callable[[], float] = time.time,
) -> threading.Thread:
    """Start a daemon thread that publishes heartbeat until ``stop_event``.

    The first heartbeat is sent immediately, then every ``interval_seconds``.
    """

    def _run() -> None:
        while not stop_event.is_set():
            publish_bot_heartbeat_via_state_manager(state_manager, now=now_func())
            stop_event.wait(interval_seconds)

    thread = threading.Thread(
        target=_run,
        name="DashboardHeartbeat",
        daemon=True,
    )
    thread.start()
    return thread
