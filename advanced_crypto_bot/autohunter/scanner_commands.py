#!/usr/bin/env python3
# Tujuan: Telegram command handlers untuk pair scanner — /top_volume, /top_movers, /scan_pairs.
# Caller: bot.AdvancedCryptoBot via register_scanner_handlers(bot, app).
# Dependensi: autohunter.pair_scanner, telegram.ext.CommandHandler.
# Main Functions: top_volume_cmd, top_movers_cmd, scan_pairs_cmd, register_scanner_handlers.
# Side Effects: Send Telegram message, opsional auto-add ke watchlist.
"""Telegram commands buat ngecek + auto-promote pair dari Indodax.

Commands yang didaftarkan:

- `/top_volume [N]` — top N pair berdasar volume IDR 24 jam (default 15)
- `/top_movers [N]` — top N gainers (momentum), default 10
- `/top_losers [N]` — top N losers, default 10
- `/scan_pairs [add]` — gabung top volume + top movers, opsi `add` =
  auto-add yang belum ada ke watchlist user.

Format output: pesan Telegram HTML compact.
"""
from __future__ import annotations

import logging
from telegram import Update
from telegram.ext import CommandHandler, ContextTypes

from autohunter.pair_scanner import (
    build_watchlist_recommendation,
    scan_top_movers,
    scan_top_volume,
)

logger = logging.getLogger("crypto_bot")


# ─── Formatters ──────────────────────────────────────────────────────────────


def _fmt_price(value):
    if value is None or value <= 0:
        return "—"
    if value >= 1e9:
        return f"{value/1e9:.2f}B"
    if value >= 1e6:
        return f"{value/1e6:.2f}M"
    if value >= 1e3:
        return f"{value:,.0f}".replace(",", ".")
    if value >= 1:
        return f"{value:.2f}"
    return f"{value:.6f}"


def _fmt_volume(value):
    if not value or value <= 0:
        return "—"
    if value >= 1e12:
        return f"Rp{value/1e12:.1f}T"
    if value >= 1e9:
        return f"Rp{value/1e9:.1f}B"
    if value >= 1e6:
        return f"Rp{value/1e6:.0f}M"
    return f"Rp{value:,.0f}".replace(",", ".")


def _fmt_change(value):
    if value is None:
        return "—"
    sign = "+" if value >= 0 else ""
    emoji = "🟢" if value > 0 else ("🔴" if value < 0 else "⚪")
    return f"{emoji} {sign}{value:.2f}%"


def _badges_label(badges: list[str]) -> str:
    if not badges:
        return ""
    icons = []
    for b in badges:
        if b == "PUMPING":
            icons.append("🚀")
        elif b == "TOP_GAINER":
            icons.append("📈")
        elif b == "TOP_LOSER":
            icons.append("📉")
        elif b == "TOP_VOLUME":
            icons.append("💰")
    return "".join(icons)


def _format_pair_line(rank: int, snap, show_volume=True) -> str:
    """One line per pair untuk Telegram message."""
    sym = snap.pair.replace("idr", "").upper()
    price = _fmt_price(snap.last)
    change = _fmt_change(snap.change_percent)
    badges = _badges_label(snap.badges)
    if show_volume:
        vol = _fmt_volume(snap.volume_idr)
        return f"<code>{rank:>2}.</code> <b>{sym}</b> {badges}\n    {price} · {change} · vol {vol}"
    return f"<code>{rank:>2}.</code> <b>{sym}</b> {badges} · {price} · {change}"


# ─── Command implementations ─────────────────────────────────────────────────


async def top_volume_cmd(bot, update: Update, context: ContextTypes.DEFAULT_TYPE):
    """`/top_volume [N]` — top N pair berdasar volume IDR 24h."""
    try:
        limit = int(context.args[0]) if context.args else 15
        limit = max(1, min(limit, 30))
    except (ValueError, IndexError):
        limit = 15

    try:
        results = scan_top_volume(bot.indodax, limit=limit)
    except Exception as e:
        logger.error(f"top_volume_cmd failed: {e}")
        await update.message.reply_text("⚠️ Gagal scan Indodax. Coba lagi nanti.")
        return

    if not results:
        await update.message.reply_text("Tidak ada pair yang lolos filter volume minimum.")
        return

    lines = [f"💰 <b>TOP {len(results)} VOLUME — Indodax IDR 24h</b>\n"]
    for s in results:
        lines.append(_format_pair_line(s.rank, s))
    lines.append(f"\n<i>Cache 60s · /scan_pairs untuk auto-add</i>")
    await update.message.reply_text("\n".join(lines), parse_mode="HTML")


