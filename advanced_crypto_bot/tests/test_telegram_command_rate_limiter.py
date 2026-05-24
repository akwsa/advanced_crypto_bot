import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock

from core.telegram_rate_limiter import TelegramCommandRateLimiter, rate_limited_command


class FakeClock:
    def __init__(self, now=100.0):
        self.now = now

    def __call__(self):
        return self.now


def _update(user_id=123, text="/status"):
    message = SimpleNamespace(text=text, replies=[])

    async def reply_text(text, **kwargs):
        message.replies.append((text, kwargs))

    message.reply_text = reply_text
    return SimpleNamespace(
        effective_user=SimpleNamespace(id=user_id),
        effective_message=message,
        message=message,
        callback_query=None,
    )


async def _run(handler, update):
    await handler(update, SimpleNamespace())


def test_rate_limiter_allows_first_command_and_blocks_repeat_within_window():
    clock = FakeClock()
    limiter = TelegramCommandRateLimiter(per_command_seconds=5.0, clock=clock)

    assert limiter.check(user_id=1, command="status").allowed
    blocked = limiter.check(user_id=1, command="status")

    assert not blocked.allowed
    assert 0 < blocked.retry_after <= 5.0


def test_rate_limiter_tracks_different_commands_independently():
    clock = FakeClock()
    limiter = TelegramCommandRateLimiter(per_command_seconds=5.0, clock=clock)

    assert limiter.check(user_id=1, command="status").allowed
    assert limiter.check(user_id=1, command="price").allowed


def test_rate_limiter_allows_again_after_window():
    clock = FakeClock()
    limiter = TelegramCommandRateLimiter(per_command_seconds=5.0, clock=clock)

    assert limiter.check(user_id=1, command="status").allowed
    clock.now += 5.1

    assert limiter.check(user_id=1, command="status").allowed


def test_rate_limited_command_sends_soft_warning_and_skips_callback():
    clock = FakeClock()
    limiter = TelegramCommandRateLimiter(per_command_seconds=5.0, clock=clock)
    callback = AsyncMock()
    wrapped = rate_limited_command("status", callback, limiter=limiter)

    asyncio.run(_run(wrapped, _update(user_id=1, text="/status")))
    asyncio.run(_run(wrapped, _update(user_id=1, text="/status")))

    assert callback.await_count == 1
