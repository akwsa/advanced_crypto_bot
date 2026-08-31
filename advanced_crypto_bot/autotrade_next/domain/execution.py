"""Pure fill-authoritative execution and settlement kernel."""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import UTC, datetime
from enum import Enum

from .content import ContentRef
from .identity import DeterministicIdentity, build_identity
from .numeric import ScaledInteger
from .simulator import OrderStatus, SimulatedFill, SimulatorEvent


MAX_SETTLEMENT_INPUT_SCALE = 18
MAX_SETTLEMENT_PRODUCT_SCALE = MAX_SETTLEMENT_INPUT_SCALE * 2


class ExecutionError(ValueError):
    """Reject an execution transition without exposing partial state."""

    def __init__(self, code: str) -> None:
        self.code = self.error_code = code
        self.partial_result = None
        self.severity = "ERROR"
        self.retryable = False
        super().__init__(code)


def _fail(code: str) -> None:
    raise ExecutionError(code)


def _reference(value: object, code: str = "INVALID_EXECUTION_REFERENCE") -> str:
    if type(value) is not str or not value.strip():
        _fail(code)
    return value


def _utc(value: object) -> datetime:
    if type(value) is not datetime or value.tzinfo is not UTC:
        _fail("INVALID_EXECUTION_TIME")
    return value


def _positive(value: object, code: str) -> ScaledInteger:
    if (type(value) is not ScaledInteger or value.units <= 0
            or value.scale > MAX_SETTLEMENT_INPUT_SCALE):
        _fail(code)
    return value


def _nonnegative(value: object, code: str) -> ScaledInteger:
    if (type(value) is not ScaledInteger or value.units < 0
            or value.scale > MAX_SETTLEMENT_INPUT_SCALE):
        _fail(code)
    return value


def _at_scale(value: ScaledInteger, scale: int) -> int:
    """Represent ``value`` at a common scale without rounding."""
    if (type(scale) is not int or scale < value.scale
            or scale > MAX_SETTLEMENT_PRODUCT_SCALE
            or scale - value.scale > MAX_SETTLEMENT_INPUT_SCALE):
        _fail("INTERNAL_SCALE_REGRESSION")
    return value.units * 10 ** (scale - value.scale)


def _rescale_exact(value: ScaledInteger, scale: int, code: str) -> ScaledInteger:
    if type(scale) is not int or not 0 <= scale <= MAX_SETTLEMENT_INPUT_SCALE:
        _fail("SCALE_OUT_OF_RANGE")
    if value.scale <= scale:
        return ScaledInteger(_at_scale(value, scale), scale)
    divisor = 10 ** (value.scale - scale)
    quotient, remainder = divmod(value.units, divisor)
    if remainder:
        _fail(code)
    return ScaledInteger(quotient, scale)


def _rescale_ceil(value: ScaledInteger, scale: int, code: str) -> ScaledInteger:
    """Match the simulator's conservative quote-scale notional evidence."""
    if type(scale) is not int or not 0 <= scale <= MAX_SETTLEMENT_INPUT_SCALE:
        _fail("SCALE_OUT_OF_RANGE")
    if value.scale <= scale:
        return ScaledInteger(_at_scale(value, scale), scale)
    divisor = 10 ** (value.scale - scale)
    quotient, remainder = divmod(value.units, divisor)
    if value.units < 0:
        _fail(code)
    return ScaledInteger(quotient + bool(remainder), scale)


def _same(left: ScaledInteger, right: ScaledInteger) -> bool:
    scale = max(left.scale, right.scale)
    return _at_scale(left, scale) == _at_scale(right, scale)


def _sum(values: tuple[ScaledInteger, ...], *, minimum_scale: int = 0) -> ScaledInteger:
    scale = max((value.scale for value in values), default=minimum_scale)
    scale = max(scale, minimum_scale)
    return ScaledInteger(sum(_at_scale(value, scale) for value in values), scale)


