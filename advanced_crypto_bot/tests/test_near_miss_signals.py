# Tujuan: Test helper laporan near-miss signal yang bersifat read-only/informatif.
# Caller: pytest focused near-miss Telegram/dashboard reporting behavior.
# Dependensi: signals.near_miss pure helper.
# Main Functions: build_near_miss_summary, format_near_miss_report_html.
# Side Effects: Tidak ada; tidak menyentuh trading/order path.

from signals.near_miss import build_near_miss_summary, format_near_miss_report_html


def test_build_near_miss_summary_extracts_buy_and_sell_rejections_without_actionable():
    signals = [
        {
            "pair": "btcidr",
            "recommendation": "HOLD",
            "combined_strength": 0.42,
            "ml_confidence": 0.81,
            "reason": "BUY rejected: BUY at/near resistance",
            "final_gate_source": "SR_VALIDATION",
        },
        {
            "pair": "ethidr",
            "recommendation": "HOLD",
            "combined_strength": -0.36,
            "ml_confidence": 0.78,
            "reason": "SELL rejected: SELL at/near support",
            "final_gate_source": "SR_VALIDATION",
        },
        {
            "pair": "solidr",
            "recommendation": "BUY",
            "combined_strength": 0.55,
            "ml_confidence": 0.88,
            "reason": "Actionable BUY",
        },
        {
            "pair": "xrpidr",
            "recommendation": "HOLD",
            "combined_strength": 0.01,
            "ml_confidence": 0.50,
            "reason": "Neutral/no edge",
        },
    ]

    summary = build_near_miss_summary(signals)

    assert summary["total"] == 2
    assert summary["by_side"] == {"BUY": 1, "SELL": 1}
    assert summary["by_source"] == {"SR_VALIDATION": 2}
    assert [item["pair"] for item in summary["items"]] == ["btcidr", "ethidr"]
    assert summary["items"][0]["side"] == "BUY"
    assert summary["items"][1]["side"] == "SELL"


def test_build_near_miss_summary_detects_rr_and_quality_rejection_sources():
    signals = [
        {
            "pair": "adaidr",
            "recommendation": "HOLD",
            "combined_strength": 0.31,
            "ml_confidence": 0.74,
            "reason": "Signal rejected: risk/reward low",
            "final_gate_source": "SR_VALIDATION",
        },
        {
            "pair": "dogeidr",
            "recommendation": "HOLD",
            "combined_strength": -0.29,
            "ml_confidence": 0.71,
            "reason": "Signal rejected by Quality Engine V3 (was SELL)",
            "final_gate_source": "QUALITY_ENGINE",
        },
    ]

    summary = build_near_miss_summary(signals)

    assert summary["total"] == 2
    assert summary["by_side"] == {"BUY": 1, "SELL": 1}
    assert summary["by_source"] == {"SR_VALIDATION": 1, "QUALITY_ENGINE": 1}
    assert summary["items"][0]["category"] == "RR_LOW"
    assert summary["items"][1]["category"] == "QUALITY_REJECT"


def test_format_near_miss_report_html_is_informational_and_escapes_text():
    summary = build_near_miss_summary([
        {
            "pair": "bad<idr",
            "recommendation": "HOLD",
            "combined_strength": 0.44,
            "ml_confidence": 0.82,
            "reason": "BUY rejected: BUY at/near resistance <unsafe>",
            "final_gate_source": "SR_VALIDATION",
        }
    ])

    text = format_near_miss_report_html(summary, watched_count=3)

    assert "Near-miss Signal" in text
    assert "hanya informatif" in text
    assert "Tidak membuka order" in text
    assert "BUY=1" in text
    assert "SELL=0" in text
    assert "BAD&lt;IDR" in text
    assert "&lt;unsafe&gt;" in text
