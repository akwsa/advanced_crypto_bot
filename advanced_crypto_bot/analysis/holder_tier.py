"""Holder Tier Analysis — 5-tier orderbook classification (adapted from Cryptoiz)."""
from dataclasses import dataclass, field
from typing import Dict, Optional
import time
TIER_THRESHOLDS = {"WHALE": 500_000_000, "DOLPHIN": 100_000_000, "SHARK": 20_000_000, "FISH": 5_000_000, "SHRIMP": 0}
TIER_ORDER = ["WHALE", "DOLPHIN", "SHARK", "FISH", "SHRIMP"]
@dataclass
class TierSnapshot:
    pair: str; timestamp: float; total_bid_notional: float = 0.0; total_ask_notional: float = 0.0
    bid_tiers: Dict[str, float] = field(default_factory=dict); ask_tiers: Dict[str, float] = field(default_factory=dict)
    bid_count: Dict[str, int] = field(default_factory=dict); ask_count: Dict[str, int] = field(default_factory=dict)
def classify_tier(notional: float) -> str:
    for tier in TIER_ORDER:
        if notional >= TIER_THRESHOLDS[tier]: return tier
    return "SHRIMP"
def analyze_orderbook_tiers(pair, bids, asks):
    snap = TierSnapshot(pair=pair, timestamp=time.time())
    for side, levels, tm, cm in [("bid", bids, snap.bid_tiers, snap.bid_count), ("ask", asks, snap.ask_tiers, snap.ask_count)]:
        for level in (levels or []):
            try:
                price = float(level[0]) if isinstance(level, (list, tuple)) else float(level)
                amount = float(level[1]) if isinstance(level, (list, tuple)) and len(level) > 1 else 0
            except: continue
            n = price * amount; t = classify_tier(n)
            tm[t] = tm.get(t, 0) + n; cm[t] = cm.get(t, 0) + 1
            if side == "bid": snap.total_bid_notional += n
            else: snap.total_ask_notional += n
    return snap
def detect_accumulation(current, previous=None):
    r = {"signal": "NEUTRAL", "confidence": 0.0, "reasons": []}
    wb = current.bid_tiers.get("WHALE", 0) + current.bid_tiers.get("DOLPHIN", 0)
    wa = current.ask_tiers.get("WHALE", 0) + current.ask_tiers.get("DOLPHIN", 0)
    t = wb + wa
    if t > 0:
        br = wb / t
        if br > 0.65: r = {"signal": "ACCUMULATION", "confidence": min(1.0, br), "reasons": [f"Whale bid dominance: {br:.0%}"]}
        elif br < 0.35: r = {"signal": "DISTRIBUTION", "confidence": min(1.0, 1.0 - br), "reasons": [f"Whale ask dominance: {1.0-br:.0%}"]}
    return r
def holder_tier_summary(snap):
    lines = [f"Holder Tiers for {snap.pair}:"]
    for tier in TIER_ORDER:
        b = snap.bid_tiers.get(tier, 0); a = snap.ask_tiers.get(tier, 0)
        bc = snap.bid_count.get(tier, 0); ac = snap.ask_count.get(tier, 0)
        lines.append(f"  {tier:8s} | BID: Rp {b:>14,.0f} ({bc:>3d}) | ASK: Rp {a:>14,.0f} ({ac:>3d})")
    return "\n".join(lines)
