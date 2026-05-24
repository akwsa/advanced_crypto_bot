# Tujuan: Helper panel admin Telegram yang sebelumnya tertanam di bot.py.
# Caller: bot.AdvancedCryptoBot._show_admin_panel dan test UI/quick actions.
# Dependensi: python-telegram-bot.
# Main Functions: build_admin_panel_text, build_admin_panel_markup.
# Side Effects: none.

from telegram import InlineKeyboardButton, InlineKeyboardMarkup


def build_admin_panel_text():
    """Build admin maintenance panel text."""
    return (
        "⚙️ <b>Admin Panel</b>\n\n"
        "Panel ini untuk cek kesehatan bot dan menjalankan maintenance.\n\n"
        "• <code>/status</code> status sistem\n"
        "• <code>/autotrade_status</code> status auto-trade\n"
        "• <code>/retrain</code> latih ulang model ML\n"
        "• <code>/backtest btcidr 30</code> uji strategi\n\n"
        "Gunakan Restart hanya kalau bot macet atau setelah deploy patch."
    )


def build_admin_panel_markup():
    """Build admin maintenance panel inline keyboard."""
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("⚙️ Status", callback_data="status_quick"),
            InlineKeyboardButton("📊 Logs", callback_data="admin_logs"),
        ],
        [
            InlineKeyboardButton("🤖 Retrain", callback_data="admin_retrain"),
            InlineKeyboardButton("📈 Backtest", callback_data="admin_backtest"),
        ],
        [InlineKeyboardButton("⬅️ Menu Utama", callback_data="menu_home")],
    ])
