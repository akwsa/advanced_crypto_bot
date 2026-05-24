# Tujuan: Test Telegram access control default-deny whitelist + invite registration flow.
# Caller: unittest focused security policy.
# Dependensi: bot.AdvancedCryptoBot, core.config.Config, core.database.Database.
# Side Effects: Tidak ada; DB/Config dipatch.

import sys
import unittest
from dataclasses import dataclass
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, patch

from bot import AdvancedCryptoBot
from core.config import Config


class TestTelegramAccessControl(unittest.IsolatedAsyncioTestCase):
    def _bot(self, admin_ids=None, allowed_user_ids=None, active_db_users=None):
        bot = AdvancedCryptoBot.__new__(AdvancedCryptoBot)
        bot.allowed_user_ids = set(admin_ids or []) | set(allowed_user_ids or [])
        bot.db = SimpleNamespace(
            get_active_telegram_users=Mock(
                return_value=active_db_users if active_db_users is not None else []
            ),
            upsert_telegram_user=Mock(),
            register_telegram_user=Mock(),
        )
        # _send_message and _deny_unauthorized helpers awaited — use AsyncMock by default.
        bot._send_message = AsyncMock()
        return bot

    def _update(self, user_id, callback_query=None, chat_type="private"):
        user = SimpleNamespace(id=user_id, username="testuser", first_name="Test")
        chat = SimpleNamespace(type=chat_type)
        # callback_query.answer is awaited inside _deny_unauthorized — must be AsyncMock.
        cbq = SimpleNamespace(answer=AsyncMock()) if callback_query else None
        return SimpleNamespace(
            effective_user=user,
            effective_chat=chat,
            callback_query=cbq,
            effective_message=SimpleNamespace(reply_text=AsyncMock()),
        )

    # ------------------------------------------------------------------ _is_authorized

    def test_admin_always_authorized(self):
        bot = self._bot(admin_ids=[42])
        with patch.object(Config, "ADMIN_IDS", [42]):
            self.assertTrue(bot._is_authorized(42))
            self.assertTrue(bot._is_authorized(42, admin_only=True))

    def test_allowed_user_authorized(self):
        bot = self._bot(allowed_user_ids=[99])
        with patch.object(Config, "ADMIN_IDS", [42]):
            self.assertTrue(bot._is_authorized(99))

    def test_allowed_user_not_admin_authorized_for_user_commands(self):
        bot = self._bot(allowed_user_ids=[99])
        with patch.object(Config, "ADMIN_IDS", [42]):
            self.assertTrue(bot._is_authorized(99, admin_only=False))
            self.assertFalse(bot._is_authorized(99, admin_only=True))

    def test_unknown_user_denied(self):
        bot = self._bot(admin_ids=[42], allowed_user_ids=[55])
        with patch.object(Config, "ADMIN_IDS", [42]):
            self.assertFalse(bot._is_authorized(888))
            self.assertFalse(bot._is_authorized(888, admin_only=True))

    # ------------------------------------------------------------- require_authorized

    async def test_require_authorized_allows_registered_user(self):
        bot = self._bot(admin_ids=[42])
        with patch.object(Config, "ADMIN_IDS", [42]):
            update = self._update(42)
            context = SimpleNamespace()
            result = await bot._require_authorized(update, context)
        self.assertTrue(result)

    async def test_require_authorized_denies_unknown_private_chat(self):
        bot = self._bot(admin_ids=[42])
        with patch.object(Config, "ADMIN_IDS", [42]):
            sent = []
            bot._send_message = AsyncMock(
                side_effect=lambda update, context, text, **kw: sent.append(text)
            )
            update = self._update(999)
            context = SimpleNamespace()
            result = await bot._require_authorized(update, context)
        self.assertFalse(result)
        self.assertTrue(any("Access denied" in s for s in sent))

    async def test_require_authorized_denies_callback_query(self):
        bot = self._bot(admin_ids=[42])
        with patch.object(Config, "ADMIN_IDS", [42]):
            sent = []
            bot._send_message = AsyncMock(
                side_effect=lambda update, context, text, **kw: sent.append(text)
            )
            update = self._update(999, callback_query=True)
            context = SimpleNamespace()
            result = await bot._require_authorized(update, context)
        self.assertFalse(result)
        update.callback_query.answer.assert_awaited_once()
        self.assertTrue(any("Access denied" in s for s in sent))

    # ----------------------------------------------------- group / channel rejected

    async def test_require_authorized_denies_group_chat(self):
        bot = self._bot(admin_ids=[42])
        with patch.object(Config, "ADMIN_IDS", [42]):
            sent = []
            bot._send_message = AsyncMock(
                side_effect=lambda update, context, text, **kw: sent.append(text)
            )
            update = self._update(42, chat_type="group")
            context = SimpleNamespace()
            result = await bot._require_authorized(update, context)
        self.assertFalse(result)

    # --------------------------------------------------------------- invite register

    async def test_register_access_success(self):
        bot = self._bot(admin_ids=[42])
        with patch.object(Config, "ADMIN_IDS", [42], create=True), \
             patch.object(Config, "TELEGRAM_INVITE_CODE", "secret123", create=True):
            sent = []
            bot._send_message = AsyncMock(
                side_effect=lambda update, context, text, **kw: sent.append(text)
            )
            context = SimpleNamespace(args=["secret123"])
            update = self._update(99)
            await bot.register_access(update, context)
        self.assertIn(99, bot.allowed_user_ids)
        bot.db.register_telegram_user.assert_called_once()
        self.assertTrue(any("berhasil" in s for s in sent))

    async def test_register_access_admin_no_invite_needed(self):
        bot = self._bot(admin_ids=[42])
        with patch.object(Config, "ADMIN_IDS", [42], create=True):
            sent = []
            bot._send_message = AsyncMock(
                side_effect=lambda update, context, text, **kw: sent.append(text)
            )
            context = SimpleNamespace(args=[])
            update = self._update(42)
            await bot.register_access(update, context)
        self.assertIn(42, bot.allowed_user_ids)
        self.assertTrue(any("sudah terdaftar" in s for s in sent))

    async def test_register_access_invalid_code(self):
        bot = self._bot(admin_ids=[42])
        with patch.object(Config, "ADMIN_IDS", [42], create=True), \
             patch.object(Config, "TELEGRAM_INVITE_CODE", "secret123", create=True):
            sent = []
            bot._send_message = AsyncMock(
                side_effect=lambda update, context, text, **kw: sent.append(text)
            )
            context = SimpleNamespace(args=["wrong"])
            update = self._update(99)
            await bot.register_access(update, context)
        self.assertNotIn(99, bot.allowed_user_ids)
        self.assertTrue(any("tidak valid" in s for s in sent))

    # --------------------------------------------------------------- DB persistence

    def test_allowed_user_ids_merged_from_config_and_db(self):
        bot = AdvancedCryptoBot.__new__(AdvancedCryptoBot)
        bot.db = SimpleNamespace(
            get_active_telegram_users=Mock(return_value=[77, 88]),
            upsert_telegram_user=Mock(),
            register_telegram_user=Mock(),
        )
        with patch.object(Config, "ALLOWED_USER_IDS", [22, 33], create=True), \
             patch.object(Config, "ADMIN_IDS", [42]):
            bot.allowed_user_ids = set(getattr(Config, "ALLOWED_USER_IDS", [])) | set(getattr(Config, "ADMIN_IDS", []))
            bot._load_telegram_access_control()
        self.assertEqual(bot.allowed_user_ids, {22, 33, 42, 77, 88})


if __name__ == "__main__":
    unittest.main()
