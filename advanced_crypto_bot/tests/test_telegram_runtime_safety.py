import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from bot import AdvancedCryptoBot


class _FakeLoop:
    def __init__(self):
        self.calls = []
        self.closed = False

    def call_soon_threadsafe(self, callback, *args):
        self.calls.append((callback, args))
        callback(*args)

    def is_closed(self):
        return self.closed


def _make_bot_stub():
    bot = AdvancedCryptoBot.__new__(AdvancedCryptoBot)
    bot.app = SimpleNamespace(bot=SimpleNamespace(send_message=AsyncMock()))
    bot._telegram_loop = _FakeLoop()
    return bot


def test_send_telegram_admins_uses_main_telegram_loop_and_existing_bot(monkeypatch):
    bot = _make_bot_stub()

    scheduled = []

    def fake_run_coroutine_threadsafe(coro, loop):
        scheduled.append(loop)
        asyncio.run(coro)
        future = MagicMock()
        future.result.return_value = None
        return future

    monkeypatch.setattr("bot.asyncio.run_coroutine_threadsafe", fake_run_coroutine_threadsafe)
    monkeypatch.setattr("bot.Config.ADMIN_IDS", [111, 222])

    bot._send_telegram_admins("<b>Hello</b>")

    assert scheduled == [bot._telegram_loop]
    assert bot.app.bot.send_message.await_count == 2
    first_call = bot.app.bot.send_message.await_args_list[0]
    assert first_call.kwargs["chat_id"] == 111
    assert first_call.kwargs["parse_mode"] == "HTML"


@pytest.mark.asyncio
async def test_send_message_sanitizes_html_proactively_so_telegram_accepts_it():
    """
    Bug Critical #4 (audit 2026-06-07): _send_message must sanitize stray
    '<', '>', '&' before sending so Telegram doesn't reject the message with
    'Can't parse entities'. The sanitizer preserves whitelisted tags
    (<b>, <i>, etc) and escapes everything else.
    """
    bot = AdvancedCryptoBot.__new__(AdvancedCryptoBot)
    callback_message = SimpleNamespace(reply_text=AsyncMock())
    update = SimpleNamespace(
        callback_query=SimpleNamespace(
            edit_message_text=AsyncMock(),  # success path
            message=callback_message,
        ),
        message=None,
        effective_message=None,
    )

    # Input has stray '<' that previously broke Telegram parsing.
    await bot._send_message(update, None, "<b>bad < reason</b>", parse_mode="HTML")

    # The sanitizer should have escaped the stray '<' before send.
    update.callback_query.edit_message_text.assert_awaited_once()
    call = update.callback_query.edit_message_text.await_args
    sent_text = call.args[0] if call.args else call.kwargs.get("text")
    assert sent_text == "<b>bad &lt; reason</b>"
    assert call.kwargs["parse_mode"] == "HTML"
    # No fallback path needed because sanitizer prevented the error.
    callback_message.reply_text.assert_not_awaited()


@pytest.mark.asyncio
async def test_send_message_retries_with_html_escaped_text_when_parse_fails():
    """Legacy fallback path: even if sanitizer misses something, the
    'parse entities' fallback still triggers when Telegram rejects."""
    bot = AdvancedCryptoBot.__new__(AdvancedCryptoBot)
    html_error = Exception("Can't parse entities: can't find end of the entity")
    callback_message = SimpleNamespace(reply_text=AsyncMock(side_effect=[html_error, None]))
    update = SimpleNamespace(
        callback_query=SimpleNamespace(
            edit_message_text=AsyncMock(side_effect=Exception("message is not modified")),
            message=callback_message,
        ),
        message=None,
        effective_message=None,
    )

    # Pass already-sanitized text that still triggers a Telegram error
    # (e.g. weird unicode entity); the fallback should escape and retry.
    await bot._send_message(update, None, "<b>safe text</b>", parse_mode="HTML")

    assert callback_message.reply_text.await_count == 2
    second = callback_message.reply_text.await_args_list[1]
    # Second call uses fully html-escaped text — that's the core safety guarantee.
    assert second.args[0] == "&lt;b&gt;safe text&lt;/b&gt;"


def test_run_on_telegram_loop_returns_false_without_initialized_loop(monkeypatch):
    bot = AdvancedCryptoBot.__new__(AdvancedCryptoBot)
    bot.app = None
    bot._telegram_loop = None

    async def _sample():
        return None

    assert bot._run_on_telegram_loop(_sample()) is False
