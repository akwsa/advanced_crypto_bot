#!/usr/bin/env python3
# Tujuan: Formatter pesan signal Telegram Markdown/HTML.
# Caller: bot.py, signal queue, notification flow.
# Dependensi: Utils, Config, signal payloads.
# Main Functions: format_signal_message; format_signal_message_html.
# Side Effects: No side effects.
"""Signal formatting helpers extracted from bot.py."""

from datetime import datetime
from html import escape

from core.utils import Utils


def _recommendation_theme(recommendation):
    """Return emoji theme metadata for signal recommendation."""
    return {
        "STRONG_BUY": {
            "accent": "🟢",
            "header": "🟩🟩🟩",
            "badge": "BELI KUAT",
            "action": "Boleh entry bertahap. Tetap pasang batas rugi.",
            "trend_icon": "🚀",
            "gain_icon": "✅",
            "momentum": "🔥",
            "plain": "Peluang beli kuat",
        },
        "BUY": {
            "accent": "🟢",
            "header": "🟩🟩",
            "badge": "BELI",
            "action": "Boleh pantau entry kecil. Jangan kejar harga yang sudah lari.",
            "trend_icon": "📈",
            "gain_icon": "✅",
            "momentum": "💪",
            "plain": "Peluang beli",
        },
        "HOLD": {
            "accent": "🟡",
            "header": "🟨🟨",
            "badge": "TUNGGU",
            "action": "Belum ada peluang bersih. Lebih aman menunggu.",
            "trend_icon": "➡️",
            "gain_icon": "⚪",
            "momentum": "⏳",
            "plain": "Tunggu dulu",
        },
        "SELL": {
            "accent": "🔴",
            "header": "🟥🟥",
            "badge": "JUAL",
            "action": "Pertimbangkan amankan profit atau kurangi posisi.",
            "trend_icon": "📉",
            "gain_icon": "⚠️",
            "momentum": "💨",
            "plain": "Sinyal jual",
        },
        "STRONG_SELL": {
            "accent": "🔴",
            "header": "🟥🟥🟥",
            "badge": "JUAL KUAT",
            "action": "Hindari entry baru. Jika punya posisi, cek untuk keluar.",
            "trend_icon": "🔻",
            "gain_icon": "🚨",
            "momentum": "⛔",
            "plain": "Risiko turun kuat",
        },
    }.get(
        recommendation,
        {
            "accent": "⚪",
            "header": "⬜⬜",
            "badge": f"{recommendation}",
            "action": "Belum ada saran.",
            "trend_icon": "❓",
            "gain_icon": "❓",
            "momentum": "❓",
            "plain": "Belum jelas",
        },
    )


def _alert_marker(recommendation):
    """Return a compact colored marker for the alert title."""
    if recommendation in ["BUY", "STRONG_BUY"]:
        return "🟩"
    if recommendation in ["SELL", "STRONG_SELL"]:
        return "🟥"
    if recommendation == "HOLD":
        return "🟨"
    return "⬜"


def _display_badge(theme, signal=None):
    """Return a readable decision label for Telegram text (UPPER CASE)."""
    if signal is not None:
        display_rec = str(signal.get("display_recommendation") or "").upper()
        if display_rec == "PANTAU":
            return "PANTAU"
        if display_rec == "BELI_BERTAHAP":
            return "BELI BERTAHAP"
    return str(theme.get("badge", "")).upper()


def generate_strength_bar(strength):
    """Generate emoji-based strength bar for more consistent Telegram rendering."""
    strength = max(-1, min(1, strength))
    bar_length = int(abs(strength) * 10)
    empty_length = 10 - bar_length

    if strength > 0:
        bar = "🟩" * bar_length + "⬜" * empty_length
        return f"🟢 {bar}"
    if strength < 0:
        bar = "⬜" * empty_length + "🟥" * bar_length
        return f"🔴 {bar}"
    return f"⚪ {'⬜' * 10}"


def generate_strength_bar_html(strength):
    """Generate emoji-based strength bar for HTML Telegram messages."""
    return generate_strength_bar(strength)


def generate_strength_bar_plain(strength):
    """Generate classic block bar for compact metric display."""
    strength = max(-1, min(1, strength))
    bar_length = int(abs(strength) * 10)
    empty_length = 10 - bar_length

    if strength > 0:
        bar = "█" * bar_length + "░" * empty_length
    elif strength < 0:
        bar = "░" * empty_length + "█" * bar_length
    else:
        bar = "░" * 10
    return f"[{bar}]"


