#!/usr/bin/env python3
"""Signal formatting helpers extracted from bot.py."""

from datetime import datetime

from core.utils import Utils


def generate_strength_bar(strength):
    """Generate visual strength bar indicator."""
    strength = max(-1, min(1, strength))
    bar_length = int(abs(strength) * 10)
    empty_length = 10 - bar_length

    if strength > 0:
        bar = "█" * bar_length + "░" * empty_length
        return f"🟢 [{bar}]"
    if strength < 0:
        bar = "░" * empty_length + "█" * bar_length
        return f"🔴 [{bar}]"
    return f"⚪ [{'░' * 10}]"


def generate_strength_bar_html(strength):
    """Generate visual strength bar indicator for HTML."""
    strength = max(-1, min(1, strength))
    bar_length = int(abs(strength) * 10)

    if strength > 0:
        bar = "█" * bar_length + "░" * (10 - bar_length)
        return f"<code>[{bar}]</code>"
    if strength < 0:
        bar = "░" * (10 - bar_length) + "█" * bar_length
        return f"<code>[{bar}]</code>"
    return f"<code>[{'░' * 10}]</code>"


def format_signal_message(signal):
    """Format signal into readable Telegram message (Markdown)."""
    indicators = signal.get("indicators", {})
    pair = signal.get("pair", "UNKNOWN")
    recommendation = signal.get("recommendation", "HOLD")
    price = signal.get("price", 0)
    ml_confidence = signal.get("ml_confidence", 0.5)
    combined_strength = signal.get("combined_strength", 0)
    timestamp = signal.get("timestamp", datetime.now())
    reason = signal.get("reason", "No analysis available")

    if recommendation in ["BUY", "STRONG_BUY"]:
        rec_colored = f"🟢 {recommendation}"
    elif recommendation in ["SELL", "STRONG_SELL"]:
        rec_colored = f"🔴 {recommendation}"
    else:
        rec_colored = f"⚪ {recommendation}"

    signal_config = {
        "STRONG_BUY": {
            "emoji": "🚀",
            "desc": "Strong Buy Signal",
            "action": "Consider buying immediately",
        },
        "BUY": {
            "emoji": "📈",
            "desc": "Buy Signal",
            "action": "Good entry point",
        },
        "HOLD": {
            "emoji": "⏸️",
            "desc": "Hold Position",
            "action": "Wait for better opportunity",
        },
        "SELL": {
            "emoji": "📉",
            "desc": "Sell Signal",
            "action": "Consider taking profits",
        },
        "STRONG_SELL": {
            "emoji": "🔻",
            "desc": "Strong Sell Signal",
            "action": "Exit position immediately",
        },
    }.get(recommendation, {"emoji": "❓", "desc": "Unknown", "action": "N/A"})

    support_1 = signal.get("support_1", 0)
    resistance_1 = signal.get("resistance_1", 0)

    sr_section = ""
    if support_1 > 0 or resistance_1 > 0:
        sr_section = f"""
🎯 **Support/Resistance:**
• Support: `{Utils.format_price(support_1)}` {'IDR' if support_1 > 0 else ''}
• Resistance: `{Utils.format_price(resistance_1)}` {'IDR' if resistance_1 > 0 else ''}"""

    strength_bar = generate_strength_bar(combined_strength)
    confidence_bar = generate_strength_bar(ml_confidence * 2 - 1)

    rsi_val = indicators.get("rsi", "N/A")
    macd_val = indicators.get("macd", "N/A")
    ma_val = indicators.get("ma_trend", "N/A")
    bb_val = indicators.get("bb", "N/A")
    vol_val = indicators.get("volume", "N/A")

    rsi_emoji = "🔴" if rsi_val == "OVERBOUGHT" else "🟢" if rsi_val == "OVERSOLD" else "⚪"
    macd_emoji = "🟢" if "BULLISH" in str(macd_val) else "🔴" if "BEARISH" in str(macd_val) else "⚪"
    ma_emoji = "🟢" if ma_val == "BULLISH" else "🔴" if ma_val == "BEARISH" else "⚪"

    return f"""
{signal_config['emoji']} *{pair} — Trading Signal*

{rec_colored} *Recommendation: {recommendation}*
_{signal_config['desc']}_
💡 Action: {signal_config['action']}

💰 *Current Price:* `{Utils.format_price(price)}` IDR

📊 *Signal Strength:*
{strength_bar} `{combined_strength:+.2f}`
🤖 *ML Confidence:*
{confidence_bar} `{ml_confidence:.1%}`

📈 *Technical Indicators:*
{rsi_emoji} RSI (14): `{rsi_val}`
{macd_emoji} MACD: `{macd_val}`
{ma_emoji} MA Trend: `{ma_val}`
⚪ Bollinger: `{bb_val}`
⚪ Volume: `{vol_val}`
{sr_section}

📝 *Analysis:*
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
    combined_strength = signal.get("combined_strength", 0)
    timestamp = signal.get("timestamp", datetime.now())
    reason = signal.get("reason", "No analysis available")

    signal_config = {
        "STRONG_BUY": {"emoji": "🚀", "desc": "Strong Buy Signal", "action": "Consider buying immediately"},
        "BUY": {"emoji": "📈", "desc": "Buy Signal", "action": "Good entry point"},
        "HOLD": {"emoji": "⏸️", "desc": "Hold Position", "action": "Wait for better opportunity"},
        "SELL": {"emoji": "📉", "desc": "Sell Signal", "action": "Consider taking profits"},
        "STRONG_SELL": {"emoji": "🔻", "desc": "Strong Sell Signal", "action": "Exit position immediately"},
    }.get(recommendation, {"emoji": "❓", "desc": "Unknown", "action": "N/A"})

    support_1 = signal.get("support_1", 0)
    support_2 = signal.get("support_2", 0)
    resistance_1 = signal.get("resistance_1", 0)
    resistance_2 = signal.get("resistance_2", 0)
    price_zone = signal.get("price_zone", "UNKNOWN")
    rr_ratio = signal.get("risk_reward_ratio", 0)

    sr_section = ""
    if support_1 > 0 or resistance_1 > 0:
        sr_section = f"""

