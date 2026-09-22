import pandas as pd

from bot_parts.scalper_ai_analysis import (
    build_gemini_style_technical_analysis,
    calculate_gemini_style_metrics,
)


def _sample_pullback_df():
    closes = [1950, 1980, 2020, 2070, 2164, 2130, 2090, 2050]
    return pd.DataFrame(
        {
            "open": [1940, 1950, 1980, 2020, 2070, 2164, 2130, 2090],
            "high": [1960, 1990, 2030, 2080, 2164, 2140, 2100, 2060],
            "low": [1935, 1945, 1975, 2010, 2060, 2120, 2080, 2040],
            "close": closes,
            "volume": [100, 110, 130, 160, 250, 230, 210, 220],
        }
    )


def test_gemini_style_metrics_detect_breakdown_below_short_emas():
    df = _sample_pullback_df()
    metrics = calculate_gemini_style_metrics(
        df,
        timeframe="15m",
        ema_periods=(3, 5, 7),
    )

    assert metrics["current_price"] == 2050
    assert metrics["swing_low"] == 1950
    assert metrics["swing_high"] == 2164
    assert metrics["short_momentum"] == "bearish"
    assert metrics["price_vs_short_emas"] == "below"
    assert metrics["support_1"] < metrics["current_price"]
    assert metrics["resistance_1"] > metrics["current_price"]


def test_gemini_style_analysis_is_pair_specific_indonesian_narrative():
    df = _sample_pullback_df()
    message = build_gemini_style_technical_analysis(
        "trollsolidr",
        df,
        timeframe="15m",
        ema_periods=(3, 5, 7),
    )

    assert "TROLLSOL/IDR" in message
    assert "timeframe 15m" in message
    assert "Kondisi Tren Saat Ini" in message
    assert "Analisa Indikator (EMA)" in message
    assert "Area Support & Resistance" in message
    assert "Kesimpulan Singkat" in message
    assert "Hanya menganalisa pair yang diminta" in message
    assert "bukan saran keuangan" in message.lower()