def _simple_strength_label(strength):
    if strength >= 0.55:
        return "naik kuat"
    if strength >= 0.20:
        return "mulai naik"
    if strength <= -0.55:
        return "turun kuat"
    if strength <= -0.20:
        return "mulai turun"
    return "netral"


def _format_volume_compact(value):
    """Format volume IDR menjadi compact: 2.5M, 1.2B, 500K, dsb."""
    if value is None or value == 0:
        return "—"  # Tampilkan "—" agar user tahu volume tidak tersedia
    value = float(value)
    if value <= 0:
        return "—"
    if value >= 1_000_000_000:
        v = value / 1_000_000_000
        return f"Rp{v:.1f}B".replace(".0B", "B")
    if value >= 1_000_000:
        v = value / 1_000_000
        return f"Rp{v:.1f}M".replace(".0M", "M")
    if value >= 1_000:
        v = value / 1_000
        return f"Rp{v:.0f}K"
    return f"Rp{value:,.0f}"


def _safe_text(value):
    if value is None:
        return "N/A"
    return escape(str(value))


def format_signal_message(signal):
    """Format signal into readable Telegram message (Markdown)."""
    indicators = signal.get("indicators", {})
    pair = signal.get("pair", "UNKNOWN")
    recommendation = signal.get("recommendation", "HOLD")
    price = signal.get("price", 0)
    ml_confidence = signal.get("ml_confidence", 0.5)
    ml_confidence_raw = signal.get("ml_confidence_raw", ml_confidence)
    combined_strength = signal.get("combined_strength", 0)
    timestamp = signal.get("timestamp", datetime.now())
    reason = signal.get("reason", "No analysis available")
    final_gate_source = signal.get("final_gate_source")
    theme = _recommendation_theme(recommendation)

    support_1 = signal.get("support_1", 0)
    resistance_1 = signal.get("resistance_1", 0)

    sr_section = ""
    if support_1 > 0 or resistance_1 > 0:
        sr_section = f"""
🎯 Support/Resistance:
• S: `{Utils.format_price(support_1)}`   • R: `{Utils.format_price(resistance_1)}`"""

    strength_bar = generate_strength_bar_plain(combined_strength)

    rsi_val = indicators.get("rsi", "N/A")
    macd_val = indicators.get("macd", "N/A")
    ma_val = indicators.get("ma_trend", "N/A")
    bb_val = indicators.get("bb", "N/A")
    vol_val = indicators.get("volume", "N/A")

    rsi_emoji = "🔴" if rsi_val == "OVERBOUGHT" else "🟢" if rsi_val == "OVERSOLD" else "⚪"
    macd_emoji = "🟢" if "BULLISH" in str(macd_val) else "🔴" if "BEARISH" in str(macd_val) else "⚪"
    ma_emoji = "🟢" if ma_val == "BULLISH" else "🔴" if ma_val == "BEARISH" else "⚪"
    bb_emoji = "🟢" if bb_val == "OVERSOLD" else "🔴" if bb_val == "OVERBOUGHT" else "⚪"
    alert_marker = _alert_marker(recommendation)
    trend_icon = theme.get('trend_icon', '📊')
    gain_icon = theme.get('gain_icon', '✅')
    momentum = theme.get('momentum', '💪')

    # Performance indicator based on combined strength
    perf_indicator = ""
    if combined_strength > 0.5:
        perf_indicator = f"{momentum} Dorongan naik kuat"
    elif combined_strength > 0.2:
        perf_indicator = f"{trend_icon} Mulai menguat"
    elif combined_strength < -0.5:
        perf_indicator = f"{momentum} Tekanan turun kuat"
    elif combined_strength < -0.2:
        perf_indicator = f"{trend_icon} Mulai melemah"
    else:
        perf_indicator = f"➡️ Netral"

    volume_label = _format_volume_compact(signal.get("volume_24h"))

    return f"""{trend_icon} Signal Alert — {alert_marker} {pair.upper()} {alert_marker}
Vol: {volume_label}
{_display_badge(theme, signal)} {gain_icon}
💡 Action: {theme['action']}
📊 {perf_indicator}

💰 Current Price: `{Utils.format_price(price)}` IDR

📊 Signal Metrics:
• Combined Strength: `{strength_bar}` `{combined_strength:+.2f}`
• ML Confidence (final): `{ml_confidence:.1%}`
• ML Raw (pre-adjust): `{ml_confidence_raw:.1%}`

📈 Technical Indicators:
{rsi_emoji} RSI (14): `{rsi_val}`
{macd_emoji} MACD: `{macd_val}`
{ma_emoji} MA Trend: `{ma_val}`
{bb_emoji} Bollinger: `{bb_val}`
⚪ Volume: `{vol_val}`
{sr_section}

📝 Analysis:
_{reason}_
⏰ `{timestamp.strftime('%H:%M:%S')}`
        """