🎯 <b>Support/Resistance:</b>
• S1: <code>{Utils.format_price(support_1) if support_1 > 0 else '—'}</code>
• S2: <code>{Utils.format_price(support_2) if support_2 > 0 else '—'}</code>
• R1: <code>{Utils.format_price(resistance_1) if resistance_1 > 0 else '—'}</code>
• R2: <code>{Utils.format_price(resistance_2) if resistance_2 > 0 else '—'}</code>

📍 <b>Price Zone:</b> {price_zone}
⚖️ <b>Risk/Reward:</b> {rr_ratio:.2f}"""

    rsi_val = indicators.get("rsi", "N/A")
    macd_val = indicators.get("macd", "N/A")
    ma_val = indicators.get("ma_trend", "N/A")
    bb_val = indicators.get("bb", "N/A")
    vol_val = indicators.get("volume", "N/A")

    rsi_emoji = "🔴" if rsi_val == "OVERBOUGHT" else "🟢" if rsi_val == "OVERSOLD" else "⚪"
    macd_emoji = "🟢" if "BULLISH" in str(macd_val) else "🔴" if "BEARISH" in str(macd_val) else "⚪"
    ma_emoji = "🟢" if ma_val == "BULLISH" else "🔴" if ma_val == "BEARISH" else "⚪"
    bb_emoji = "🟢" if bb_val == "OVERSOLD" else "🔴" if bb_val == "OVERBOUGHT" else "⚪"

    strength_bar = generate_strength_bar_html(combined_strength)
    confidence_pct = int(ml_confidence * 100)
    recommendation_label = (
        f"🟢 {recommendation}" if recommendation in ["BUY", "STRONG_BUY"]
        else f"🔴 {recommendation}" if recommendation in ["SELL", "STRONG_SELL"]
        else f"⚪ {recommendation}"
    )

    return f"""
{signal_config['emoji']} <b>{pair} — Trading Signal</b>

<b>Recommendation: {recommendation_label}</b>
<i>{signal_config['desc']}</i>
💡 <b>Action:</b> {signal_config['action']}

💰 <b>Current Price:</b> <code>{Utils.format_price(price)}</code> IDR

📊 <b>Signal Metrics:</b>
• Combined Strength: {strength_bar} <code>{combined_strength:+.2f}</code>
• ML Confidence: <code>{confidence_pct}%</code>

📈 <b>Technical Indicators:</b>
{rsi_emoji} RSI (14): <code>{rsi_val}</code>
{macd_emoji} MACD: <code>{macd_val}</code>
{ma_emoji} MA Trend: <code>{ma_val}</code>
{bb_emoji} Bollinger: <code>{bb_val}</code>
⚪ Volume: <code>{vol_val}</code>
{sr_section}

📝 <b>Analysis:</b>
<i>{reason}</i>

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
        "STRONG_BUY": {"emoji": "🚀"},
        "BUY": {"emoji": "📈"},
        "HOLD": {"emoji": "⏸️"},
        "SELL": {"emoji": "📉"},
        "STRONG_SELL": {"emoji": "🔻"},
    }
    config = signal_config.get(sig_type, {"emoji": "❓"})
    now = datetime.now().strftime("%H:%M:%S")

    if sig_type in ["BUY", "STRONG_BUY"]:
        rec_colored = f"<b>🟢 {sig_type}</b>"
    elif sig_type in ["SELL", "STRONG_SELL"]:
        rec_colored = f"<b>🔴 {sig_type}</b>"
    else:
        rec_colored = f"<b>⚪ {sig_type}</b>"

    return f"""{config['emoji']} <b>Signal Alert — {rec_colored}</b>

📊 <b>{pair.upper()}</b>

💰 Price: <code>{price:,.0f} IDR</code>
🎯 Confidence: {confidence:.0%}
⏰ Time: {now}

📝 <b>Reason:</b> {reason}
"""