def _add(left: ScaledInteger, right: ScaledInteger) -> ScaledInteger:
    scale = max(left.scale, right.scale)
    return ScaledInteger(_at_scale(left, scale) + _at_scale(right, scale), scale)


def _subtract(left: ScaledInteger, right: ScaledInteger) -> ScaledInteger:
    scale = max(left.scale, right.scale)
    return ScaledInteger(_at_scale(left, scale) - _at_scale(right, scale), scale)


def _multiply(left: ScaledInteger, right: ScaledInteger) -> ScaledInteger:
    return ScaledInteger(left.units * right.units, left.scale + right.scale)


def _number(value: ScaledInteger) -> dict[str, int]:
    return {"units": value.units, "scale": value.scale}


def _validate_fill_evidence(fill: SimulatedFill) -> None:
    _positive(fill.quantity, "INVALID_FILL_EVIDENCE")
    _positive(fill.price, "INVALID_FILL_EVIDENCE")
    _nonnegative(fill.fee, "INVALID_FILL_COST")
    if fill.notional is None or fill.tax is None:
        _fail("MISSING_FILL_COST_EVIDENCE")
    _positive(fill.notional, "INVALID_FILL_NOTIONAL")
    _nonnegative(fill.tax, "INVALID_FILL_COST")
    _utc(fill.filled_at_utc)


def _validate_event_fill_times(
    event: SimulatorEvent,
    *,
    previous_fill_count: int,
) -> None:
    """Reject fill timestamps that claim knowledge after their receipt."""
    new_fills = event.fills[previous_fill_count:]
    if any(fill.filled_at_utc > event.event_at_utc for fill in new_fills):
        _fail("FILL_TIME_AFTER_EVENT")


def _validate_terminal_status(event: SimulatorEvent) -> None:
    if event.remaining_quantity.units == 0 and event.status is not OrderStatus.FILLED:
        _fail("TERMINAL_STATUS_MISMATCH")


class ExecutionSide(str, Enum):
    BUY = "BUY"
    SELL = "SELL"


class OutboxStatus(str, Enum):
    PENDING = "PENDING"


@dataclass(frozen=True, slots=True)
class ExecutionIntent:
    intent_id: DeterministicIdentity
    decision_id: str
    authority_scope_id: str
    account_id: str
    instrument_id: str
    side: ExecutionSide
    requested_quantity: ScaledInteger
    created_at_utc: datetime
    intent_ref: ContentRef

    def __post_init__(self) -> None:
        for value in (self.decision_id, self.authority_scope_id,
                      self.account_id, self.instrument_id):
            _reference(value)
        if type(self.side) is not ExecutionSide:
            _fail("INVALID_EXECUTION_SIDE")
        _positive(self.requested_quantity, "INVALID_REQUESTED_QUANTITY")
        _utc(self.created_at_utc)
        expected = build_identity("intent", {"decision_id": self.decision_id})
        if type(self.intent_id) is not DeterministicIdentity or self.intent_id != expected:
            _fail("INVALID_INTENT_ID")
        if type(self.intent_ref) is not ContentRef or not self.intent_ref.verify(
                self.binding_value()):
            _fail("INTENT_REFERENCE_MISMATCH")

    def binding_value(self) -> dict[str, object]:
        return {
            "schema_version": "execution-intent:v1",
            "intent_id": self.intent_id.key,
            "decision_id": self.decision_id,
            "authority_scope_id": self.authority_scope_id,
            "account_id": self.account_id,
            "instrument_id": self.instrument_id,
            "side": self.side.value,
            "requested_quantity": _number(self.requested_quantity),
            "created_at_utc": self.created_at_utc,
        }