def format_signal_message_html(signal):
    """Format signal into readable Telegram message (HTML)."""
    indicators = signal.get("indicators", {})
    pair = signal.get("pair", "UNKNOWN")
    recommendation = signal.get("recommendation", "HOLD")
    price = signal.get("price", 0)
    ml_confidence = signal.get("ml_confidence", 0.5)
    ml_confidence_raw = signal.get("ml_confidence_raw", ml_confidence)
    combined_strength = signal.get("combined_strength", 0)
    timestamp = signal.get("timestamp", datetime.now())
    reason = signal.get("reason", "No analysis available")
    final_gate_source = signal.get("final_gate_source")
    theme = _recommendation_theme(recommendation)

    support_1 = signal.get("support_1", 0)
    support_2 = signal.get("support_2", 0)
    resistance_1 = signal.get("resistance_1", 0)
    resistance_2 = signal.get("resistance_2", 0)
    price_zone = signal.get("price_zone", "UNKNOWN")
    rr_ratio = signal.get("risk_reward_ratio", 0)

    sr_section = ""
    if support_1 > 0 or resistance_1 > 0:
        s1 = Utils.format_price(support_1) if support_1 > 0 else '—'
        s2 = Utils.format_price(support_2) if support_2 > 0 else '—'
        r1 = Utils.format_price(resistance_1) if resistance_1 > 0 else '—'
        r2 = Utils.format_price(resistance_2) if resistance_2 > 0 else '—'
        sr_section = f"""
🎯 Support/Resistance:
• S1: <code>{s1}</code>   • S2: <code>{s2}</code>
• R1: <code>{r1}</code>   • R2: <code>{r2}</code>

📍 Zona Harga: {_safe_text(price_zone)}
⚖️ Risk/Reward: {rr_ratio:.2f}"""

    rsi_val = indicators.get("rsi", "N/A")
    macd_val = indicators.get("macd", "N/A")
    ma_val = indicators.get("ma_trend", "N/A")
    bb_val = indicators.get("bb", "N/A")
    vol_val = indicators.get("volume", "N/A")

    rsi_emoji = "🔴" if rsi_val == "OVERBOUGHT" else "🟢" if rsi_val == "OVERSOLD" else "⚪"
    macd_emoji = "🟢" if "BULLISH" in str(macd_val) else "🔴" if "BEARISH" in str(macd_val) else "⚪"
    ma_emoji = "🟢" if ma_val == "BULLISH" else "🔴" if ma_val == "BEARISH" else "⚪"
    bb_emoji = "🟢" if bb_val == "OVERSOLD" else "🔴" if bb_val == "OVERBOUGHT" else "⚪"
    alert_marker = _alert_marker(recommendation)

    strength_bar = generate_strength_bar_plain(combined_strength)
    confidence_pct = int(ml_confidence * 100)
    raw_confidence_pct = int(ml_confidence_raw * 100)

    signal_emoji = signal.get("signal_emoji", theme.get("trend_icon", "📊"))
    gain_icon = theme.get('gain_icon', '✅')
    momentum = theme.get('momentum', '💪')

    # Performance indicator based on combined strength
    perf_indicator = ""
    if combined_strength > 0.5:
        perf_indicator = f"{momentum} Dorongan naik kuat"
    elif combined_strength > 0.2:
        perf_indicator = f"{signal_emoji} Mulai menguat"
    elif combined_strength < -0.5:
        perf_indicator = f"{momentum} Tekanan turun kuat"
    elif combined_strength < -0.2:
        perf_indicator = f"{signal_emoji} Mulai melemah"
    else:
        perf_indicator = f"➡️ Netral"

    pair_text = _safe_text(pair.upper())
    volume_label = _format_volume_compact(signal.get("volume_24h"))
    volume_suffix = f"  Vol: {volume_label}"
    reason_text = _safe_text(reason)
<<<<<<< Updated upstream
=======
    # "Filter akhir" removed — info sudah ada di Catatan bot
