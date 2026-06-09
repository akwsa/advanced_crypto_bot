# Tujuan: Sanitizer HTML untuk Telegram parse_mode='HTML'.
#         Mencegah error "Can't parse entities" karena stray <, >, & atau tag invalid.
# Caller: bot.py::_send_message, autotrade/runtime.py, autohunter, retrain notifications.
# Dependensi: stdlib re/html.
# Main Functions: sanitize_telegram_html (utama), escape_telegram_html (full escape).
# Side Effects: pure function, no I/O.
"""Telegram HTML sanitization.

Telegram Bot API only allows a limited tag whitelist for parse_mode='HTML':
  <b>, <strong>, <i>, <em>, <u>, <ins>, <s>, <strike>, <del>,
  <a href="...">, <code>, <pre>, <tg-spoiler>, <span class="tg-spoiler">,
  <blockquote>

Any other `<...>` token, unbalanced tag, or stray `&` causes Telegram to reject
the message with "Can't parse entities". Dynamic text (error messages, reasons,
indicator values, pair names) frequently contains such characters.

This module sanitizes a "best-effort HTML" string into a strict-valid one:
- Bare `&` (not part of an entity) → `&amp;`
- Tags outside the whitelist → escaped to `&lt;...&gt;`
- Whitelisted tags preserved verbatim.

The intent is to make `_send_message(..., parse_mode='HTML')` succeed even
when the upstream formatter forgot to escape user/data content.
"""

from __future__ import annotations

import re

# Telegram Bot API allowed HTML tags (lowercase, without angle brackets).
# Source: https://core.telegram.org/bots/api#html-style
_ALLOWED_TAGS = frozenset({
    "b", "strong",
    "i", "em",
    "u", "ins",
    "s", "strike", "del",
    "a",
    "code",
    "pre",
    "tg-spoiler",
    "span",          # only when class="tg-spoiler"
    "blockquote",
    "br",            # legacy single tag, ignored by Telegram but harmless
})

# Match a full tag candidate: <name ...attrs...> or </name> or <name/>
# Captures the inner content for analysis.
_TAG_RE = re.compile(r"<(/?)([a-zA-Z][a-zA-Z0-9-]*)((?:\s[^<>]*)?)(/?)>")

# Match any `&` that is NOT already a valid HTML/XML entity reference.
# Valid: &amp; &lt; &gt; &quot; &#39; &#NNN; &#xHEX;
_BARE_AMP_RE = re.compile(r"&(?!(?:amp|lt|gt|quot|apos|#[0-9]+|#x[0-9a-fA-F]+);)")


def _escape_chunk(s: str) -> str:
    """Escape only stray characters; leave already-escaped entities alone."""
    s = _BARE_AMP_RE.sub("&amp;", s)
    return s


def sanitize_telegram_html(text: str) -> str:
    """
    Make `text` safe for Telegram `parse_mode='HTML'`.

    - Preserves whitelisted tags (b/i/u/s/code/pre/a/blockquote/tg-spoiler/etc).
    - Escapes any other `<...>` token as literal text.
    - Escapes bare `&` that is not already part of an entity.
    - Stray `<` or `>` not part of a tag-shaped token → escaped.

    This does NOT validate balanced tag pairs (Telegram is fairly tolerant of
    minor imbalance once the whitelist is enforced). The most common source of
    "Can't parse entities" is stray `<` from text content (e.g. `<unknown>`,
    `if x<3`, ML output `<feature_count>`), which this function handles.
    """
    if text is None:
        return ""
    if not isinstance(text, str):
        text = str(text)

    out: list[str] = []
    pos = 0
    for m in _TAG_RE.finditer(text):
        # Escape preceding chunk (and its stray '&' / '<' / '>').
        chunk = text[pos:m.start()]
        chunk = _escape_chunk(chunk)
        # Stray '<' or '>' that didn't form a tag in this chunk are safe to
        # leave as-is for Telegram only if they don't pair into entities, but
        # the safest course is to escape them. The regex `_TAG_RE` matched
        # well-formed tag candidates, so anything left is bare punctuation.
        chunk = chunk.replace("<", "&lt;").replace(">", "&gt;")
        out.append(chunk)

        closing, name, attrs, self_close = m.group(1), m.group(2), m.group(3), m.group(4)
        name_lower = name.lower()

        if name_lower in _ALLOWED_TAGS:
            # Reconstruct the tag verbatim (Telegram tolerates attribute spelling).
            out.append(f"<{closing}{name}{attrs}{self_close}>")
        else:
            # Escape the entire match as literal text.
            out.append(_escape_chunk(m.group(0)).replace("<", "&lt;").replace(">", "&gt;"))
        pos = m.end()

    # Tail
    tail = text[pos:]
    tail = _escape_chunk(tail).replace("<", "&lt;").replace(">", "&gt;")
    out.append(tail)
    return "".join(out)


def escape_telegram_html(text: str) -> str:
    """Full-escape: treat input as plain text, no tags preserved."""
    if text is None:
        return ""
    if not isinstance(text, str):
        text = str(text)
    return (
        text.replace("&", "&amp;")
            .replace("<", "&lt;")
            .replace(">", "&gt;")
    )


__all__ = ["sanitize_telegram_html", "escape_telegram_html"]