@dataclass(frozen=True, slots=True)
class ExecutionOrder:
    order_id: DeterministicIdentity
    intent_id: str
    authority_scope_id: str
    account_id: str
    instrument_id: str
    side: ExecutionSide
    requested_quantity: ScaledInteger
    order_ordinal: int
    created_at_utc: datetime
    order_ref: ContentRef

    def __post_init__(self) -> None:
        for value in (self.intent_id, self.authority_scope_id,
                      self.account_id, self.instrument_id):
            _reference(value)
        if type(self.side) is not ExecutionSide:
            _fail("INVALID_EXECUTION_SIDE")
        _positive(self.requested_quantity, "INVALID_REQUESTED_QUANTITY")
        if type(self.order_ordinal) is not int or self.order_ordinal != 0:
            _fail("INVALID_ORDER_ORDINAL")
        _utc(self.created_at_utc)
        expected = build_identity("client_order", {
            "authority_scope_id": self.authority_scope_id,
            "intent_id": self.intent_id,
            "order_ordinal": self.order_ordinal,
        })
        if type(self.order_id) is not DeterministicIdentity or self.order_id != expected:
            _fail("INVALID_ORDER_ID")
        if type(self.order_ref) is not ContentRef or not self.order_ref.verify(
                self.binding_value()):
            _fail("ORDER_REFERENCE_MISMATCH")

    def binding_value(self) -> dict[str, object]:
        return {
            "schema_version": "execution-order:v1",
            "order_id": self.order_id.key,
            "intent_id": self.intent_id,
            "authority_scope_id": self.authority_scope_id,
            "account_id": self.account_id,
            "instrument_id": self.instrument_id,
            "side": self.side.value,
            "requested_quantity": _number(self.requested_quantity),
            "order_ordinal": self.order_ordinal,
            "created_at_utc": self.created_at_utc,
        }


@dataclass(frozen=True, slots=True)
class OutboxMessage:
    message_id: DeterministicIdentity
    authority_scope_id: str
    aggregate_id: str
    aggregate_sequence: int
    event_type: str
    payload_ref: ContentRef
    status: OutboxStatus
    created_at_utc: datetime

    def __post_init__(self) -> None:
        _reference(self.authority_scope_id)
        _reference(self.aggregate_id)
        _reference(self.event_type)
        if type(self.aggregate_sequence) is not int or self.aggregate_sequence <= 0:
            _fail("INVALID_OUTBOX_SEQUENCE")
        if type(self.payload_ref) is not ContentRef:
            _fail("INVALID_OUTBOX_PAYLOAD")
        if type(self.status) is not OutboxStatus:
            _fail("INVALID_OUTBOX_STATUS")
        _utc(self.created_at_utc)
        expected = build_identity("event", {
            "authority_scope_id": self.authority_scope_id,
            "aggregate_id": self.aggregate_id,
            "aggregate_seq": self.aggregate_sequence,
            "event_type": self.event_type,
            "schema_version": 1,
        })
        if type(self.message_id) is not DeterministicIdentity or self.message_id != expected:
            _fail("INVALID_OUTBOX_ID")