>>>>>>> Stashed changes
    strength_label = _simple_strength_label(combined_strength)

    # ── Quant section (GARCH / VaR / ARIMA) ──────────────────────────────
    quant_section = ""
    garch_regime = signal.get("garch_regime")
    garch_vol = signal.get("garch_current_vol")
    var_hist = signal.get("var_historical")
    cvar_hist = signal.get("cvar_historical")
    arima_dir = signal.get("arima_direction")
    arima_pct = signal.get("arima_change_pct")

    if any(v is not None for v in [garch_regime, var_hist, arima_dir]):
        regime_emoji = {"LOW": "🟢", "MEDIUM": "🟡", "HIGH": "🟠", "EXTREME": "🔴"}.get(garch_regime, "⚪")
        arima_emoji = {"UP": "📈", "DOWN": "📉", "FLAT": "➡️"}.get(arima_dir, "❓")
        parts = []
        if garch_regime and garch_vol is not None:
            parts.append(f"{regime_emoji} Volatilitas: <code>{garch_vol:.2f}%</code> [{garch_regime}]")
        if var_hist is not None and cvar_hist is not None:
            parts.append(f"⚠️ VaR 95%: <code>{var_hist:.2f}%</code> | CVaR: <code>{cvar_hist:.2f}%</code>")
        if arima_dir and arima_pct is not None:
            parts.append(f"{arima_emoji} ARIMA: <code>{arima_pct:+.2f}%</code> [{arima_dir}]")
        if parts:
            quant_section = "\n\n📐 Quant Analysis\n" + "\n".join(parts)
    # ── End quant section ─────────────────────────────────────────────────

<<<<<<< Updated upstream
    return f"""{signal_emoji} {pair_text}{volume_suffix}
=======
    # Volume info for header
    volume_24h = signal.get("volume_24h") or indicators.get("volume_24h")
    volume_text = ""
    if volume_24h is not None:
        try:
            vol_num = float(volume_24h)
            if vol_num >= 1_000_000_000:
                volume_text = f" | Vol: {vol_num/1_000_000_000:.1f}B"
            elif vol_num >= 1_000_000:
                volume_text = f" | Vol: {vol_num/1_000_000:.1f}M"
            elif vol_num >= 1_000:
                volume_text = f" | Vol: {vol_num/1_000:.0f}K"
            else:
                volume_text = f" | Vol: {vol_num:.0f}"
        except (TypeError, ValueError):
            pass

    return f"""{signal_emoji} {pair_text}{volume_text}
>>>>>>> Stashed changes
Keputusan: {_display_badge(theme, signal)} {gain_icon}

Saran: {escape(theme['action'])}
Harga: <code>{Utils.format_price(price)}</code> IDR

Ringkasan
• Keyakinan bot: <code>{confidence_pct}%</code>
• Tenaga sinyal: <code>{combined_strength:+.2f}</code> ({strength_label})
• Arah cepat: {perf_indicator}

Indikator utama
{rsi_emoji} RSI: <code>{_safe_text(rsi_val)}</code>   {macd_emoji} MACD: <code>{_safe_text(macd_val)}</code>
{ma_emoji} MA: <code>{_safe_text(ma_val)}</code>   {bb_emoji} BB: <code>{_safe_text(bb_val)}</code>
⚪ Vol: <code>{_safe_text(vol_val)}</code>
{sr_section}{quant_section}

Catatan bot
<i>{reason_text}</i>
⏰ <code>{timestamp.strftime('%H:%M:%S')}</code>
        """


def format_market_scan_signal(signal):
    """Format market scan signal (simple dict) into Telegram message."""
    pair = signal.get("pair", "UNKNOWN")
    sig_type = signal.get("type", "HOLD")
    confidence = signal.get("confidence", 0)
    price = signal.get("price", 0)
    reason = signal.get("reason", "TA analysis")

    signal_config = {
        "STRONG_BUY": {"emoji": "🚀", "gain": "✅", "momentum": "🔥"},
        "BUY": {"emoji": "📈", "gain": "✅", "momentum": "💪"},
        "HOLD": {"emoji": "➡️", "gain": "⚪", "momentum": "⏳"},
        "SELL": {"emoji": "📉", "gain": "⚠️", "momentum": "💨"},
        "STRONG_SELL": {"emoji": "🔻", "gain": "🚨", "momentum": "⛔"},
    }
    config = signal_config.get(sig_type, {"emoji": "❓", "gain": "❓", "momentum": "❓"})
    now = datetime.now().strftime("%H:%M:%S")
    theme = _recommendation_theme(sig_type)

    return f"""{config['emoji']} {_safe_text(pair.upper())}
Keputusan: {_display_badge(theme)} {config['gain']}

💰 Harga: <code>{price:,.0f} IDR</code>
🎯 Keyakinan: {confidence:.0%}
⏰ Jam: {now}

📝 Alasan: {_safe_text(reason)}
"""
