"""Typed contracts for the dry-run decision/execution spine."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
import hashlib
import json
import fcntl
import math
from types import MappingProxyType
import copy
from typing import Any, Dict, Optional


CONTRACT_VERSION = 1
ACTIONABLE_RECOMMENDATIONS = {"BUY", "STRONG_BUY", "SELL", "STRONG_SELL"}


def acquire_process_singleton(path: str):
    """Acquire a non-blocking process lock; return owned handle or ``None``."""
    handle = open(path, "a+")
    try:
        fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        return handle
    except BlockingIOError:
        handle.close()
        return None


def _canonical(value: Dict[str, Any]) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), default=str)

def _freeze(value):
    if isinstance(value, dict): return MappingProxyType({k:_freeze(v) for k,v in value.items()})
    if isinstance(value, list): return tuple(_freeze(v) for v in value)
    return value

def _thaw(value):
    if isinstance(value, MappingProxyType): return {k:_thaw(v) for k,v in value.items()}
    if isinstance(value, tuple): return [_thaw(v) for v in value]
    return copy.deepcopy(value)


@dataclass(frozen=True)
class TradeIntent:
    pair: str
    recommendation: str
    confidence: float
    price: float
    signal: Dict[str, Any]
    created_at: float
    correlation_id: str
    idempotency_key: str
    version: int = CONTRACT_VERSION
    user_id: Optional[int] = None

    @classmethod
    def from_signal(cls, signal: Dict[str, Any]) -> "TradeIntent":
        payload = dict(signal or {})
        data = dict(payload.get("data") or {})
        semantic = json.loads(json.dumps(data.get("signal") or data, default=str))
        pair = str(payload.get("pair") or semantic.get("pair") or "").lower().replace("/", "").replace("_", "")
        recommendation = str(
            semantic.get("recommendation") or payload.get("signal_type") or ""
        ).upper()
        confidence = float(semantic.get("ml_confidence", payload.get("confidence", 0)) or 0)
        price = float(semantic.get("price", payload.get("price", 0)) or 0)
        created_at = float(payload.get("created_at") or datetime.now(timezone.utc).timestamp())
        semantic.update({"pair": pair, "recommendation": recommendation, "price": price})
        semantic.setdefault("ml_confidence", confidence)
        stable = {"pair": pair, "recommendation": recommendation, "price": price,
                  "signal": semantic, "created_at": created_at}
        digest = hashlib.sha256(_canonical(stable).encode()).hexdigest()
        correlation_id = str(payload.get("correlation_id") or payload.get("signal_id") or digest[:24])
        user_id=payload.get("user_id") or payload.get("source_user_id") or semantic.get("user_id")
        return cls(pair, recommendation, confidence, price, _freeze(semantic), created_at,
                   correlation_id, str(payload.get("idempotency_key") or digest),
                   int(payload.get("version", CONTRACT_VERSION)), int(user_id) if user_id is not None else None)

    def validate(self, max_age_seconds: Optional[float] = None, now: Optional[float] = None) -> Optional[str]:
        if self.version != CONTRACT_VERSION:
            return "UNSUPPORTED_CONTRACT_VERSION"
        if not self.pair:
            return "MISSING_PAIR"
        if self.recommendation not in ACTIONABLE_RECOMMENDATIONS:
            return "INVALID_RECOMMENDATION"
        if self.price <= 0:
            return "INVALID_PRICE"
        if not all(math.isfinite(x) for x in (self.price, self.confidence, self.created_at)):
            return "NON_FINITE_NUMERIC"
        current = now or datetime.now(timezone.utc).timestamp()
        if self.created_at > current + 60:
            return "FUTURE_SIGNAL"
        if max_age_seconds is not None and current - self.created_at > max_age_seconds:
            return "STALE_SIGNAL"
        return None

    def to_dict(self) -> Dict[str, Any]:
        return {"pair":self.pair,"recommendation":self.recommendation,"confidence":self.confidence,
                "price":self.price,"signal":_thaw(self.signal),"created_at":self.created_at,
                "correlation_id":self.correlation_id,"idempotency_key":self.idempotency_key,"version":self.version,
                "user_id":self.user_id}


@dataclass(frozen=True)
class ExecutionDecision:
    idempotency_key: str
    correlation_id: str
    status: str
    reason_code: str
    reason: str = ""
    order_id: Optional[str] = None
    trade_id: Optional[int] = None
    metadata: Dict[str, Any] = field(default_factory=dict)
