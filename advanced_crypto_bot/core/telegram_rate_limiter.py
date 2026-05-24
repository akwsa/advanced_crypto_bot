# Tujuan: Lightweight per-user Telegram command cooldowns.
# Caller: core.handler_registry saat mendaftarkan CommandHandler.
# Dependensi: time monotonic clock, python-telegram-bot Update shape.
# Main Functions: TelegramCommandRateLimiter, rate_limited_command.
# Side Effects: Mutasi state in-memory cooldown per proses bot.
"""Telegram command rate limiting helpers."""

from __future__ import annotations

import inspect
import time
from dataclasses import dataclass
from typing import Awaitable, Callable, Optional


@dataclass(frozen=True)
class RateLimitDecision:
    """Result of a rate-limit check."""

    allowed: bool
    retry_after: float = 0.0


class TelegramCommandRateLimiter:
    """Per-user/per-command cooldown limiter for Telegram command handlers.

    The limiter is intentionally in-memory: it protects the running bot from
    repeated manual command spam without changing persistence/trading state.
    """

    def __init__(self, per_command_seconds: float = 2.0, clock: Optional[Callable[[], float]] = None):
        self.per_command_seconds = max(0.0, float(per_command_seconds))
        self._clock = clock or time.monotonic
        self._last_seen: dict[tuple[int, str], float] = {}

    def check(self, user_id: int, command: str) -> RateLimitDecision:
        """Return whether this user may run this command now."""
        if self.per_command_seconds <= 0:
            return RateLimitDecision(True, 0.0)

        command_key = str(command or "").strip().lstrip("/").lower()
        key = (int(user_id), command_key)
        now = float(self._clock())
        last = self._last_seen.get(key)
        if last is not None:
            elapsed = now - last
            if elapsed < self.per_command_seconds:
                return RateLimitDecision(False, self.per_command_seconds - elapsed)

        self._last_seen[key] = now
        return RateLimitDecision(True, 0.0)


def _extract_user_id(update) -> Optional[int]:
    user = getattr(update, "effective_user", None)
    user_id = getattr(user, "id", None)
    return int(user_id) if user_id is not None else None


async def _send_rate_limit_warning(update, retry_after: float) -> None:
    message = getattr(update, "effective_message", None) or getattr(update, "message", None)
    if message is None or not hasattr(message, "reply_text"):
        return
    seconds = max(1, int(round(retry_after)))
    await message.reply_text(f"⏳ Terlalu cepat. Coba lagi dalam {seconds} detik.")


def rate_limited_command(
    command: str,
    callback: Callable[..., Awaitable[object]],
    *,
    limiter: TelegramCommandRateLimiter,
):
    """Wrap a Telegram command callback with per-user command cooldown."""

    async def wrapped(update, context):
        user_id = _extract_user_id(update)
        if user_id is not None:
            decision = limiter.check(user_id=user_id, command=command)
            if not decision.allowed:
                await _send_rate_limit_warning(update, decision.retry_after)
                return None

        result = callback(update, context)
        if inspect.isawaitable(result):
            return await result
        return result

    wrapped.__name__ = getattr(callback, "__name__", f"rate_limited_{command}")
    wrapped.__doc__ = getattr(callback, "__doc__", None)
    return wrapped