@dataclass(frozen=True, slots=True)
class OrderSettlementState:
    order: ExecutionOrder
    last_sequence: int
    status: OrderStatus | None
    filled_quantity: ScaledInteger
    remaining_quantity: ScaledInteger
    cumulative_fills: tuple[SimulatedFill, ...]
    receipts: tuple[SimulatorEvent, ...]
    entry_frozen: bool

    def __post_init__(self) -> None:
        if type(self.order) is not ExecutionOrder:
            _fail("INVALID_ORDER_STATE")
        if type(self.last_sequence) is not int or self.last_sequence < 0:
            _fail("INVALID_ORDER_SEQUENCE")
        if self.status is not None and type(self.status) is not OrderStatus:
            _fail("INVALID_ORDER_STATUS")
        for value in (self.filled_quantity, self.remaining_quantity):
            _nonnegative(value, "INVALID_ORDER_QUANTITY")
        if (self.filled_quantity.scale != self.order.requested_quantity.scale
                or self.remaining_quantity.scale != self.order.requested_quantity.scale):
            _fail("ORDER_QUANTITY_SCALE_MISMATCH")
        if not _same(
            _add(self.filled_quantity, self.remaining_quantity),
            self.order.requested_quantity,
        ):
            _fail("QUANTITY_CONSERVATION_BREACH")
        if type(self.cumulative_fills) is not tuple or type(self.receipts) is not tuple:
            _fail("MUTABLE_ORDER_EVIDENCE")
        if any(type(fill) is not SimulatedFill for fill in self.cumulative_fills):
            _fail("INVALID_FILL_EVIDENCE")
        for fill in self.cumulative_fills:
            _validate_fill_evidence(fill)
        if len({fill.fill_id for fill in self.cumulative_fills}) != len(
                self.cumulative_fills):
            _fail("DUPLICATE_FILL_ID")
        if any(type(event) is not SimulatorEvent for event in self.receipts):
            _fail("INVALID_EVENT_EVIDENCE")
        if self.last_sequence != len(self.receipts):
            _fail("ORDER_SEQUENCE_EVIDENCE_MISMATCH")
        if self.receipts:
            if any(event.order_id != self.order.order_id.key
                   or event.sequence != index
                   for index, event in enumerate(self.receipts, 1)):
                _fail("ORDER_SEQUENCE_EVIDENCE_MISMATCH")
            if len({event.event_id for event in self.receipts}) != len(self.receipts):
                _fail("CONFLICTING_DUPLICATE_EVENT")
            previous_status = None
            previous_fills: tuple[SimulatedFill, ...] = ()
            previous_time: datetime | None = None
            for event in self.receipts:
                if event.schema_version != "simulator-event:v1":
                    _fail("UNSUPPORTED_EVENT_SCHEMA")
                if previous_time is not None and event.event_at_utc < previous_time:
                    _fail("EVENT_TIME_REGRESSION")
                if event.status not in _LEGAL.get(previous_status, set()):
                    _fail("ILLEGAL_TRANSITION")
                if event.fills[:len(previous_fills)] != previous_fills:
                    _fail("FILL_PREFIX_CONFLICT")
                _validate_event_fill_times(
                    event,
                    previous_fill_count=len(previous_fills),
                )
                _validate_terminal_status(event)
                previous_status = event.status
                previous_fills = event.fills
                previous_time = event.event_at_utc
            latest = self.receipts[-1]
            if latest.sequence != self.last_sequence or latest.status is not self.status:
                _fail("ORDER_SEQUENCE_EVIDENCE_MISMATCH")
            if latest.fills != self.cumulative_fills:
                _fail("FILL_PREFIX_CONFLICT")
            if (not _same(latest.filled_quantity, self.filled_quantity)
                    or not _same(latest.remaining_quantity, self.remaining_quantity)):
                _fail("ORDER_QUANTITY_EVIDENCE_MISMATCH")
        elif self.status is not None or self.cumulative_fills:
            _fail("ORDER_SEQUENCE_EVIDENCE_MISMATCH")
        if type(self.entry_frozen) is not bool:
            _fail("INVALID_ENTRY_FREEZE")
        if self.status is OrderStatus.UNKNOWN and not self.entry_frozen:
            _fail("UNKNOWN_NOT_FROZEN")


@dataclass(frozen=True, slots=True)
class AccountState:
    account_id: str
    instrument_id: str
    cash_balance: ScaledInteger
    position_quantity: ScaledInteger
    fees_paid: ScaledInteger
    taxes_paid: ScaledInteger
    processed_fill_ids: tuple[str, ...]
    revision: int = 0

    def __post_init__(self) -> None:
        _reference(self.account_id)
        _reference(self.instrument_id)
        for value in (self.cash_balance, self.position_quantity,
                      self.fees_paid, self.taxes_paid):
            _nonnegative(value, "INVALID_ACCOUNT_VALUE")
        if type(self.processed_fill_ids) is not tuple:
            _fail("MUTABLE_FILL_IDS")
        if any(type(value) is not str or not value.strip()
               for value in self.processed_fill_ids):
            _fail("INVALID_FILL_ID")
        if len(set(self.processed_fill_ids)) != len(self.processed_fill_ids):
            _fail("DUPLICATE_PROCESSED_FILL")
        if type(self.revision) is not int or self.revision < 0:
            _fail("INVALID_ACCOUNT_REVISION")


