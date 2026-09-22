# Tujuan: Membuat narasi analisa teknikal bergaya AI untuk Scalper Telegram.
# Caller: scalper.scalper_module.ScalperModule.cmd_analisa.
# Dependensi: pandas DataFrame OHLCV; pure computation/formatting.
# Side Effects: none.

from __future__ import annotations

from typing import Iterable


def _safe_float(value, default=0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _fmt_price(value) -> str:
    value = _safe_float(value)
    if value >= 1000:
        return f"{value:,.0f}".replace(",", ".")
    if value >= 1:
        return f"{value:,.2f}".rstrip("0").rstrip(".").replace(",", ".")
    return f"{value:.8f}".rstrip("0").rstrip(".")


def _display_pair(pair: str) -> str:
    pair = (pair or "").upper().replace("_", "")
    if pair.endswith("IDR") and len(pair) > 3:
        return f"{pair[:-3]}/IDR"
    return pair


def _label_timeframe(timeframe: str) -> str:
    return timeframe or "15m"


def calculate_gemini_style_metrics(df, timeframe: str = "15m", ema_periods: Iterable[int] = (7, 25, 99)) -> dict:
    """Return deterministic technical metrics for the narrative analysis.

    The helper accepts short test frames by using min_periods=1 for EMA, but in
    production callers should still provide enough candles for meaningful EMA99.
    """
    if df is None or getattr(df, "empty", True):
        raise ValueError("Data historis kosong")
    required = {"open", "high", "low", "close"}
    missing = required - set(df.columns)
    if missing:
        raise ValueError(f"Data historis tidak lengkap: {', '.join(sorted(missing))}")

    frame = df.copy()
    for col in ("open", "high", "low", "close"):
        frame[col] = frame[col].astype(float)

    close = frame["close"]
    current_price = float(close.iloc[-1])
    previous_price = float(close.iloc[-2]) if len(close) >= 2 else current_price
    price_change_pct = ((current_price - previous_price) / previous_price * 100) if previous_price else 0.0

    ema_values = {}
    for period in ema_periods:
        ema_values[int(period)] = float(close.ewm(span=int(period), adjust=False, min_periods=1).mean().iloc[-1])

    sorted_periods = sorted(ema_values)
    short_period = sorted_periods[0]
    mid_period = sorted_periods[1] if len(sorted_periods) > 1 else sorted_periods[0]
    long_period = sorted_periods[-1]

    recent_window = frame.tail(min(len(frame), 40))
    # Use close-based swing levels for Telegram narrative. The public Indodax
    # trades endpoint is resampled from ticks, so synthetic high/low can be too
    # noisy; close levels better match what users visually read from charts.
    swing_low = float(recent_window["close"].min())
    swing_high = float(recent_window["close"].max())

    recent_closes = close.tail(min(len(close), 5))
    red_candles = int((recent_closes.diff().dropna() < 0).sum())
    green_candles = int((recent_closes.diff().dropna() > 0).sum())
    short_momentum = "bullish" if green_candles > red_candles else "bearish" if red_candles > green_candles else "netral"

    short_emas = [ema_values[short_period], ema_values[mid_period]]
    if all(current_price > value for value in short_emas):
        price_vs_short_emas = "above"
    elif all(current_price < value for value in short_emas):
        price_vs_short_emas = "below"
    else:
        price_vs_short_emas = "between"

    supports = sorted({float(x) for x in [swing_low, ema_values[long_period]] if _safe_float(x) > 0 and float(x) < current_price}, reverse=True)
    resistances = sorted({float(x) for x in [swing_high, ema_values[short_period], ema_values[mid_period]] if _safe_float(x) > current_price})

    if not supports:
        supports = [current_price * 0.98, current_price * 0.96]
    elif len(supports) == 1:
        supports.append(supports[0] * 0.97)

    if not resistances:
        resistances = [current_price * 1.02, current_price * 1.04]
    elif len(resistances) == 1:
        resistances.append(resistances[0] * 1.03)

    trend_from_swing = "naik" if current_price > swing_low and swing_high > swing_low else "mendatar"
    if current_price < ema_values[short_period] and price_change_pct < 0:
        phase = "koreksi / pullback bearish"
    elif current_price > ema_values[mid_period] and price_change_pct > 0:
        phase = "lanjutan bullish"
    else:
        phase = "konsolidasi / menunggu konfirmasi"

    return {
        "timeframe": _label_timeframe(timeframe),
        "current_price": current_price,
        "previous_price": previous_price,
        "price_change_pct": price_change_pct,
        "swing_low": swing_low,
        "swing_high": swing_high,
        "ema_values": ema_values,
        "short_period": short_period,
        "mid_period": mid_period,
        "long_period": long_period,
        "short_momentum": short_momentum,
        "price_vs_short_emas": price_vs_short_emas,
        "support_1": supports[0],
        "support_2": supports[1],
        "resistance_1": resistances[0],
        "resistance_2": resistances[1],
        "trend_from_swing": trend_from_swing,
        "phase": phase,
        "red_candles": red_candles,
        "green_candles": green_candles,
    }


def build_gemini_style_technical_analysis(pair: str, df, timeframe: str = "15m", ema_periods: Iterable[int] = (7, 25, 99)) -> str:
    """Build Indonesian Gemini-style narrative for exactly one requested pair."""
    m = calculate_gemini_style_metrics(df, timeframe=timeframe, ema_periods=ema_periods)
    pair_label = _display_pair(pair)
    ema = m["ema_values"]
    sp, mp, lp = m["short_period"], m["mid_period"], m["long_period"]

    if m["price_vs_short_emas"] == "below":
        ema_read = "Harga saat ini sudah berada di bawah EMA jangka pendek/menengah, sehingga momentum pendek cenderung dikuasai tekanan jual."
        ema_bias = "bearish"
    elif m["price_vs_short_emas"] == "above":
        ema_read = "Harga masih berada di atas EMA jangka pendek/menengah, sehingga momentum pendek masih cenderung positif."
        ema_bias = "bullish"
    else:
        ema_read = "Harga berada di antara EMA pendek dan menengah, sehingga momentum belum sepenuhnya jelas dan rawan konsolidasi."
        ema_bias = "netral"

    if m["phase"].startswith("koreksi"):
        conclusion = (
            f"Secara jangka pendek ({m['timeframe']}), momentum sedang melemah / bearish pullback. "
            f"Level kunci terdekat ada di sekitar {_fmt_price(m['support_1'])}; jika tertahan dan memantul, harga berpeluang menguji ulang area EMA/resistance. "
            f"Jika jebol, risiko turun lanjutan menuju {_fmt_price(m['support_2'])} perlu diwaspadai."
        )
    elif m["phase"].startswith("lanjutan"):
        conclusion = (
            f"Secara jangka pendek ({m['timeframe']}), momentum masih condong bullish. "
            f"Selama harga bertahan di atas support {_fmt_price(m['support_1'])}, peluang uji resistance {_fmt_price(m['resistance_1'])} masih terbuka. "
            f"Namun jika turun kembali di bawah EMA pendek, skenario berubah menjadi pullback."
        )
    else:
        conclusion = (
            f"Secara jangka pendek ({m['timeframe']}), kondisi masih netral/konsolidasi. "
            f"Konfirmasi naik terjadi jika harga menembus {_fmt_price(m['resistance_1'])}; konfirmasi lemah terjadi jika turun di bawah {_fmt_price(m['support_1'])}."
        )

    return (
        f"Berikut adalah analisa teknikal singkat berdasarkan data {pair_label} pada timeframe {m['timeframe']}:\n\n"
        f"**Kondisi Tren Saat Ini**\n"
        f"• **Pergerakan Harga:** Harga bergerak dari area swing low sekitar {_fmt_price(m['swing_low'])} sampai swing high sekitar {_fmt_price(m['swing_high'])}. "
        f"Harga terakhir berada di kisaran {_fmt_price(m['current_price'])}.\n"
        f"• **Fase Saat Ini:** Kondisi terakhir terbaca sebagai **{m['phase']}**. "
        f"Candle pendek menunjukkan {m['red_candles']} tekanan turun vs {m['green_candles']} tekanan naik pada beberapa candle terakhir.\n\n"
        f"**Analisa Indikator (EMA)**\n"
        f"• **EMA{sp}:** {_fmt_price(ema[sp])}\n"
        f"• **EMA{mp}:** {_fmt_price(ema[mp])}\n"
        f"• **EMA{lp}:** {_fmt_price(ema[lp])}\n"
        f"• **Pembacaan:** {ema_read} Bias EMA saat ini: **{ema_bias.upper()}**.\n\n"
        f"**Area Support & Resistance**\n"
        f"• **Support terdekat:** {_fmt_price(m['support_1'])}. Jika area ini jebol, support berikutnya sekitar {_fmt_price(m['support_2'])}.\n"
        f"• **Resistance terdekat:** {_fmt_price(m['resistance_1'])}. Jika ditembus, target uji berikutnya sekitar {_fmt_price(m['resistance_2'])}.\n\n"
        f"**Kesimpulan Singkat**\n"
        f"{conclusion}\n\n"
        f"Catatan: Ini analisa teknikal otomatis, Hanya menganalisa pair yang diminta ({pair_label}), dan bukan saran keuangan/investasi."
    )