async def top_movers_cmd(bot, update: Update, context: ContextTypes.DEFAULT_TYPE):
    """`/top_movers [N]` — top N gainers (momentum + likuiditas score)."""
    try:
        limit = int(context.args[0]) if context.args else 10
        limit = max(1, min(limit, 25))
    except (ValueError, IndexError):
        limit = 10

    try:
        results = scan_top_movers(bot.indodax, limit=limit, direction="up")
    except Exception as e:
        logger.error(f"top_movers_cmd failed: {e}")
        await update.message.reply_text("⚠️ Gagal scan Indodax.")
        return

    if not results:
        await update.message.reply_text("Tidak ada gainers yang lolos filter likuiditas.")
        return

    lines = [f"🚀 <b>TOP {len(results)} GAINERS — Momentum 24h</b>\n"]
    for s in results:
        lines.append(_format_pair_line(s.rank, s))
    lines.append(
        f"\n<i>Score = change% + dekat-puncak + likuiditas - spread penalty.</i>"
    )
    await update.message.reply_text("\n".join(lines), parse_mode="HTML")


async def top_losers_cmd(bot, update: Update, context: ContextTypes.DEFAULT_TYPE):
    """`/top_losers [N]` — top N losers (downward momentum)."""
    try:
        limit = int(context.args[0]) if context.args else 10
        limit = max(1, min(limit, 25))
    except (ValueError, IndexError):
        limit = 10

    try:
        results = scan_top_movers(bot.indodax, limit=limit, direction="down")
    except Exception as e:
        logger.error(f"top_losers_cmd failed: {e}")
        await update.message.reply_text("⚠️ Gagal scan Indodax.")
        return

    if not results:
        await update.message.reply_text("Tidak ada losers yang lolos filter likuiditas.")
        return

    lines = [f"📉 <b>TOP {len(results)} LOSERS — 24h</b>\n"]
    for s in results:
        lines.append(_format_pair_line(s.rank, s))
    await update.message.reply_text("\n".join(lines), parse_mode="HTML")


async def scan_pairs_cmd(bot, update: Update, context: ContextTypes.DEFAULT_TYPE):
    """`/scan_pairs [add]` — rekomendasi watchlist gabungan.

    Tanpa argumen: tampilkan rekomendasi (read-only).
    Dengan `add`: auto-add ke watchlist user yang belum ada.
    """
    user_id = update.effective_user.id
    do_add = bool(context.args) and context.args[0].lower() in {"add", "yes", "ya"}

    try:
        existing: set = set()
        try:
            existing_pairs = bot.subscribers.get(user_id, [])
            existing = {str(p).replace("/", "").replace("_", "").lower() for p in existing_pairs}
        except Exception:
            pass

        results = build_watchlist_recommendation(
            bot.indodax,
            top_volume_limit=15,
            top_mover_limit=10,
            exclude=existing if not do_add else set(),  # kalau do_add, kasih lihat semuanya
        )
    except Exception as e:
        logger.error(f"scan_pairs_cmd failed: {e}")
        await update.message.reply_text("⚠️ Gagal scan Indodax.")
        return

    if not results:
        await update.message.reply_text("Tidak ada rekomendasi pair baru. Watchlist sudah lengkap.")
        return

    added = []
    skipped = []
    if do_add:
        for s in results:
            if s.pair in existing:
                skipped.append(s.pair)
                continue
            try:
                # Add ke watchlist user (sync ke DB)
                if user_id not in bot.subscribers:
                    bot.subscribers[user_id] = []
                if s.pair not in bot.subscribers[user_id]:
                    bot.subscribers[user_id].append(s.pair)
                # Sync ke DB kalau ada helper
                try:
                    from bot_parts.state_sync import sync_watchlist_to_db
                    sync_watchlist_to_db(bot, user_id, s.pair)
                except Exception as sync_err:
                    logger.debug(f"sync_watchlist_to_db skipped: {sync_err}")
                added.append(s.pair.replace("idr", "").upper())
            except Exception as add_err:
                logger.warning(f"Failed to add {s.pair}: {add_err}")

    lines = [f"🎯 <b>WATCHLIST RECOMMENDATION</b>\n"]
    for s in results:
        prefix = ""
        if do_add and s.pair.replace("idr", "").upper() in added:
            prefix = "✅ "
        elif do_add and s.pair in skipped:
            prefix = "⏭️ "
        lines.append(prefix + _format_pair_line(s.rank, s))

    if do_add:
        lines.append(
            f"\n<b>Hasil:</b> {len(added)} pair ditambahkan, {len(skipped)} sudah ada."
        )
    else:
        lines.append("\n<i>Pakai <code>/scan_pairs add</code> untuk auto-tambah ke watchlist.</i>")

    await update.message.reply_text("\n".join(lines), parse_mode="HTML")


# ─── Register ────────────────────────────────────────────────────────────────


def register_scanner_handlers(bot, app):
    """Daftarkan semua scanner commands ke Telegram app."""

    async def _top_volume(update, context):
        await top_volume_cmd(bot, update, context)

    async def _top_movers(update, context):
        await top_movers_cmd(bot, update, context)

    async def _top_losers(update, context):
        await top_losers_cmd(bot, update, context)

    async def _scan_pairs(update, context):
        await scan_pairs_cmd(bot, update, context)

    app.add_handler(CommandHandler("top_volume", _top_volume))
    app.add_handler(CommandHandler("top_movers", _top_movers))
    app.add_handler(CommandHandler("top_losers", _top_losers))
    app.add_handler(CommandHandler("scan_pairs", _scan_pairs))

    logger.info("✅ Pair scanner commands registered (4 commands)")
