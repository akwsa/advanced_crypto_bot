"""Immutable, deterministic contracts for Strategy 2."""

from __future__ import annotations

from dataclasses import dataclass, field
import hashlib
import json
import math
from types import MappingProxyType
from typing import Any, Mapping

from .state_machine import validate_transition
from .taxonomy import DecisionStatus, PositionState, ReasonCode


STRATEGY_ID = "strategy2"


def _require_text(name: str, value: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{name} must be a non-empty string")
    return value.strip()


def _require_finite(name: str, value: float, *, positive: bool = False, nonnegative: bool = False) -> float:
    if isinstance(value, bool):
        raise ValueError(f"{name} must be numeric")
    try:
        number = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{name} must be numeric") from exc
    if not math.isfinite(number):
        raise ValueError(f"{name} must be finite")
    if positive and number <= 0:
        raise ValueError(f"{name} must be positive")
    if nonnegative and number < 0:
        raise ValueError(f"{name} must be non-negative")
    return number


def _normalize_pair(name: str, value: str) -> str:
    pair = _require_text(name, value).upper().replace("/", "").replace("_", "").replace("-", "")
    if not pair:
        raise ValueError(f"{name} must be non-empty")
    return pair


def _optional_text(name: str, value: Any, *, allow_empty: bool = True) -> str:
    if not isinstance(value, str):
        raise TypeError(f"{name} must be text")
    text = value.strip()
    if not allow_empty and not text:
        raise ValueError(f"{name} must be a non-empty string")
    return text


def _freeze(value: Any) -> Any:
    if isinstance(value, Mapping):
        if any(not isinstance(key, str) for key in value):
            raise TypeError("contract payload mapping keys must be strings")
        return MappingProxyType({key: _freeze(item) for key, item in value.items()})
    if isinstance(value, (list, tuple)):
        return tuple(_freeze(item) for item in value)
    if value is None or isinstance(value, (str, bool, int)):
        return value
    if isinstance(value, float):
        if not math.isfinite(value):
            raise ValueError("contract payload contains a non-finite numeric value")
        return value
    raise TypeError(f"unsupported contract payload value: {type(value).__name__}")


def stable_idempotency_key(strategy_version: str, experiment_id: str, operation_identity: str) -> str:
    payload = {
        "experiment_id": _require_text("experiment_id", experiment_id),
        "operation_identity": _require_text("operation_identity", operation_identity),
        "strategy_id": STRATEGY_ID,
        "strategy_version": _require_text("strategy_version", strategy_version),
    }
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return f"{STRATEGY_ID}:{hashlib.sha256(canonical.encode('utf-8')).hexdigest()}"


@dataclass(frozen=True)
class StrategyVersion:
    strategy_version: str
    experiment_id: str
    strategy_id: str = STRATEGY_ID

    def __post_init__(self) -> None:
        object.__setattr__(self, "strategy_version", _require_text("strategy_version", self.strategy_version))
        object.__setattr__(self, "experiment_id", _require_text("experiment_id", self.experiment_id))
        if self.strategy_id != STRATEGY_ID:
            raise ValueError(f"strategy_id must be {STRATEGY_ID!r}")

    def idempotency_key(self, operation_identity: str) -> str:
        return stable_idempotency_key(self.strategy_version, self.experiment_id, operation_identity)


@dataclass(frozen=True)
class CostAssumptions:
    buy_fee_rate: float = 0.0
    sell_fee_rate: float = 0.0
    buy_slippage_rate: float = 0.0
    sell_slippage_rate: float = 0.0
    safety_margin_rate: float = 0.0

    def __post_init__(self) -> None:
        for name in (
            "buy_fee_rate", "sell_fee_rate", "buy_slippage_rate", "sell_slippage_rate", "safety_margin_rate"
        ):
            object.__setattr__(self, name, _require_finite(name, getattr(self, name), nonnegative=True))

    @property
    def round_trip_rate(self) -> float:
        return _require_finite(
            "round_trip_rate",
            sum((
                self.buy_fee_rate,
                self.sell_fee_rate,
                self.buy_slippage_rate,
                self.sell_slippage_rate,
                self.safety_margin_rate,
            )),
            nonnegative=True,
        )


@dataclass(frozen=True)
class MarketSnapshot:
    snapshot_id: str
    pair: str
    event_time: float
    bid: float
    ask: float
    last: float
    received_at: float | None = None
    source: str = "unknown"
    timeframe: str = ""
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(self, "snapshot_id", _require_text("snapshot_id", self.snapshot_id))
        object.__setattr__(self, "pair", _normalize_pair("pair", self.pair))
        object.__setattr__(self, "event_time", _require_finite("event_time", self.event_time, positive=True))
        for name in ("bid", "ask", "last"):
            object.__setattr__(self, name, _require_finite(name, getattr(self, name), positive=True))
        if self.ask < self.bid:
            raise ValueError("ask must be greater than or equal to bid")
        if self.received_at is not None:
            object.__setattr__(self, "received_at", _require_finite("received_at", self.received_at, positive=True))
        object.__setattr__(self, "source", _optional_text("source", self.source, allow_empty=False))
        object.__setattr__(self, "timeframe", _optional_text("timeframe", self.timeframe))
        object.__setattr__(self, "metadata", _freeze(self.metadata))


@dataclass(frozen=True)
class FeatureSnapshot:
    snapshot_id: str
    event_time: float
    features: Mapping[str, Any]
    feature_version: str = "1"

    def __post_init__(self) -> None:
        object.__setattr__(self, "snapshot_id", _require_text("snapshot_id", self.snapshot_id))
        object.__setattr__(self, "event_time", _require_finite("event_time", self.event_time, positive=True))
        object.__setattr__(self, "feature_version", _require_text("feature_version", self.feature_version))
        if not isinstance(self.features, Mapping):
            raise TypeError("features must be a mapping")
        object.__setattr__(self, "features", _freeze(self.features))


@dataclass(frozen=True)
class Strategy2Decision:
    strategy: StrategyVersion
    operation_identity: str
    idempotency_key: str
    correlation_id: str
    snapshot_id: str
    pair: str
    status: DecisionStatus
    reason_code: ReasonCode
    current_state: PositionState
    next_state: PositionState
    event_time: float
    reason: str = ""
    evidence: Mapping[str, Any] = field(default_factory=dict)

    @property
    def strategy_version(self) -> str:
        return self.strategy.strategy_version

    @property
    def experiment_id(self) -> str:
        return self.strategy.experiment_id

    def __post_init__(self) -> None:
        if not isinstance(self.strategy, StrategyVersion):
            raise TypeError("strategy must be a StrategyVersion")
        for name in ("operation_identity", "idempotency_key", "correlation_id", "snapshot_id", "pair"):
            object.__setattr__(self, name, _require_text(name, getattr(self, name)))
        expected = self.strategy.idempotency_key(self.operation_identity)
        if self.idempotency_key != expected:
            raise ValueError("idempotency_key does not match the Strategy 2 namespace")
        object.__setattr__(self, "pair", _normalize_pair("pair", self.pair))
        object.__setattr__(self, "status", DecisionStatus(self.status))
        object.__setattr__(self, "reason_code", ReasonCode(self.reason_code))
        object.__setattr__(self, "current_state", PositionState(self.current_state))
        object.__setattr__(self, "next_state", PositionState(self.next_state))
        validate_transition(self.current_state, self.next_state)
        object.__setattr__(self, "event_time", _require_finite("event_time", self.event_time, positive=True))
        object.__setattr__(self, "reason", _optional_text("reason", self.reason))
        object.__setattr__(self, "evidence", _freeze(self.evidence))

    @classmethod
    def create(cls, *, strategy: StrategyVersion, operation_identity: str, **kwargs: Any) -> "Strategy2Decision":
        return cls(
            strategy=strategy,
            operation_identity=operation_identity,
            idempotency_key=strategy.idempotency_key(operation_identity),
            **kwargs,
        )
