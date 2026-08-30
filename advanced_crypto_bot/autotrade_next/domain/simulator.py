"""Pure deterministic order lifecycle simulator for DRY RUN and replay."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from enum import Enum
from hashlib import sha256

from .content import ContentRef
from .encoding import canonical_bytes
from .errors import MarketEvidenceError
from .market import MarketSnapshot, OrderBookSide
from .numeric import ScaledInteger


class SimulatorError(ValueError):
    def __init__(self, code: str) -> None:
        self.code = self.error_code = code
        self.partial_result = None
        super().__init__(code)


def _fail(code: str) -> None:
    raise SimulatorError(code)


def _units_at_scale(value: ScaledInteger, scale: int) -> int:
    if value.scale <= scale:
        return value.units * 10 ** (scale - value.scale)
    divisor = 10 ** (value.scale - scale)
    if value.units % divisor:
        raise MarketEvidenceError("SILENT_PRECISION_LOSS", path=("quantity",))
    return value.units // divisor


def _ceil_rescale(units: int, source: int, target: int) -> int:
    if source <= target:
        return units * 10 ** (target - source)
    quotient, remainder = divmod(units, 10 ** (source - target))
    return quotient + bool(remainder)


def _ceil_bps(units: int, bps: int) -> int:
    return (units * bps + 9_999) // 10_000


def _identity(domain: str, value: object) -> str:
    return sha256(canonical_bytes({"domain": domain, "value": value})).hexdigest()


class OrderStatus(str, Enum):
    ACCEPTED = "ACCEPTED"
    OPEN = "OPEN"
    PARTIAL = "PARTIAL"
    FILLED = "FILLED"
    CANCELLED = "CANCELLED"
    REJECTED = "REJECTED"
    EXPIRED = "EXPIRED"
    UNKNOWN = "UNKNOWN"


class FeeType(str, Enum):
    MAKER = "MAKER"
    TAKER = "TAKER"


class ScenarioOutcome(str, Enum):
    EXECUTE = "EXECUTE"
    REJECT = "REJECT"
    EXPIRE = "EXPIRE"
    NON_FILL = "NON_FILL"
    AMBIGUOUS = "AMBIGUOUS"


class LifecycleActionType(str, Enum):
    FILL = "FILL"
    CANCEL = "CANCEL"


@dataclass(frozen=True, slots=True)
class LifecycleAction:
    sequence: int
    action: LifecycleActionType
    recorded_at_utc: datetime

    def __post_init__(self) -> None:
        if type(self.sequence) is not int or self.sequence <= 0:
            _fail("INVALID_ACTION_SEQUENCE")
        if (type(self.action) is not LifecycleActionType
                or type(self.recorded_at_utc) is not datetime
                or self.recorded_at_utc.tzinfo is not UTC):
            _fail("INVALID_RECORDED_ACTION")

    def to_canonical_value(self) -> dict[str, object]:
        return {"sequence": self.sequence, "action": self.action.value,
                "recorded_at_utc": self.recorded_at_utc}


@dataclass(frozen=True, slots=True)
class LifecycleScenario:
    version: str
    seed: str
    latency_micros: int
    adverse_selection_bps: int
    outcome: ScenarioOutcome
    liquidity: FeeType
    actions: tuple[LifecycleAction, ...] = ()

    def __post_init__(self) -> None:
        if (type(self.version) is not str or not self.version.strip()
                or type(self.seed) is not str or not self.seed.strip()):
            _fail("INVALID_SCENARIO_IDENTITY")
        if (type(self.latency_micros) is not int or self.latency_micros < 0
                or self.latency_micros > 604_800_000_000):
            _fail("INVALID_LATENCY")
        if (type(self.adverse_selection_bps) is not int
                or not 0 <= self.adverse_selection_bps <= 10_000):
            _fail("INVALID_ADVERSE_SELECTION")
        if type(self.outcome) is not ScenarioOutcome or type(self.liquidity) is not FeeType:
            _fail("INVALID_SCENARIO_ENUM")
        if type(self.actions) is not tuple:
            _fail("MUTABLE_SCENARIO_ACTIONS")
        if any(type(action) is not LifecycleAction for action in self.actions):
            _fail("INVALID_SCENARIO_ACTION")

    def to_canonical_value(self) -> dict[str, object]:
        return {"version": self.version, "seed": self.seed,
                "latency_micros": self.latency_micros,
                "adverse_selection_bps": self.adverse_selection_bps,
                "outcome": self.outcome.value, "liquidity": self.liquidity.value,
                "actions": tuple(item.to_canonical_value() for item in self.actions)}


@dataclass(frozen=True, slots=True)
class CostRules:
    version: str
    maker_fee_bps: int
    taker_fee_bps: int
    tax_bps: int
    quote_scale: int

    def __post_init__(self) -> None:
        if type(self.version) is not str or not self.version.strip():
            _fail("INVALID_COST_VERSION")
        if any(type(getattr(self, name)) is not int or not 0 <= getattr(self, name) <= 10_000
               for name in ("maker_fee_bps", "taker_fee_bps", "tax_bps")):
            _fail("INVALID_COST_BPS")
        if type(self.quote_scale) is not int or not 0 <= self.quote_scale <= 18:
            _fail("INVALID_QUOTE_SCALE")

    def to_canonical_value(self) -> dict[str, object]:
        return {name: getattr(self, name) for name in (
            "version", "maker_fee_bps", "taker_fee_bps", "tax_bps", "quote_scale")}


@dataclass(frozen=True, slots=True)
class SimulatedFill:
    fill_id: str
    order_id: str
    price: ScaledInteger
    quantity: ScaledInteger
    fee: ScaledInteger
    fee_type: FeeType
    filled_at_utc: datetime
    notional: ScaledInteger | None = None
    tax: ScaledInteger | None = None

    def __post_init__(self) -> None:
        if type(self.fill_id) is not str or not self.fill_id.strip():
            _fail("INVALID_FILL_ID")
        if type(self.order_id) is not str or not self.order_id.strip():
            _fail("INVALID_ORDER_ID")
        if (type(self.price) is not ScaledInteger or self.price.units <= 0
                or type(self.quantity) is not ScaledInteger or self.quantity.units <= 0):
            _fail("INVALID_FILL_VALUE")
        if type(self.fee) is not ScaledInteger or self.fee.units < 0:
            _fail("INVALID_FILL_COST")
        if (type(self.fee_type) is not FeeType
                or type(self.filled_at_utc) is not datetime
                or self.filled_at_utc.tzinfo is not UTC):
            _fail("INVALID_FILL_EVIDENCE")
        if self.notional is not None and (
                type(self.notional) is not ScaledInteger or self.notional.units <= 0):
            _fail("INVALID_FILL_NOTIONAL")
        if self.tax is not None and (type(self.tax) is not ScaledInteger or self.tax.units < 0):
            _fail("INVALID_FILL_COST")

    def to_canonical_value(self) -> dict[str, object]:
        def number(value):
            return None if value is None else {"units": value.units, "scale": value.scale}
        return {"fill_id": self.fill_id, "order_id": self.order_id,
                "price": number(self.price), "quantity": number(self.quantity),
                "notional": number(self.notional), "fee": number(self.fee),
                "tax": number(self.tax), "fee_type": self.fee_type.value,
                "filled_at_utc": self.filled_at_utc}


@dataclass(frozen=True, slots=True)
class SimulatorEvent:
    event_id: str
    order_id: str
    status: OrderStatus
    filled_quantity: ScaledInteger
    remaining_quantity: ScaledInteger
    average_price: ScaledInteger
    fills: tuple[SimulatedFill, ...]
    event_at_utc: datetime
    event_ref: ContentRef
    sequence: int = 1
    schema_version: str = "simulator-event:v1"

    def __post_init__(self) -> None:
        if type(self.event_id) is not str or not self.event_id.strip():
            _fail("INVALID_EVENT_ID")
        if type(self.order_id) is not str or not self.order_id.strip():
            _fail("INVALID_ORDER_ID")
        if type(self.status) is not OrderStatus:
            _fail("INVALID_ORDER_STATUS")
        if type(self.sequence) is not int or self.sequence <= 0:
            _fail("INVALID_EVENT_SEQUENCE")
        if type(self.schema_version) is not str or not self.schema_version.strip():
            _fail("INVALID_EVENT_SCHEMA")
        if type(self.event_at_utc) is not datetime or self.event_at_utc.tzinfo is not UTC:
            _fail("INVALID_EVENT_TIME")
        if type(self.fills) is not tuple or any(type(fill) is not SimulatedFill for fill in self.fills):
            _fail("INVALID_EVENT_FILLS")
        if any(fill.order_id != self.order_id for fill in self.fills):
            _fail("INVALID_EVENT_FILLS")
        for value in (self.filled_quantity, self.remaining_quantity, self.average_price):
            if type(value) is not ScaledInteger or value.units < 0:
                _fail("INVALID_EVENT_VALUE")
        fill_status = self.status in (OrderStatus.PARTIAL, OrderStatus.FILLED)
        if fill_status and not self.fills:
            _fail("INVALID_EVENT_FILLS")
        if bool(self.fills) != (self.filled_quantity.units > 0):
            _fail("INVALID_EVENT_FILLS")
        if self.fills:
            quantity_scale = self.filled_quantity.scale
            fill_units = sum(_units_at_scale(fill.quantity, quantity_scale)
                             for fill in self.fills)
            if fill_units != self.filled_quantity.units:
                _fail("INVALID_EVENT_FILLS")
        if self.fills and self.average_price.units <= 0:
            _fail("INVALID_EVENT_VALUE")
        if self.status is OrderStatus.FILLED and self.remaining_quantity.units != 0:
            _fail("INVALID_TERMINAL_QUANTITY")
        if self.status is OrderStatus.PARTIAL and self.remaining_quantity.units <= 0:
            _fail("INVALID_TERMINAL_QUANTITY")
        if (self.status in (OrderStatus.ACCEPTED, OrderStatus.OPEN, OrderStatus.REJECTED)
                and self.filled_quantity.units != 0):
            _fail("INVALID_EVENT_VALUE")
        if type(self.event_ref) is not ContentRef or not self.event_ref.verify(self.binding_value()):
            _fail("EVENT_REFERENCE_MISMATCH")

    def binding_value(self) -> dict[str, object]:
        return {"schema_version": self.schema_version, "event_id": self.event_id,
                "sequence": self.sequence, "order_id": self.order_id,
                "status": self.status.value, "filled_quantity": self.filled_quantity,
                "remaining_quantity": self.remaining_quantity, "average_price": self.average_price,
                "fills": tuple(fill.to_canonical_value() for fill in self.fills),
                "event_at_utc": self.event_at_utc}

    @classmethod
    def create(cls, *, event_id, order_id, status, filled_quantity, remaining_quantity,
               average_price, fills, event_at_utc, sequence=1,
               schema_version="simulator-event:v1"):
        if type(status) is not OrderStatus:
            _fail("INVALID_ORDER_STATUS")
        if type(fills) not in (tuple, list):
            _fail("INVALID_EVENT_FILLS")
        frozen = tuple(fills)
        value = {"schema_version": schema_version, "event_id": event_id,
                 "sequence": sequence, "order_id": order_id, "status": status.value,
                 "filled_quantity": filled_quantity, "remaining_quantity": remaining_quantity,
                 "average_price": average_price,
                 "fills": tuple(fill.to_canonical_value() for fill in frozen),
                 "event_at_utc": event_at_utc}
        return cls(event_id, order_id, status, filled_quantity, remaining_quantity,
                   average_price, frozen, event_at_utc,
                   ContentRef.v2("simulator.event", "simulator-event", value),
                   sequence, schema_version)


@dataclass(frozen=True, slots=True)
class LifecycleResult:
    events: tuple[SimulatorEvent, ...]
    latest_event: SimulatorEvent
    entry_frozen: bool
    is_terminal: bool

    @property
    def terminal_event(self) -> SimulatorEvent:
        """Compatibility alias; callers should inspect ``is_terminal``."""
        return self.latest_event


_LEGAL = {
    None: {OrderStatus.ACCEPTED, OrderStatus.REJECTED},
    OrderStatus.ACCEPTED: {OrderStatus.OPEN, OrderStatus.REJECTED, OrderStatus.UNKNOWN},
    OrderStatus.OPEN: {OrderStatus.PARTIAL, OrderStatus.FILLED, OrderStatus.CANCELLED,
                       OrderStatus.EXPIRED, OrderStatus.UNKNOWN},
    OrderStatus.PARTIAL: {OrderStatus.PARTIAL, OrderStatus.FILLED, OrderStatus.CANCELLED,
                          OrderStatus.EXPIRED, OrderStatus.UNKNOWN},
}


def reduce_lifecycle(events) -> LifecycleResult:
    seen, accepted = {}, []
    previous_status, previous_sequence, order_id = None, 0, None
    quantity_scale = total_quantity = previous_filled = previous_remaining = None
    previous_fills: tuple[SimulatedFill, ...] = ()
    for event in events:
        if type(event) is not SimulatorEvent:
            _fail("INVALID_LIFECYCLE_EVENT")
        duplicate = seen.get(event.event_id)
        if duplicate is not None:
            if duplicate == event:
                continue
            _fail("CONFLICTING_DUPLICATE_EVENT")
        if event.sequence != previous_sequence + 1:
            _fail("OUT_OF_ORDER_EVENT")
        if accepted and event.event_at_utc < accepted[-1].event_at_utc:
            _fail("EVENT_TIME_REGRESSION")
        if order_id is not None and event.order_id != order_id:
            _fail("MIXED_ORDER_STREAM")
        if event.status not in _LEGAL.get(previous_status, set()):
            _fail("ILLEGAL_TRANSITION")
        if not event.event_ref.verify(event.binding_value()):
            _fail("EVENT_REFERENCE_MISMATCH")
        seen[event.event_id] = event
        if quantity_scale is None:
            quantity_scale = event.filled_quantity.scale
            if event.remaining_quantity.scale != quantity_scale:
                _fail("INCONSISTENT_QUANTITY_SCALE")
            total_quantity = event.filled_quantity.units + event.remaining_quantity.units
        elif (event.filled_quantity.scale != quantity_scale
              or event.remaining_quantity.scale != quantity_scale):
            _fail("INCONSISTENT_QUANTITY_SCALE")
        if event.filled_quantity.units + event.remaining_quantity.units != total_quantity:
            _fail("QUANTITY_CONSERVATION_BREACH")
        if (previous_filled is not None
                and (event.filled_quantity.units < previous_filled
                     or event.remaining_quantity.units > previous_remaining)):
            _fail("QUANTITY_REGRESSION")
        if event.fills[:len(previous_fills)] != previous_fills:
            _fail("FILL_PREFIX_CONFLICT")
        accepted.append(event)
        order_id, previous_sequence, previous_status = event.order_id, event.sequence, event.status
        previous_filled = event.filled_quantity.units
        previous_remaining = event.remaining_quantity.units
        previous_fills = event.fills
    if not accepted:
        _fail("EMPTY_EVENT_STREAM")
    terminal = accepted[-1].status in {
        OrderStatus.FILLED, OrderStatus.CANCELLED, OrderStatus.REJECTED,
        OrderStatus.EXPIRED, OrderStatus.UNKNOWN,
    }
    return LifecycleResult(
        tuple(accepted), accepted[-1],
        accepted[-1].status is OrderStatus.UNKNOWN, terminal)


@dataclass(frozen=True, slots=True)
class OrderSimulator:
    seed: int
    maker_fee_bps: int = 10
    taker_fee_bps: int = 20

    def __post_init__(self) -> None:
        if type(self.seed) is not int:
            _fail("INVALID_ENGINE_SEED")
        if any(type(value) is not int or not 0 <= value <= 10_000
               for value in (self.maker_fee_bps, self.taker_fee_bps)):
            _fail("INVALID_COST_BPS")

    def _event(self, order_id, status, sequence, filled, remaining, average, fills, at, context):
        event_id = "sim-evt-" + _identity("simulator.event-id", {
            **context, "order_id": order_id, "sequence": sequence, "status": status.value})[:32]
        return SimulatorEvent.create(event_id=event_id, order_id=order_id, status=status,
            filled_quantity=filled, remaining_quantity=remaining, average_price=average,
            fills=fills, event_at_utc=at, sequence=sequence)

    def simulate_lifecycle(self, *, order_id, side, requested_size, snapshot,
                           evaluated_at_utc, scenario, cost_rules):
        if type(order_id) is not str or not order_id.strip():
            _fail("INVALID_ORDER_ID")
        if type(snapshot) is not MarketSnapshot:
            _fail("INVALID_MARKET_SNAPSHOT")
        if type(side) is not OrderBookSide or side is not snapshot.execution_side:
            _fail("EXECUTION_SIDE_MISMATCH")
        if type(requested_size) is not ScaledInteger or requested_size.units <= 0:
            _fail("INVALID_REQUESTED_SIZE")
        if type(scenario) is not LifecycleScenario or type(cost_rules) is not CostRules:
            _fail("INVALID_SIMULATOR_INPUT")
        if type(evaluated_at_utc) is not datetime or evaluated_at_utc.tzinfo is not UTC:
            _fail("INVALID_EVALUATION_TIME")
        scale = snapshot.rules.quantity_scale
        requested = _units_at_scale(requested_size, scale)
        if requested != _units_at_scale(snapshot.requested_size, scale):
            _fail("REQUESTED_SIZE_MISMATCH")
        zero_q, zero_p = ScaledInteger(0, scale), ScaledInteger(0, snapshot.rules.price_scale)
        context = {"engine_seed": self.seed, "scenario": scenario.to_canonical_value(),
                   "cost_rules": cost_rules.to_canonical_value(),
                   "snapshot_ref": snapshot.snapshot_ref.to_canonical_value()}
        events = []

        def add(status, filled=zero_q, remaining=None, average=zero_p, fills=(), at=evaluated_at_utc):
            remaining = ScaledInteger(requested, scale) if remaining is None else remaining
            events.append(self._event(order_id, status, len(events) + 1, filled, remaining,
                                      average, fills, at, context))

        if scenario.outcome is ScenarioOutcome.REJECT:
            add(OrderStatus.REJECTED)
            return reduce_lifecycle(events)
        add(OrderStatus.ACCEPTED)
        open_time = evaluated_at_utc + timedelta(microseconds=scenario.latency_micros)
        add(OrderStatus.OPEN, at=open_time)
        terminals = {ScenarioOutcome.EXPIRE: OrderStatus.EXPIRED,
                     ScenarioOutcome.NON_FILL: OrderStatus.CANCELLED,
                     ScenarioOutcome.AMBIGUOUS: OrderStatus.UNKNOWN}
        if scenario.outcome in terminals:
            add(terminals[scenario.outcome], at=open_time)
            return reduce_lifecycle(events)
        ordered: tuple[LifecycleAction, ...] = ()
        recorded_fill: LifecycleAction | None = None
        recorded_cancel: LifecycleAction | None = None
        if scenario.actions:
            ordered = tuple(sorted(scenario.actions, key=lambda item: item.sequence))
            sequences = tuple(item.sequence for item in ordered)
            times = tuple(item.recorded_at_utc for item in ordered)
            action_evidence_valid = (
                sequences == tuple(range(1, len(ordered) + 1))
                and all(left < right for left, right in zip(times, times[1:]))
                and all(value >= open_time for value in times)
                and sum(item.action is LifecycleActionType.FILL for item in ordered) <= 1
                and sum(item.action is LifecycleActionType.CANCEL for item in ordered) <= 1
            )
            if not action_evidence_valid:
                add(OrderStatus.UNKNOWN, at=open_time)
                return reduce_lifecycle(events)
            recorded_fill = next(
                (item for item in ordered if item.action is LifecycleActionType.FILL), None)
            recorded_cancel = next(
                (item for item in ordered if item.action is LifecycleActionType.CANCEL), None)
            if recorded_cancel is not None and (
                    recorded_fill is None or recorded_cancel.sequence < recorded_fill.sequence):
                add(OrderStatus.CANCELLED, at=recorded_cancel.recorded_at_utc)
                return reduce_lifecycle(events)

        levels = snapshot.asks if side is OrderBookSide.ASK else snapshot.bids
        remaining, fills, total_notional = requested, [], 0
        for index, level in enumerate(levels, 1):
            take = min(remaining, _units_at_scale(level.quantity, scale))
            if take <= 0:
                continue
            base = _units_at_scale(level.price, snapshot.rules.price_scale)
            adverse = _ceil_bps(base, scenario.adverse_selection_bps)
            price = base + adverse if side is OrderBookSide.ASK else max(0, base - adverse)
            if price <= 0:
                _fail("NONPOSITIVE_ADVERSE_PRICE")
            raw = take * price
            notional = _ceil_rescale(raw, scale + snapshot.rules.price_scale, cost_rules.quote_scale)
            fee_bps = cost_rules.maker_fee_bps if scenario.liquidity is FeeType.MAKER else cost_rules.taker_fee_bps
            fill_time = (recorded_fill.recorded_at_utc if recorded_fill is not None
                         else open_time + timedelta(microseconds=index))
            fill_context = {**context, "order_id": order_id, "level": index,
                            "quantity": take, "price": price}
            fills.append(SimulatedFill(
                "fill-" + _identity("simulator.fill-id", fill_context)[:32], order_id,
                ScaledInteger(price, snapshot.rules.price_scale), ScaledInteger(take, scale),
                ScaledInteger(_ceil_rescale(
                    raw * fee_bps, scale + snapshot.rules.price_scale + 4,
                    cost_rules.quote_scale), cost_rules.quote_scale),
                scenario.liquidity, fill_time, ScaledInteger(notional, cost_rules.quote_scale),
                ScaledInteger(_ceil_rescale(
                    raw * cost_rules.tax_bps, scale + snapshot.rules.price_scale + 4,
                    cost_rules.quote_scale), cost_rules.quote_scale)))
            remaining -= take
            total_notional += raw
            filled = requested - remaining
            average, remainder = divmod(total_notional, filled)
            average += bool(remainder and side is OrderBookSide.ASK)
            status = OrderStatus.FILLED if remaining == 0 else OrderStatus.PARTIAL
            add(status, ScaledInteger(filled, scale), ScaledInteger(remaining, scale),
                ScaledInteger(average, snapshot.rules.price_scale), tuple(fills), fill_time)
            if remaining == 0:
                break
        if not fills:
            add(OrderStatus.REJECTED, at=open_time)
        elif remaining > 0 and recorded_cancel is not None:
            add(OrderStatus.CANCELLED, ScaledInteger(requested - remaining, scale),
                ScaledInteger(remaining, scale),
                events[-1].average_price, tuple(fills), recorded_cancel.recorded_at_utc)
        return reduce_lifecycle(events)

    def simulate_execution(self, *, order_id, side, requested_size, snapshot, evaluated_at_utc):
        scenario = LifecycleScenario("compatibility:v1", str(self.seed), 0, 0,
                                     ScenarioOutcome.EXECUTE, FeeType.TAKER, ())
        costs = CostRules("compatibility:v1", self.maker_fee_bps, self.taker_fee_bps, 0,
                          snapshot.rules.quantity_scale + snapshot.rules.price_scale)
        return self.simulate_lifecycle(order_id=order_id, side=side,
            requested_size=requested_size, snapshot=snapshot, evaluated_at_utc=evaluated_at_utc,
            scenario=scenario, cost_rules=costs).terminal_event


__all__ = ("CostRules", "FeeType", "LifecycleAction", "LifecycleActionType",
           "LifecycleResult", "LifecycleScenario", "OrderSimulator", "OrderStatus",
           "ScenarioOutcome", "SimulatedFill", "SimulatorError", "SimulatorEvent",
           "reduce_lifecycle")
