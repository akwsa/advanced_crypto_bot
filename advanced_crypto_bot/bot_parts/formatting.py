# Tujuan: Helper formatting untuk tampilan signal agar bot.py tetap ringkas.
# Caller: bot.AdvancedCryptoBot method wrappers.
# Dependensi: core.utils.Utils.
# Main Functions: signal_visual, format_signal_list_price, format_signal_scan_line_html, format_signal_section_html, build_signal_overview_html.
# Side Effects: none (pure formatting).

from core.utils import Utils


def _safe_float(value, default=0.0):
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def signal_display_rank(signal):
    """Rank signals for Telegram display only; does not affect execution logic."""
    rec = str(signal.get("recommendation", "HOLD") or "HOLD").upper()
    rec_priority = {
        "STRONG_BUY": 4,
        "STRONG_SELL": 4,
        "BUY": 3,
        "SELL": 3,
        "HOLD": 1,
    }.get(rec, 0)
    strength = abs(_safe_float(signal.get("combined_strength"), 0.0))
    score = _safe_float(signal.get("score"), 0.0)
    confidence = _safe_float(signal.get("ml_confidence"), 0.0)
    volume = _safe_float(signal.get("volume") or signal.get("vol_idr"), 0.0)
    return (rec_priority, strength, score, confidence, volume)


def signal_visual(recommendation):
    if recommendation in ["BUY", "STRONG_BUY"]:
        return "🟢", "BUY"
    if recommendation in ["SELL", "STRONG_SELL"]:
        return "🔴", "SELL"
    return "⚪", "HOLD"


def format_signal_list_price(price):
    if price is None:
        return "0"

    abs_price = abs(price)
    if abs_price >= 1000:
        decimals = 0
    elif abs_price >= 1:
        decimals = 2
    elif abs_price >= 0.01:
        decimals = 4
    else:
        decimals = 6

    return Utils.format_price(price, decimals=decimals)


def format_signal_scan_line_html(signal):
    pair = signal.get("pair", "UNKNOWN").upper()
    recommendation = signal.get("recommendation", "HOLD")
    confidence = signal.get("ml_confidence", 0)
    price = signal.get("price", 0)
    icon, _ = signal_visual(recommendation)
    return (
        f"{icon} <b>{pair}</b>  "
        f"<b>{recommendation}</b>  "
        f"<code>{confidence:.0%}</code>\n"
        f"Price: <code>{format_signal_list_price(price)}</code> IDR"
    )


def format_signal_section_html(title, signals):
    if not signals:
        return ""

    lines = [f"<b>{title}</b>"]
    for signal in sorted(signals, key=signal_display_rank, reverse=True):
        lines.append(format_signal_scan_line_html(signal))
        lines.append("")
    return "\n".join(lines).rstrip()


def build_signal_overview_html(
    buy_signals,
    sell_signals,
    hold_signals,
    updated_at=None,
    include_hold=True,
    hold_limit=None,
):
    sections = ["<b>📊 Trading Opportunities</b>"]
    if updated_at:
        sections.append(f"Updated: <code>{updated_at}</code>")

    buy_section = format_signal_section_html("🟢 BUY Signals", buy_signals)
    sell_section = format_signal_section_html("🔴 SELL Signals", sell_signals)
    visible_hold_signals = hold_signals
    hidden_hold_count = 0
    if include_hold and hold_limit is not None and len(hold_signals) > hold_limit:
        visible_hold_signals = sorted(hold_signals, key=signal_display_rank, reverse=True)[:hold_limit]
        hidden_hold_count = len(hold_signals) - len(visible_hold_signals)

    hold_section = (
        format_signal_section_html("⚪ HOLD / Neutral", visible_hold_signals)
        if include_hold
        else ""
    )

    for section in [buy_section, sell_section, hold_section]:
        if section:
            sections.append("")
            sections.append(section)

    if hidden_hold_count > 0:
        sections.append(f"… and <b>{hidden_hold_count}</b> more HOLD signals")

    if not buy_signals and not sell_signals and (not include_hold or not hold_signals):
        sections.append("")
        sections.append("⚠️ <b>No actionable signals found</b>")

    return "\n".join(sections)
