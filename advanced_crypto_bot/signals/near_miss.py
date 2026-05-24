#!/usr/bin/env python3
# Tujuan: Helper pure untuk ringkasan near-miss signal read-only.
# Caller: Telegram watchlist filters/dashboard diagnostics.
# Dependensi: stdlib only.
# Main Functions: build_near_miss_summary, format_near_miss_report_html.
# Side Effects: Tidak ada; tidak mengubah signal/trading/order path.
"""Read-only near-miss signal extraction and formatting helpers."""

from __future__ import annotations

from html import escape
from typing import Any, Dict, Iterable, List, Optional

ACTIONABLE_RECOMMENDATIONS = {"BUY", "STRONG_BUY", "SELL", "STRONG_SELL"}


_CATEGORY_KEYWORDS = (
    ("RR_LOW", ("risk/reward low", "rr low", "risk reward low")),
    ("NEAR_RESISTANCE", ("near resistance", "at/near resistance", "resistance")),
    ("NEAR_SUPPORT", ("near support", "at/near support", "support")),
    ("QUALITY_REJECT", ("quality engine", "quality")),
    ("V4_REJECT", ("v4",)),
    ("PRICE_REJECT", ("stale price", "price validation", "stale realtime")),
    ("VOLATILITY_REJECT", ("volatility", "regime")),
)


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        if value is None or value == "":
            return default
        return float(value)
    except (TypeError, ValueError):
        return default


def _reason_text(signal: Dict[str, Any]) -> str:
    return str(signal.get("reason") or signal.get("analysis") or "").strip()


def _detect_side(signal: Dict[str, Any]) -> Optional[str]:
    """Infer intended candidate side without treating it as actionable."""
    text = _reason_text(signal).upper()
    for key in ("candidate_side", "near_miss_side", "original_recommendation", "requested_recommendation"):
        side = str(signal.get(key) or "").upper()
        if "BUY" in side:
            return "BUY"
        if "SELL" in side:
            return "SELL"

    if "BUY" in text:
        return "BUY"
    if "SELL" in text:
        return "SELL"

    strength = _safe_float(signal.get("combined_strength"))
    if strength > 0.05:
        return "BUY"
    if strength < -0.05:
        return "SELL"
    return None


def _detect_category(signal: Dict[str, Any]) -> str:
    text = _reason_text(signal).lower()
    source = str(signal.get("final_gate_source") or "").lower()
    haystack = f"{source} {text}"
    for category, keywords in _CATEGORY_KEYWORDS:
        if any(keyword in haystack for keyword in keywords):
            return category
    if source:
        return source.upper()
    return "REJECTED"


def _is_near_miss(signal: Dict[str, Any]) -> bool:
    recommendation = str(signal.get("recommendation") or "HOLD").upper()
    if recommendation in ACTIONABLE_RECOMMENDATIONS:
        return False
    return _detect_side(signal) is not None


def build_near_miss_summary(signals: Iterable[Dict[str, Any]], limit: int = 5) -> Dict[str, Any]:
    """Build a read-only near-miss summary from signal dictionaries.

    A near-miss is a final non-actionable signal (usually HOLD) with evidence that
    it started as, or was rejected as, a BUY/SELL candidate. This function only
    classifies already-produced signal data; it never changes recommendations.
    """
    items: List[Dict[str, Any]] = []
    by_side = {"BUY": 0, "SELL": 0}
    by_source: Dict[str, int] = {}

    for raw in signals or []:
        signal = dict(raw or {})
        if not _is_near_miss(signal):
            continue

        side = _detect_side(signal)
        if side not in by_side:
            continue

        source = str(signal.get("final_gate_source") or "UNKNOWN").upper()
        reason = _reason_text(signal) or "Tidak ada alasan detail"
        item = {
            "pair": str(signal.get("pair") or signal.get("symbol") or "?").lower(),
            "side": side,
            "source": source,
            "category": _detect_category(signal),
            "combined_strength": _safe_float(signal.get("combined_strength")),
            "ml_confidence": _safe_float(signal.get("ml_confidence")),
            "reason": reason,
        }
        items.append(item)
        by_side[side] += 1
        by_source[source] = by_source.get(source, 0) + 1

    items.sort(
        key=lambda item: (
            abs(item["combined_strength"]),
            item["ml_confidence"],
        ),
        reverse=True,
    )
    if limit is not None and limit >= 0:
        items = items[:limit]

    by_side = {side: count for side, count in by_side.items() if count}
    return {
        "total": sum(by_side.values()),
        "by_side": by_side,
        "by_source": by_source,
        "items": items,
    }


def _truncate(text: str, max_len: int = 120) -> str:
    text = str(text or "").strip()
    if len(text) <= max_len:
        return text
    return text[: max_len - 3] + "..."


def format_near_miss_report_html(summary: Dict[str, Any], watched_count: Optional[int] = None) -> str:
    """Format near-miss summary for Telegram HTML/dashboard reuse."""
    summary = dict(summary or {})
    total = int(summary.get("total") or 0)
    by_side = dict(summary.get("by_side") or {})
    by_source = dict(summary.get("by_source") or {})
    items = list(summary.get("items") or [])

    scope = f" dari <code>{watched_count}</code> pair" if watched_count is not None else ""
    lines = [
        "🟡 <b>Near-miss Signal</b>",
        f"Ditemukan <code>{total}</code> kandidat tertahan{scope}.",
        "Near-miss signal ini hanya informatif. Tidak membuka order dan tidak mengubah keputusan final bot.",
        "",
        "📊 Ringkasan: "
        f"BUY={int(by_side.get('BUY', 0))}, "
        f"SELL={int(by_side.get('SELL', 0))}",
    ]

    if by_source:
        source_text = ", ".join(
            f"{escape(str(source))}=<code>{count}</code>"
            for source, count in sorted(by_source.items())
        )
        lines.append(f"🛡️ Filter: {source_text}")

    if items:
        lines.extend(["", "Top kandidat tertahan:"])
        for item in items:
            pair = escape(str(item.get("pair", "?")).upper())
            side = escape(str(item.get("side", "?")))
            source = escape(str(item.get("source", "UNKNOWN")))
            category = escape(str(item.get("category", "REJECTED")))
            strength = _safe_float(item.get("combined_strength"))
            confidence = _safe_float(item.get("ml_confidence"))
            reason = escape(_truncate(str(item.get("reason") or "Tidak ada alasan detail")))
            lines.append(
                f"• <code>{pair}</code> {side} near-miss "
                f"({category}/{source}) — strength=<code>{strength:+.2f}</code>, "
                f"ML=<code>{confidence:.1%}</code> — {reason}"
            )
    else:
        lines.extend(["", "Tidak ada near-miss BUY/SELL yang jelas dari data signal saat ini."])

    return "\n".join(lines)
