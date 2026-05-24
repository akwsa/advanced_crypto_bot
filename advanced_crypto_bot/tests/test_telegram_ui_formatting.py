import unittest
from datetime import datetime

import pandas as pd

from bot_parts.charts import build_signal_chart_image
from bot_parts.command_texts import (
    TELEGRAM_BOT_COMMANDS,
    build_help_html,
    build_main_menu_html,
    build_menu_markdown,
    build_menu_section_html,
    build_start_html,
)
from signals.signal_formatter import format_market_scan_signal, format_signal_message_html


class TestTelegramUiFormatting(unittest.TestCase):
    def test_help_is_compact_and_plain_language(self):
        text = build_help_html()

        self.assertIn("Panduan Singkat", text)
        self.assertIn("/autotrade dryrun", text)
        self.assertIn("Aturan aman", text)
        self.assertNotIn("COMPLETE USER GUIDE", text)
        self.assertLess(len(text), 2500)

    def test_start_message_shows_safe_first_steps(self):
        text = build_start_html(
            first_name="Budi",
            is_admin=True,
            is_trading=False,
            is_dry_run=True,
            watch_count=2,
            autotrade_count=1,
            dashboard_ready=True,
        )

        self.assertIn("Halo, Budi", text)
        self.assertIn("Mode uang: <b>Simulasi aman</b>", text)
        self.assertIn("/watch btcidr, ethidr", text)
        self.assertIn("/autotrade dryrun", text)

    def test_menu_keeps_core_commands_easy_to_find(self):
        text = build_menu_markdown()

        self.assertIn("Menu Cepat", text)
        self.assertIn("`/signal btcidr`", text)
        self.assertIn("`/balance`", text)
        self.assertIn("`/smarthunter on`", text)

    def test_main_menu_has_modern_sections(self):
        text = build_main_menu_html(
            is_admin=True,
            is_trading=True,
            is_dry_run=True,
            watch_count=3,
            autotrade_count=2,
            dashboard_ready=True,
        )

        self.assertIn("Menu Utama", text)
        self.assertIn("Auto-trade: <b>ON</b>", text)
        self.assertIn("Watchlist: <code>3</code> pair", text)
        self.assertIn("Dashboard: <b>Siap</b>", text)

    def test_menu_sections_cover_requested_navigation(self):
        for section, label in [
            ("market", "Market"),
            ("portfolio", "Portfolio"),
            ("alerts", "Alerts"),
            ("settings", "Settings"),
        ]:
            text = build_menu_section_html(section, is_admin=True, dashboard_ready=True)
            self.assertIn(label, text)

    def test_native_telegram_commands_include_core_navigation(self):
        commands = {command for command, _ in TELEGRAM_BOT_COMMANDS}

        self.assertIn("start", commands)
        self.assertIn("dashboard", commands)
        self.assertIn("signal", commands)
        self.assertIn("settings", commands)
        self.assertIn("help", commands)
        self.assertIn("menu", commands)
        self.assertIn("signals", commands)
        self.assertIn("price", commands)
        self.assertIn("scan", commands)
        self.assertIn("balance", commands)
        self.assertIn("portfolio", commands)
        self.assertIn("watch", commands)
        self.assertIn("autotrade", commands)
        self.assertIn("status", commands)

    def test_native_telegram_commands_include_scalper_prefix(self):
        """Pastikan command scalper /s_* muncul di native Telegram menu (autocomplete saat ketik /s_)."""
        commands = {command for command, _ in TELEGRAM_BOT_COMMANDS}

        expected_scalper = {
            "s_menu",
            "s_pair",
            "s_pairs",
            "s_analisa",
            "s_buy",
            "s_sell",
            "s_sltp",
            "s_cancel",
            "s_info",
            "s_posisi",
            "s_portfolio",
            "s_riwayat",
            "s_signal_summary",
            "s_sync",
            "s_reset",
            "s_close_all",
            "s_refresh",
        }

        missing = expected_scalper - commands
        self.assertFalse(
            missing,
            f"Scalper commands hilang dari TELEGRAM_BOT_COMMANDS: {sorted(missing)}",
        )

    def test_native_telegram_commands_format_valid(self):
        """Telegram BotCommand: command max 32 char [a-z0-9_], description max 256 char, tanpa duplikat."""
        seen = set()
        for command, description in TELEGRAM_BOT_COMMANDS:
            self.assertNotIn(command, seen, f"Command duplikat: {command}")
            seen.add(command)
            self.assertLessEqual(len(command), 32, f"Command terlalu panjang: {command}")
            self.assertRegex(command, r"^[a-z][a-z0-9_]*$", f"Command tidak valid: {command}")
            self.assertTrue(description, f"Deskripsi kosong untuk: {command}")
            self.assertLessEqual(len(description), 256, f"Deskripsi >256 char: {command}")

        self.assertLessEqual(len(TELEGRAM_BOT_COMMANDS), 100)

    def test_signal_chart_image_can_be_built(self):
        df = pd.DataFrame({"close": [100 + i for i in range(30)]})
        image = build_signal_chart_image("btcidr", df, {"recommendation": "BUY"})

        self.assertIsNotNone(image)
        self.assertTrue(image.getbuffer().nbytes > 1000)

    def test_signal_chart_image_skips_flat_synthetic_data(self):
        df = pd.DataFrame({"close": [2145.0] * 80})
        image = build_signal_chart_image("hypeidr", df, {"recommendation": "BUY"})

        self.assertIsNone(image)

    def test_signal_html_is_simple_and_escapes_dynamic_text(self):
        signal = {
            "pair": "btcidr",
            "recommendation": "BUY",
            "price": 1000000000,
            "ml_confidence": 0.78,
            "combined_strength": 0.42,
            "timestamp": datetime(2026, 4, 24, 20, 0, 0),
            "reason": "RSI < 30 & MACD > signal",
            "indicators": {
                "rsi": "OVERSOLD",
                "macd": "BULLISH",
                "ma_trend": "BULLISH",
                "bb": "NEUTRAL",
                "volume": "HIGH",
            },
        }

        text = format_signal_message_html(signal)

        # Implementation uses Title Case for readability (see test_signal_formatter_telegram_display.py).
        self.assertIn("Keputusan: Beli", text)
        self.assertNotIn("Keputusan: BELI", text)
        self.assertIn("Saran:", text)
        self.assertIn("Keyakinan bot", text)
        self.assertIn("RSI &lt; 30 &amp; MACD &gt; signal", text)
        self.assertNotIn("Signal Alert", text)
        self.assertNotIn("ML Raw", text)
        self.assertNotIn("<b>", text)

    def test_market_scan_signal_uses_plain_indonesian_labels(self):
        text = format_market_scan_signal({
            "pair": "ethidr",
            "type": "STRONG_SELL",
            "confidence": 0.91,
            "price": 50000000,
            "reason": "price < support",
        })

        # Implementation uses Title Case for readability (see test_signal_formatter_telegram_display.py).
        self.assertIn("Keputusan: Jual kuat", text)
        self.assertNotIn("Keputusan: JUAL KUAT", text)
        self.assertIn("Harga:", text)
        self.assertIn("Keyakinan:", text)
        self.assertIn("price &lt; support", text)
        self.assertNotIn("<b>", text)


if __name__ == "__main__":
    unittest.main()
