"""Tests for core.telegram_html sanitizer (Bug Critical #4 — audit 2026-06-07).

Telegram parse_mode='HTML' rejects stray '<', '>', '&' or non-whitelisted tags
with "Can't parse entities". This sanitizer cleans input proactively so the
message goes through.
"""
import pytest

from core.telegram_html import sanitize_telegram_html, escape_telegram_html


class TestSanitizeTelegramHtml:
    """Whitelist-aware HTML cleaner."""

    def test_preserves_whitelisted_tags(self):
        text = "<b>BUY</b> <i>signal</i> at <code>1,234</code> IDR"
        assert sanitize_telegram_html(text) == text

    def test_preserves_anchor_tag_with_href(self):
        text = '<a href="https://example.com">link</a>'
        assert sanitize_telegram_html(text) == text

    def test_preserves_blockquote_and_pre(self):
        text = "<blockquote>quote</blockquote><pre>code</pre>"
        assert sanitize_telegram_html(text) == text

    def test_preserves_tg_spoiler(self):
        text = '<tg-spoiler>secret</tg-spoiler> <span class="tg-spoiler">hidden</span>'
        assert sanitize_telegram_html(text) == text

    def test_escapes_stray_lt_inside_text(self):
        # Common case: dynamic content like "if x<3" or feature counts.
        text = "X has 58 features, but Scaler expects <47 features>"
        result = sanitize_telegram_html(text)
        # The bare '<' and following '>' should be escaped.
        assert "&lt;47 features&gt;" in result

    def test_escapes_unclosed_tag_inside_b_block(self):
        # The stray '<' is the classic source of "can't find end of entity".
        text = "<b>bad < reason</b>"
        # '<b>' and '</b>' preserved; standalone '<' escaped.
        assert sanitize_telegram_html(text) == "<b>bad &lt; reason</b>"

    def test_escapes_non_whitelisted_tags(self):
        text = "<script>alert(1)</script>"
        result = sanitize_telegram_html(text)
        assert "<script>" not in result
        assert "&lt;script&gt;" in result

    def test_escapes_bare_ampersand(self):
        text = "Profit & Loss: 5% & rising"
        result = sanitize_telegram_html(text)
        assert "&amp;" in result
        assert " & " not in result

    def test_preserves_existing_html_entities(self):
        # Already-escaped entities should NOT be double-escaped.
        text = "Use &lt;b&gt; for bold &amp; &gt; for greater"
        result = sanitize_telegram_html(text)
        assert "&amp;amp;" not in result
        assert "&amp;lt;" not in result

    def test_handles_numeric_entity(self):
        text = "Price: &#36;100 (unicode &#x1F4B0;)"
        result = sanitize_telegram_html(text)
        # Numeric/hex entities preserved as-is.
        assert "&#36;" in result
        assert "&#x1F4B0;" in result

    def test_handles_none_input(self):
        assert sanitize_telegram_html(None) == ""

    def test_handles_non_string_input(self):
        assert sanitize_telegram_html(42) == "42"

    def test_handles_empty_string(self):
        assert sanitize_telegram_html("") == ""

    def test_real_world_signal_message_passes_through(self):
        """A typical signal message with whitelisted tags should be unchanged."""
        text = (
            "📈 BTCIDR  Vol: Rp1.2B\n"
            "Keputusan: <b>BELI</b> ✅\n\n"
            "Saran: Boleh pantau entry kecil.\n"
            "Harga: <code>1,234,567</code> IDR\n\n"
            "Ringkasan\n"
            "• Keyakinan bot: <code>78%</code>\n"
            "<i>Trend bullish, RSI 65</i>"
        )
        assert sanitize_telegram_html(text) == text

    def test_problematic_signal_with_stray_lt(self):
        """Real bug scenario: feature mismatch error injected into signal."""
        text = (
            "<b>edenidr</b> Vol: 5K\n"
            "<i>X has 58 features, <47 expected> by Scaler</i>"
        )
        result = sanitize_telegram_html(text)
        # Whitelisted tags preserved.
        assert "<b>edenidr</b>" in result
        assert "<i>" in result
        assert "</i>" in result
        # Stray '<' '>' escaped.
        assert "&lt;47 expected&gt;" in result


class TestEscapeTelegramHtml:
    """Full-escape utility (no tag preservation)."""

    def test_escapes_all_specials(self):
        assert escape_telegram_html("<b>x & y</b>") == "&lt;b&gt;x &amp; y&lt;/b&gt;"

    def test_handles_none(self):
        assert escape_telegram_html(None) == ""

    def test_handles_non_string(self):
        assert escape_telegram_html(3.14) == "3.14"