@dataclass(frozen=True, slots=True)
class SettlementEntry:
    authority_scope_id: str
    account_id: str
    instrument_id: str
    order_id: str
    event_id: str
    side: ExecutionSide
    fill_id: str
    quantity: ScaledInteger
    notional: ScaledInteger
    fee: ScaledInteger
    tax: ScaledInteger
    cash_delta: ScaledInteger
    quantity_delta: ScaledInteger
    recorded_at_utc: datetime

    def __post_init__(self) -> None:
        for value in (self.authority_scope_id, self.account_id, self.instrument_id,
                      self.order_id, self.event_id, self.fill_id):
            _reference(value, "INVALID_SETTLEMENT_ENTRY")
        if type(self.side) is not ExecutionSide:
            _fail("INVALID_SETTLEMENT_ENTRY")
        _positive(self.quantity, "INVALID_SETTLEMENT_ENTRY")
        _positive(self.notional, "INVALID_SETTLEMENT_ENTRY")
        for value in (self.fee, self.tax):
            _nonnegative(value, "INVALID_SETTLEMENT_ENTRY")
        for value in (self.cash_delta, self.quantity_delta):
            if type(value) is not ScaledInteger or value.scale > MAX_SETTLEMENT_INPUT_SCALE:
                _fail("INVALID_SETTLEMENT_ENTRY")
        _utc(self.recorded_at_utc)


@dataclass(frozen=True, slots=True)
class ExecutionPreparation:
    intent: ExecutionIntent
    order: ExecutionOrder
    order_state: OrderSettlementState
    outbox: OutboxMessage

    def __post_init__(self) -> None:
        if (type(self.intent) is not ExecutionIntent
                or type(self.order) is not ExecutionOrder
                or type(self.order_state) is not OrderSettlementState
                or type(self.outbox) is not OutboxMessage):
            _fail("INVALID_EXECUTION_PREPARATION")
        if (self.order.intent_id != self.intent.intent_id.key
                or self.order.authority_scope_id != self.intent.authority_scope_id
                or self.order.account_id != self.intent.account_id
                or self.order.instrument_id != self.intent.instrument_id
                or self.order.side is not self.intent.side
                or not _same(self.order.requested_quantity,
                             self.intent.requested_quantity)
                or self.order_state.order != self.order
                or self.outbox.aggregate_id != self.intent.intent_id.key
                or self.outbox.aggregate_sequence != 1
                or self.outbox.event_type != "IntentPrepared"
                or self.outbox.payload_ref != self.order.order_ref):
            _fail("EXECUTION_PREPARATION_MISMATCH")


@dataclass(frozen=True, slots=True)
class DispatchEnvelope:
    intent_id: str
    order_id: str
    payload_ref: ContentRef

    def __post_init__(self) -> None:
        _reference(self.intent_id, "INVALID_DISPATCH_ENVELOPE")
        _reference(self.order_id, "INVALID_DISPATCH_ENVELOPE")
        if type(self.payload_ref) is not ContentRef:
            _fail("INVALID_DISPATCH_ENVELOPE")


@dataclass(frozen=True, slots=True)
class SettlementResult:
    order_state: OrderSettlementState
    account: AccountState
    entries: tuple[SettlementEntry, ...]
    outbox: OutboxMessage | None
    is_noop: bool

    def __post_init__(self) -> None:
        if (type(self.order_state) is not OrderSettlementState
                or type(self.account) is not AccountState
                or type(self.entries) is not tuple
                or any(type(entry) is not SettlementEntry for entry in self.entries)
                or (self.outbox is not None and type(self.outbox) is not OutboxMessage)
                or type(self.is_noop) is not bool):
            _fail("INVALID_SETTLEMENT_RESULT")
        if self.is_noop and (self.entries or self.outbox is not None):
            _fail("INVALID_SETTLEMENT_NOOP")


