# Tujuan: Helper keyboard Telegram yang sebelumnya tertanam di bot.py.
# Caller: bot.AdvancedCryptoBot dan test UI/quick actions.
# Dependensi: python-telegram-bot, core.config.Config.
# Main Functions: build_quick_keyboard, build_android_reply_keyboard, build_menu_panel_keyboard.
# Side Effects: none.

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardMarkup

from core.config import Config


def _dashboard_url(dashboard_url=None):
    """Return explicit dashboard URL or configured default."""
    return Config.DASHBOARD_URL if dashboard_url is None else dashboard_url


def build_quick_keyboard(is_admin=False, dashboard_url=None):
    """Build app-like Telegram quick-action buttons."""
    keyboard = [
        [
            InlineKeyboardButton("📊 Market", callback_data="market_scan_quick"),
            InlineKeyboardButton("💼 Portfolio", callback_data="portfolio_quick"),
        ],
        [
            InlineKeyboardButton("🔔 Alerts", callback_data="notifications_quick"),
            InlineKeyboardButton("📈 Signal", callback_data="signals_quick"),
        ],
        [
            InlineKeyboardButton("💰 Price", callback_data="price_quick"),
            InlineKeyboardButton("📘 Panduan", callback_data="help"),
        ],
    ]

    url = _dashboard_url(dashboard_url)
    if url:
        keyboard.append([InlineKeyboardButton("📊 Dashboard", url=url)])

    if is_admin:
        keyboard.append([
            InlineKeyboardButton("🤖 Auto-Trade", callback_data="autotrade_quick"),
            InlineKeyboardButton("⚙️ Admin", callback_data="admin_panel"),
        ])

    return InlineKeyboardMarkup(keyboard)


def build_android_reply_keyboard(is_admin=False):
    """Build persistent fallback keyboard aligned with /help quick actions."""
    keyboard = [
        ["📊 Market", "💼 Portfolio"],
        ["🔔 Alerts", "📈 Signal"],
        ["💰 Price", "📘 Panduan"],
    ]
    if is_admin:
        keyboard.append(["🤖 Auto-Trade", "⚙️ Admin"])

    return ReplyKeyboardMarkup(
        keyboard,
        resize_keyboard=True,
        is_persistent=True,
        input_field_placeholder="Pilih aksi cepat atau ketik pair, contoh btcidr",
    )


def build_menu_panel_keyboard(section, is_admin=False, dashboard_url=None):
    """Build contextual menu buttons for each main panel."""
    section = (section or "").lower()
    if section == "market":
        keyboard = [
            [
                InlineKeyboardButton("🔎 Scan", callback_data="market_scan_quick"),
                InlineKeyboardButton("📈 Signal", callback_data="signal_quick"),
            ],
            [InlineKeyboardButton("💰 Price", callback_data="price_quick")],
        ]
    elif section == "portfolio":
        keyboard = [
            [
                InlineKeyboardButton("💰 Balance", callback_data="balance_quick"),
                InlineKeyboardButton("💼 Portfolio", callback_data="portfolio_quick"),
            ],
            [InlineKeyboardButton("📊 Pair Stats", callback_data="pair_stats_quick")],
        ]
    elif section == "alerts":
        keyboard = [
            [InlineKeyboardButton("🔔 Notifications", callback_data="notifications_quick")],
            [InlineKeyboardButton("➕ Watch Pair", callback_data="watch_quick")],
        ]
    elif section == "settings":
        if is_admin:
            keyboard = [
                [
                    InlineKeyboardButton("🤖 Auto-Trade", callback_data="autotrade_quick"),
                    InlineKeyboardButton("⚙️ Status", callback_data="status_quick"),
                ],
                [InlineKeyboardButton("📘 Help", callback_data="help")],
            ]
        else:
            keyboard = [[InlineKeyboardButton("📘 Help", callback_data="help")]]
    else:
        keyboard = []

    url = _dashboard_url(dashboard_url)
    if url:
        keyboard.append([InlineKeyboardButton("📊 Dashboard", url=url)])
    keyboard.append([InlineKeyboardButton("⬅️ Menu Utama", callback_data="menu_home")])
    return InlineKeyboardMarkup(keyboard)
