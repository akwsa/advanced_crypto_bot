"""Capital Rotation Detection — whale flow shift tracking (adapted from Cryptoiz)."""
from collections import defaultdict
from dataclasses import dataclass
from typing import Dict, List
import time
ROTATION_WINDOW_MINUTES = 15
@dataclass
class RotationSignal:
    source_pair: str; target_pair: str; strength: float; bid_ratio_change: float; timestamp: float
class CapitalRotationTracker:
    def __init__(self, max_history=20):
        self.max_history = max_history; self._snapshots: Dict[str, list] = defaultdict(list)
    def update(self, pair, snapshot):
        bid_total = snapshot.total_bid_notional; ask_total = snapshot.total_ask_notional
        whale_bid = snapshot.bid_tiers.get("WHALE", 0) + snapshot.bid_tiers.get("DOLPHIN", 0)
        whale_ask = snapshot.ask_tiers.get("WHALE", 0) + snapshot.ask_tiers.get("DOLPHIN", 0)
        self._snapshots[pair].append({
            "ts": snapshot.timestamp,
            "whale_bid_ratio": whale_bid / bid_total if bid_total > 0 else 0,
            "whale_ask_ratio": whale_ask / ask_total if ask_total > 0 else 0,
            "total_bid": bid_total, "total_ask": ask_total,
        })
        if len(self._snapshots[pair]) > self.max_history:
            self._snapshots[pair] = self._snapshots[pair][-self.max_history:]
    def detect_rotation(self, pairs: List[str]) -> List[RotationSignal]:
        signals = []; now = time.time(); cutoff = now - ROTATION_WINDOW_MINUTES * 60
        trends = {}
        for pair in pairs:
            history = self._snapshots.get(pair, [])
            recent = [h for h in history if h["ts"] > cutoff]
            old = [h for h in history if h["ts"] <= cutoff]
            if not recent or not old: continue
            recent_avg = sum(h["whale_bid_ratio"] for h in recent) / len(recent)
            old_avg = sum(h["whale_bid_ratio"] for h in old) / len(old)
            trends[pair] = recent_avg - old_avg
        if len(trends) >= 2:
            sp = sorted(trends.items(), key=lambda x: x[1], reverse=True)
            if sp[0][1] > 0.05 and sp[-1][1] < -0.05:
                signals.append(RotationSignal(source_pair=sp[-1][0], target_pair=sp[0][0], strength=min(1.0, abs(sp[0][1] - sp[-1][1])), bid_ratio_change=sp[0][1], timestamp=now))
        return signals