def _outbox(*, authority_scope_id: str, aggregate_id: str, sequence: int,
            event_type: str, payload_ref: ContentRef, at: datetime) -> OutboxMessage:
    identity = build_identity("event", {
        "authority_scope_id": authority_scope_id,
        "aggregate_id": aggregate_id,
        "aggregate_seq": sequence,
        "event_type": event_type,
        "schema_version": 1,
    })
    return OutboxMessage(identity, authority_scope_id, aggregate_id, sequence, event_type,
                         payload_ref, OutboxStatus.PENDING, at)


def prepare_execution(*, decision_id: str, authority_scope_id: str, account_id: str,
                      instrument_id: str, side: ExecutionSide,
                      requested_quantity: ScaledInteger, order_ordinal: int,
                      created_at_utc: datetime) -> ExecutionPreparation:
    """Build deterministic Intent, Order and pending dispatch in one pure value."""
    intent_id = build_identity("intent", {"decision_id": decision_id})
    intent_value = {
        "schema_version": "execution-intent:v1", "intent_id": intent_id.key,
        "decision_id": decision_id, "authority_scope_id": authority_scope_id,
        "account_id": account_id, "instrument_id": instrument_id,
        "side": side.value if type(side) is ExecutionSide else side,
        "requested_quantity": _number(requested_quantity)
        if type(requested_quantity) is ScaledInteger else requested_quantity,
        "created_at_utc": created_at_utc,
    }
    intent = ExecutionIntent(
        intent_id, decision_id, authority_scope_id, account_id, instrument_id,
        side, requested_quantity, created_at_utc,
        ContentRef.v2("execution.intent", "execution-intent", intent_value),
    )
    order_id = build_identity("client_order", {
        "authority_scope_id": authority_scope_id,
        "intent_id": intent_id.key,
        "order_ordinal": order_ordinal,
    })
    order_value = {
        "schema_version": "execution-order:v1", "order_id": order_id.key,
        "intent_id": intent_id.key, "authority_scope_id": authority_scope_id,
        "account_id": account_id, "instrument_id": instrument_id,
        "side": side.value, "requested_quantity": _number(requested_quantity),
        "order_ordinal": order_ordinal, "created_at_utc": created_at_utc,
    }
    order = ExecutionOrder(
        order_id, intent_id.key, authority_scope_id, account_id, instrument_id,
        side, requested_quantity, order_ordinal, created_at_utc,
        ContentRef.v2("execution.order", "execution-order", order_value),
    )
    zero = ScaledInteger(0, requested_quantity.scale)
    state = OrderSettlementState(order, 0, None, zero, requested_quantity, (), (), False)
    outbox = _outbox(
        authority_scope_id=authority_scope_id, aggregate_id=intent_id.key, sequence=1,
        event_type="IntentPrepared", payload_ref=order.order_ref, at=created_at_utc,
    )
    return ExecutionPreparation(intent, order, state, outbox)


_LEGAL = {
    None: {OrderStatus.ACCEPTED, OrderStatus.REJECTED},
    OrderStatus.ACCEPTED: {OrderStatus.OPEN, OrderStatus.REJECTED, OrderStatus.UNKNOWN},
    OrderStatus.OPEN: {OrderStatus.PARTIAL, OrderStatus.FILLED, OrderStatus.CANCELLED,
                       OrderStatus.EXPIRED, OrderStatus.UNKNOWN},
    OrderStatus.PARTIAL: {OrderStatus.PARTIAL, OrderStatus.FILLED,
                          OrderStatus.CANCELLED, OrderStatus.EXPIRED,
                          OrderStatus.UNKNOWN},
}


