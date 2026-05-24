# Tujuan: Test tampilan teks signal Telegram tetap ringkas dan tidak berteriak ALL-CAPS.
# Caller: pytest focused UI formatting.
# Dependensi: signals.signal_formatter.
# Side Effects: Tidak ada; hanya pure formatting.

from datetime import datetime

from signals.signal_formatter import format_market_scan_signal, format_signal_message_html


def _sample_signal(recommendation="STRONG_BUY"):
    return {
        "pair": "btcidr",
        "recommendation": recommendation,
        "price": 1_000_000_000,
        "ml_confidence": 0.82,
        "ml_confidence_raw": 0.80,
        "combined_strength": 0.61,
        "timestamp": datetime(2026, 5, 22, 20, 30, 0),
        "reason": "test signal",
        "indicators": {
            "rsi": "NEUTRAL",
            "macd": "BULLISH",
            "ma_trend": "BULLISH",
            "bb": "NORMAL",
            "volume": "HIGH",
        },
    }


def test_signal_message_uses_readable_title_case_decision_label():
    text = format_signal_message_html(_sample_signal("STRONG_BUY"))

    assert "Keputusan: Beli kuat" in text
    assert "Keputusan: BELI KUAT" not in text
    assert "<b>" not in text


def test_signal_message_sell_label_is_readable_not_all_caps():
    text = format_signal_message_html(_sample_signal("STRONG_SELL"))

    assert "Keputusan: Jual kuat" in text
    assert "Keputusan: JUAL KUAT" not in text


def test_market_scan_signal_uses_same_readable_decision_label():
    text = format_market_scan_signal(
        {"pair": "ethidr", "type": "SELL", "confidence": 0.72, "price": 40_000_000, "reason": "test"}
    )

    assert "Keputusan: Jual" in text
    assert "Keputusan: JUAL" not in text
    assert "<b>" not in text