def _apply_fill(account: AccountState, order: ExecutionOrder,
                event: SimulatorEvent, fill: SimulatedFill
                ) -> tuple[AccountState, SettlementEntry]:
    if fill.fill_id in account.processed_fill_ids:
        _fail("DUPLICATE_FILL_ID")
    _validate_fill_evidence(fill)
    computed = _multiply(fill.quantity, fill.price)
    if _rescale_ceil(computed, fill.notional.scale,
                     "FILL_NOTIONAL_MISMATCH") != fill.notional:
        _fail("FILL_NOTIONAL_MISMATCH")
    fee = _nonnegative(fill.fee, "INVALID_FILL_COST")
    tax = _nonnegative(fill.tax, "INVALID_FILL_COST")
    charges = _add(fee, tax)
    if order.side is ExecutionSide.BUY:
        debit = _rescale_exact(_add(fill.notional, charges),
                               account.cash_balance.scale,
                               "CASH_PRECISION_BREACH")
        settled_quantity = _rescale_exact(fill.quantity,
                                          account.position_quantity.scale,
                                          "QUANTITY_PRECISION_BREACH")
        cash = _subtract(account.cash_balance, debit)
        quantity = _add(account.position_quantity, settled_quantity)
        cash_delta = ScaledInteger(-debit.units, debit.scale)
        quantity_delta = settled_quantity
        if cash.units < 0:
            _fail("CASH_OVERDRAFT")
    else:
        credit = _rescale_exact(_subtract(fill.notional, charges),
                                account.cash_balance.scale,
                                "CASH_PRECISION_BREACH")
        settled_quantity = _rescale_exact(fill.quantity,
                                          account.position_quantity.scale,
                                          "QUANTITY_PRECISION_BREACH")
        if credit.units < 0:
            _fail("FILL_COST_EXCEEDS_NOTIONAL")
        cash = _add(account.cash_balance, credit)
        quantity = _subtract(account.position_quantity, settled_quantity)
        cash_delta = credit
        quantity_delta = ScaledInteger(-settled_quantity.units, settled_quantity.scale)
        if quantity.units < 0:
            _fail("POSITION_OVERSELL")
    updated = AccountState(
        account.account_id, account.instrument_id, cash, quantity,
        _add(account.fees_paid, _rescale_exact(
            fee, account.fees_paid.scale, "FEE_PRECISION_BREACH")),
        _add(account.taxes_paid, _rescale_exact(
            tax, account.taxes_paid.scale, "TAX_PRECISION_BREACH")),
        (*account.processed_fill_ids, fill.fill_id),
        account.revision,
    )
    entry = SettlementEntry(
        order.authority_scope_id, account.account_id, account.instrument_id,
        order.order_id.key, event.event_id, order.side, fill.fill_id, fill.quantity,
        fill.notional, fee, tax, cash_delta, quantity_delta, fill.filled_at_utc,
    )
    return updated, entry


def settle_event(order_state: OrderSettlementState, account: AccountState,
                 event: SimulatorEvent) -> SettlementResult:
    """Apply only the new suffix of one cumulative lifecycle event."""
    if type(order_state) is not OrderSettlementState or type(account) is not AccountState:
        _fail("INVALID_SETTLEMENT_STATE")
    if type(event) is not SimulatorEvent:
        _fail("INVALID_LIFECYCLE_EVENT")
    order = order_state.order
    if event.order_id != order.order_id.key:
        _fail("FOREIGN_ORDER_EVENT")
    if account.account_id != order.account_id or account.instrument_id != order.instrument_id:
        _fail("FOREIGN_ACCOUNT")
    known_fill_ids = {fill.fill_id for fill in order_state.cumulative_fills}
    if not known_fill_ids.issubset(set(account.processed_fill_ids)):
        _fail("ACCOUNT_FILL_HISTORY_MISMATCH")

    for receipt in order_state.receipts:
        if receipt.event_id == event.event_id or receipt.sequence == event.sequence:
            if receipt == event:
                return SettlementResult(order_state, account, (), None, True)
            _fail("CONFLICTING_DUPLICATE_EVENT")
    if event.sequence != order_state.last_sequence + 1:
        _fail("OUT_OF_ORDER_EVENT")
    if event.schema_version != "simulator-event:v1":
        _fail("UNSUPPORTED_EVENT_SCHEMA")
    if (order_state.receipts
            and event.event_at_utc < order_state.receipts[-1].event_at_utc):
        _fail("EVENT_TIME_REGRESSION")
    if event.status not in _LEGAL.get(order_state.status, set()):
        _fail("ILLEGAL_TRANSITION")
    if event.fills[:len(order_state.cumulative_fills)] != order_state.cumulative_fills:
        _fail("FILL_PREFIX_CONFLICT")
    if len({fill.fill_id for fill in event.fills}) != len(event.fills):
        _fail("DUPLICATE_FILL_ID")
    for fill in event.fills:
        _validate_fill_evidence(fill)
    if (event.filled_quantity.scale != order.requested_quantity.scale
            or event.remaining_quantity.scale != order.requested_quantity.scale):
        _fail("ORDER_QUANTITY_SCALE_MISMATCH")
    if not _same(_add(event.filled_quantity, event.remaining_quantity),
                 order.requested_quantity):
        _fail("QUANTITY_CONSERVATION_BREACH")
    new_fills = event.fills[len(order_state.cumulative_fills):]
    if event.status is OrderStatus.UNKNOWN and (
            new_fills
            or not _same(event.filled_quantity, order_state.filled_quantity)
            or not _same(event.remaining_quantity, order_state.remaining_quantity)):
        _fail("UNKNOWN_QUANTITY_CHANGE")
    _validate_event_fill_times(
        event,
        previous_fill_count=len(order_state.cumulative_fills),
    )
    _validate_terminal_status(event)
    fill_total = _sum(tuple(fill.quantity for fill in event.fills),
                      minimum_scale=event.filled_quantity.scale)
    if not _same(fill_total, event.filled_quantity):
        _fail("FILL_QUANTITY_MISMATCH")
    if not _same(event.filled_quantity, order_state.filled_quantity) and (
            _subtract(event.filled_quantity, order_state.filled_quantity).units < 0):
        _fail("QUANTITY_REGRESSION")

    updated_account = account
    entries: list[SettlementEntry] = []
    for fill in new_fills:
        if fill.order_id != order.order_id.key:
            _fail("FOREIGN_FILL")
        updated_account, entry = _apply_fill(updated_account, order, event, fill)
        entries.append(entry)
    if bool(new_fills) != (not _same(event.filled_quantity,
                                     order_state.filled_quantity)):
        _fail("FILL_PREFIX_QUANTITY_MISMATCH")
    if new_fills:
        updated_account = replace(updated_account, revision=account.revision + 1)

    updated_state = OrderSettlementState(
        order, event.sequence, event.status, event.filled_quantity,
        event.remaining_quantity, event.fills, (*order_state.receipts, event),
        order_state.entry_frozen or event.status is OrderStatus.UNKNOWN,
    )
    event_type = f"Order{event.status.value.title()}"
    outbox = _outbox(
        authority_scope_id=order.authority_scope_id,
        aggregate_id=order.order_id.key,
        sequence=event.sequence,
        event_type=event_type,
        payload_ref=event.event_ref,
        at=event.event_at_utc,
    )
    return SettlementResult(updated_state, updated_account, tuple(entries), outbox, False)


__all__ = (
    "AccountState", "DispatchEnvelope", "ExecutionError", "ExecutionIntent",
    "ExecutionOrder", "ExecutionPreparation", "ExecutionSide", "OrderSettlementState",
    "OutboxMessage", "OutboxStatus", "SettlementEntry", "SettlementResult",
    "prepare_execution", "settle_event",
)
