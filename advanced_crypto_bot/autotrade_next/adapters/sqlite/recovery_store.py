"""Crash-durable lifecycle recovery snapshots and additive corrections.

The store keeps a content-verified, append-only snapshot history in the same
SQLite file as the writer fence. Encoding happens before, and decoding after,
the short transaction so no external callback runs while the write lock is held.
"""

from __future__ import annotations

from contextlib import closing
from dataclasses import dataclass
from datetime import UTC, datetime
from enum import Enum
import json
from pathlib import Path
import sqlite3

from autotrade_next.domain.content import ContentRecipe, ContentRef
from autotrade_next.domain.execution import (
    AccountState,
    ExecutionOrder,
    ExecutionPreparation,
    ExecutionSide,
    OrderSettlementState,
    OutboxMessage,
    OutboxStatus,
    SettlementEntry,
    prepare_execution,
)
from autotrade_next.domain.exit_protection import (
    DustIncident,
    ExitReason,
    PositionProtectionState,
    PositionProtectionStatus,
    ProtectionState,
)
from autotrade_next.domain.identity import build_identity
from autotrade_next.domain.numeric import ScaledInteger
from autotrade_next.domain.policy import GapBehavior, PolicyState
from autotrade_next.domain.recovery import (
    CorrectionRequest,
    ProjectionHighWater,
    RecoveryCheckpoint,
    RecoveryPlan,
    VenueOrderEvidence,
    plan_recovery,
)
from autotrade_next.domain.simulator import (
    FeeType,
    OrderStatus,
    SimulatedFill,
    SimulatorEvent,
)
from autotrade_next.ports.recovery import CorrectionApprovalVerifier


_EPOCH = datetime(1970, 1, 1, tzinfo=UTC)
_SCHEMA = "recovery-snapshot:v1"


class RecoveryPersistenceError(ValueError):
    def __init__(self, code: str) -> None:
        self.code = self.error_code = code
        self.partial_result = None
        super().__init__(code)


class RecoveryIndeterminateCommit(RuntimeError):
    """COMMIT may have succeeded even though the caller lost its result."""


class RecoveryCommitStatus(str, Enum):
    COMMITTED = "COMMITTED"
    IDEMPOTENT = "IDEMPOTENT"
    COMMITTED_AFTER_INDETERMINATE = "COMMITTED_AFTER_INDETERMINATE"
    AUTHORIZATION_REJECTED = "AUTHORIZATION_REJECTED"
    AUTHORITY_MISSING = "AUTHORITY_MISSING"
    STALE_EPOCH = "STALE_EPOCH"
    UNCLAIMED_EPOCH = "UNCLAIMED_EPOCH"
    FENCE_LOST = "FENCE_LOST"
    LEASE_EXPIRED = "LEASE_EXPIRED"
    CLOCK_ANOMALY = "CLOCK_ANOMALY"
    HEAD_CONFLICT = "HEAD_CONFLICT"
    HIGH_WATER_CONFLICT = "HIGH_WATER_CONFLICT"
    HISTORY_CONFLICT = "HISTORY_CONFLICT"
    IDENTITY_CONFLICT = "IDENTITY_CONFLICT"
    BUSY = "BUSY"
    INDETERMINATE_COMMIT = "INDETERMINATE_COMMIT"


@dataclass(frozen=True, slots=True)
class RecoveryCheckpointCommand:
    operation_id: str
    scope_id: str
    epoch: int
    lease_token: str
    current_time_utc: datetime
    expected_checkpoint_ref: str | None
    checkpoint: RecoveryCheckpoint

    def __post_init__(self) -> None:
        for value, code in (
            (self.operation_id, "INVALID_RECOVERY_OPERATION_ID"),
            (self.scope_id, "INVALID_RECOVERY_SCOPE"),
            (self.lease_token, "INVALID_RECOVERY_LEASE_TOKEN"),
        ):
            _text(value, code)
        if type(self.epoch) is not int or self.epoch < 0:
            _fail("INVALID_RECOVERY_EPOCH")
        if self.expected_checkpoint_ref is not None:
            _text(self.expected_checkpoint_ref, "INVALID_EXPECTED_CHECKPOINT")
        _microseconds(self.current_time_utc, "INVALID_RECOVERY_TIME")
        if (type(self.checkpoint) is not RecoveryCheckpoint
                or self.checkpoint.authority_scope_id != self.scope_id):
            _fail("RECOVERY_SCOPE_MISMATCH")


@dataclass(frozen=True, slots=True)
class RecoveryCommitResult:
    status: RecoveryCommitStatus
    operation_id: str
    checkpoint_ref: str | None = None
    journal_high_water: int | None = None


def _fail(code: str) -> None:
    raise RecoveryPersistenceError(code)


def _text(value: object, code: str) -> str:
    if type(value) is not str or not value.strip():
        _fail(code)
    return value


def _microseconds(value: object, code: str) -> int:
    if type(value) is not datetime or value.tzinfo is not UTC:
        _fail(code)
    delta = value - _EPOCH
    return (delta.days * 86_400 + delta.seconds) * 1_000_000 + delta.microseconds


def _time(value: datetime) -> str:
    _microseconds(value, "INVALID_RECOVERY_TIME")
    return value.isoformat(timespec="microseconds").replace("+00:00", "Z")


def _parse_time(value: object) -> datetime:
    if type(value) is not str or not value.endswith("Z"):
        _fail("RECOVERY_SNAPSHOT_CORRUPT")
    try:
        result = datetime.fromisoformat(value[:-1] + "+00:00")
    except ValueError as error:
        raise RecoveryPersistenceError("RECOVERY_SNAPSHOT_CORRUPT") from error
    if result.tzinfo is not UTC:
        _fail("RECOVERY_SNAPSHOT_CORRUPT")
    return result


def _number(value: ScaledInteger) -> dict[str, int]:
    return {"units": value.units, "scale": value.scale}


def _parse_number(value: object) -> ScaledInteger:
    if type(value) is not dict or set(value) != {"units", "scale"}:
        _fail("RECOVERY_SNAPSHOT_CORRUPT")
    try:
        return ScaledInteger(value["units"], value["scale"])
    except (TypeError, ValueError) as error:
        raise RecoveryPersistenceError("RECOVERY_SNAPSHOT_CORRUPT") from error


def _optional_number(value: ScaledInteger | None) -> dict[str, int] | None:
    return None if value is None else _number(value)


def _parse_optional_number(value: object) -> ScaledInteger | None:
    return None if value is None else _parse_number(value)


def _ref(value: ContentRef) -> dict[str, str]:
    return value.to_canonical_value()


def _parse_ref(value: object) -> ContentRef:
    if type(value) is not dict or set(value) != {"domain", "kind", "recipe", "digest"}:
        _fail("RECOVERY_SNAPSHOT_CORRUPT")
    try:
        return ContentRef(
            value["domain"], value["kind"], ContentRecipe(value["recipe"]),
            value["digest"],
        )
    except (TypeError, ValueError) as error:
        raise RecoveryPersistenceError("RECOVERY_SNAPSHOT_CORRUPT") from error


def _encode_fill(value: SimulatedFill) -> dict[str, object]:
    return {
        "fill_id": value.fill_id,
        "order_id": value.order_id,
        "price": _number(value.price),
        "quantity": _number(value.quantity),
        "fee": _number(value.fee),
        "fee_type": value.fee_type.value,
        "filled_at_utc": _time(value.filled_at_utc),
        "notional": _optional_number(value.notional),
        "tax": _optional_number(value.tax),
    }


def _decode_fill(value: dict[str, object]) -> SimulatedFill:
    return SimulatedFill(
        value["fill_id"], value["order_id"], _parse_number(value["price"]),
        _parse_number(value["quantity"]), _parse_number(value["fee"]),
        FeeType(value["fee_type"]), _parse_time(value["filled_at_utc"]),
        _parse_optional_number(value["notional"]),
        _parse_optional_number(value["tax"]),
    )


def _encode_event(value: SimulatorEvent) -> dict[str, object]:
    return {
        "event_id": value.event_id,
        "order_id": value.order_id,
        "status": value.status.value,
        "filled_quantity": _number(value.filled_quantity),
        "remaining_quantity": _number(value.remaining_quantity),
        "average_price": _number(value.average_price),
        "fills": [_encode_fill(item) for item in value.fills],
        "event_at_utc": _time(value.event_at_utc),
        "sequence": value.sequence,
        "schema_version": value.schema_version,
    }


def _decode_event(value: dict[str, object]) -> SimulatorEvent:
    return SimulatorEvent.create(
        event_id=value["event_id"], order_id=value["order_id"],
        status=OrderStatus(value["status"]),
        filled_quantity=_parse_number(value["filled_quantity"]),
        remaining_quantity=_parse_number(value["remaining_quantity"]),
        average_price=_parse_number(value["average_price"]),
        fills=tuple(_decode_fill(item) for item in value["fills"]),
        event_at_utc=_parse_time(value["event_at_utc"]),
        sequence=value["sequence"], schema_version=value["schema_version"],
    )


def _encode_order(value: ExecutionOrder) -> dict[str, object]:
    return {
        "intent_id": value.intent_id,
        "authority_scope_id": value.authority_scope_id,
        "account_id": value.account_id,
        "instrument_id": value.instrument_id,
        "side": value.side.value,
        "requested_quantity": _number(value.requested_quantity),
        "order_ordinal": value.order_ordinal,
        "created_at_utc": _time(value.created_at_utc),
    }


def _decode_order(value: dict[str, object]) -> ExecutionOrder:
    order_id = build_identity("client_order", {
        "authority_scope_id": value["authority_scope_id"],
        "intent_id": value["intent_id"],
        "order_ordinal": value["order_ordinal"],
    })
    quantity = _parse_number(value["requested_quantity"])
    side = ExecutionSide(value["side"])
    created = _parse_time(value["created_at_utc"])
    binding = {
        "schema_version": "execution-order:v1", "order_id": order_id.key,
        "intent_id": value["intent_id"],
        "authority_scope_id": value["authority_scope_id"],
        "account_id": value["account_id"], "instrument_id": value["instrument_id"],
        "side": side.value, "requested_quantity": _number(quantity),
        "order_ordinal": value["order_ordinal"], "created_at_utc": created,
    }
    return ExecutionOrder(
        order_id, value["intent_id"], value["authority_scope_id"],
        value["account_id"], value["instrument_id"], side, quantity,
        value["order_ordinal"], created,
        ContentRef.v2("execution.order", "execution-order", binding),
    )


def _encode_order_state(value: OrderSettlementState) -> dict[str, object]:
    return {
        "order": _encode_order(value.order),
        "last_sequence": value.last_sequence,
        "status": None if value.status is None else value.status.value,
        "filled_quantity": _number(value.filled_quantity),
        "remaining_quantity": _number(value.remaining_quantity),
        "cumulative_fills": [_encode_fill(item) for item in value.cumulative_fills],
        "receipts": [_encode_event(item) for item in value.receipts],
        "entry_frozen": value.entry_frozen,
    }


def _decode_order_state(value: dict[str, object]) -> OrderSettlementState:
    return OrderSettlementState(
        _decode_order(value["order"]), value["last_sequence"],
        None if value["status"] is None else OrderStatus(value["status"]),
        _parse_number(value["filled_quantity"]),
        _parse_number(value["remaining_quantity"]),
        tuple(_decode_fill(item) for item in value["cumulative_fills"]),
        tuple(_decode_event(item) for item in value["receipts"]),
        value["entry_frozen"],
    )


def _encode_preparation(value: ExecutionPreparation) -> dict[str, object]:
    return {
        "decision_id": value.intent.decision_id,
        "authority_scope_id": value.intent.authority_scope_id,
        "account_id": value.intent.account_id,
        "instrument_id": value.intent.instrument_id,
        "side": value.intent.side.value,
        "requested_quantity": _number(value.intent.requested_quantity),
        "order_ordinal": value.order.order_ordinal,
        "created_at_utc": _time(value.intent.created_at_utc),
    }


def _decode_preparation(value: dict[str, object]) -> ExecutionPreparation:
    return prepare_execution(
        decision_id=value["decision_id"],
        authority_scope_id=value["authority_scope_id"],
        account_id=value["account_id"], instrument_id=value["instrument_id"],
        side=ExecutionSide(value["side"]),
        requested_quantity=_parse_number(value["requested_quantity"]),
        order_ordinal=value["order_ordinal"],
        created_at_utc=_parse_time(value["created_at_utc"]),
    )


def _encode_outbox(value: OutboxMessage) -> dict[str, object]:
    return {
        "authority_scope_id": value.authority_scope_id,
        "aggregate_id": value.aggregate_id,
        "aggregate_sequence": value.aggregate_sequence,
        "event_type": value.event_type,
        "payload_ref": _ref(value.payload_ref),
        "status": value.status.value,
        "created_at_utc": _time(value.created_at_utc),
    }


def _decode_outbox(value: dict[str, object]) -> OutboxMessage:
    identity = build_identity("event", {
        "authority_scope_id": value["authority_scope_id"],
        "aggregate_id": value["aggregate_id"],
        "aggregate_seq": value["aggregate_sequence"],
        "event_type": value["event_type"], "schema_version": 1,
    })
    return OutboxMessage(
        identity, value["authority_scope_id"], value["aggregate_id"],
        value["aggregate_sequence"], value["event_type"],
        _parse_ref(value["payload_ref"]), OutboxStatus(value["status"]),
        _parse_time(value["created_at_utc"]),
    )


def _encode_protection(value: ProtectionState) -> dict[str, object]:
    return {
        "stop_loss_price": _optional_number(value.stop_loss_price),
        "take_profit_price": _optional_number(value.take_profit_price),
        "trailing_high_water": _optional_number(value.trailing_high_water),
        "expiration_at_utc": (
            None if value.expiration_at_utc is None else _time(value.expiration_at_utc)
        ),
        "trailing_distance": _optional_number(value.trailing_distance),
        "invalidation_ref": value.invalidation_ref,
    }


def _decode_protection(value: dict[str, object]) -> ProtectionState:
    return ProtectionState(
        _parse_optional_number(value["stop_loss_price"]),
        _parse_optional_number(value["take_profit_price"]),
        _parse_optional_number(value["trailing_high_water"]),
        None if value["expiration_at_utc"] is None
        else _parse_time(value["expiration_at_utc"]),
        _parse_optional_number(value["trailing_distance"]),
        value["invalidation_ref"],
    )


def _encode_dust(value: DustIncident | None) -> dict[str, object] | None:
    if value is None:
        return None
    return {
        "position_id": value.position_id,
        "remaining_quantity": _number(value.remaining_quantity),
        "minimum_venue_quantity": _number(value.minimum_venue_quantity),
        "valuation": _number(value.valuation),
        "valuation_evidence_ref": value.valuation_evidence_ref,
        "triggering_fill_id": value.triggering_fill_id,
        "recorded_at_utc": _time(value.recorded_at_utc),
    }


def _decode_dust(value: dict[str, object] | None) -> DustIncident | None:
    if value is None:
        return None
    return DustIncident.create(
        position_id=value["position_id"],
        remaining_quantity=_parse_number(value["remaining_quantity"]),
        minimum_venue_quantity=_parse_number(value["minimum_venue_quantity"]),
        valuation=_parse_number(value["valuation"]),
        valuation_evidence_ref=value["valuation_evidence_ref"],
        triggering_fill_id=value["triggering_fill_id"],
        recorded_at_utc=_parse_time(value["recorded_at_utc"]),
    )


def _encode_position(value: PositionProtectionState) -> dict[str, object]:
    return {
        "position_id": value.position_id,
        "authority_scope_id": value.authority_scope_id,
        "account_id": value.account_id,
        "instrument_id": value.instrument_id,
        "entry_price": _number(value.entry_price),
        "entered_at_utc": _time(value.entered_at_utc),
        "last_evaluated_at_utc": _time(value.last_evaluated_at_utc),
        "remaining_quantity": _number(value.remaining_quantity),
        "sequence": value.sequence, "status": value.status.value,
        "protection": _encode_protection(value.protection),
        "policy_state_ref": value.policy_state_ref,
        "partial_exit": value.partial_exit,
        "pending_exit_key": value.pending_exit_key,
        "pending_exit_sequence": value.pending_exit_sequence,
        "pending_order_id": value.pending_order_id,
        "pending_reason": None if value.pending_reason is None else value.pending_reason.value,
        "pending_target_quantity": _optional_number(value.pending_target_quantity),
        "processed_exit_fill_ids": list(value.processed_exit_fill_ids),
        "dust_incident": _encode_dust(value.dust_incident),
    }


def _decode_position(value: dict[str, object]) -> PositionProtectionState:
    return PositionProtectionState(
        value["position_id"], value["authority_scope_id"], value["account_id"],
        value["instrument_id"], _parse_number(value["entry_price"]),
        _parse_time(value["entered_at_utc"]),
        _parse_time(value["last_evaluated_at_utc"]),
        _parse_number(value["remaining_quantity"]), value["sequence"],
        PositionProtectionStatus(value["status"]),
        _decode_protection(value["protection"]), value["policy_state_ref"],
        value["partial_exit"], value["pending_exit_key"],
        value["pending_exit_sequence"], value["pending_order_id"],
        None if value["pending_reason"] is None else ExitReason(value["pending_reason"]),
        _parse_optional_number(value["pending_target_quantity"]),
        tuple(value["processed_exit_fill_ids"]), _decode_dust(value["dust_incident"]),
    )


def _encode_policy(value: PolicyState) -> dict[str, object]:
    result = dict(value.to_canonical_value())
    result["required_margin"] = _number(value.required_margin)
    return result


def _decode_policy(value: dict[str, object]) -> PolicyState:
    fields = dict(value)
    if fields.pop("schema_version", None) != "policy-state:v1":
        _fail("RECOVERY_SNAPSHOT_CORRUPT")
    fields["required_margin"] = _parse_number(fields["required_margin"])
    fields["gap_behavior"] = GapBehavior(fields["gap_behavior"])
    return PolicyState(**fields)


def _encode_settlement(value: SettlementEntry) -> dict[str, object]:
    return {
        "authority_scope_id": value.authority_scope_id,
        "account_id": value.account_id, "instrument_id": value.instrument_id,
        "order_id": value.order_id, "event_id": value.event_id,
        "side": value.side.value, "fill_id": value.fill_id,
        "quantity": _number(value.quantity), "notional": _number(value.notional),
        "fee": _number(value.fee), "tax": _number(value.tax),
        "cash_delta": _number(value.cash_delta),
        "quantity_delta": _number(value.quantity_delta),
        "recorded_at_utc": _time(value.recorded_at_utc),
    }


def _decode_settlement(value: dict[str, object]) -> SettlementEntry:
    return SettlementEntry(
        value["authority_scope_id"], value["account_id"], value["instrument_id"],
        value["order_id"], value["event_id"], ExecutionSide(value["side"]),
        value["fill_id"], _parse_number(value["quantity"]),
        _parse_number(value["notional"]), _parse_number(value["fee"]),
        _parse_number(value["tax"]), _parse_number(value["cash_delta"]),
        _parse_number(value["quantity_delta"]), _parse_time(value["recorded_at_utc"]),
    )


def encode_recovery_checkpoint(checkpoint: RecoveryCheckpoint) -> bytes:
    """Encode a checkpoint without pickle or runtime-specific object metadata."""
    if type(checkpoint) is not RecoveryCheckpoint:
        _fail("INVALID_RECOVERY_CHECKPOINT")
    account = checkpoint.account_snapshot
    value = {
        "schema_version": _SCHEMA,
        "checkpoint_ref": _ref(checkpoint.checkpoint_ref),
        "authority_scope_id": checkpoint.authority_scope_id,
        "journal_high_water": checkpoint.journal_high_water,
        "account_snapshot": {
            "account_id": account.account_id, "instrument_id": account.instrument_id,
            "cash_balance": _number(account.cash_balance),
            "position_quantity": _number(account.position_quantity),
            "fees_paid": _number(account.fees_paid), "taxes_paid": _number(account.taxes_paid),
            "processed_fill_ids": list(account.processed_fill_ids), "revision": account.revision,
        },
        "settlement_entries": [_encode_settlement(item) for item in checkpoint.settlement_entries],
        "order_states": [_encode_order_state(item) for item in checkpoint.order_states],
        "positions": [_encode_position(item) for item in checkpoint.positions],
        "policy_states": [_encode_policy(item) for item in checkpoint.policy_states],
        "preparations": [_encode_preparation(item) for item in checkpoint.preparations],
        "pending_command_refs": list(checkpoint.pending_command_refs),
        "inbox_ids": list(checkpoint.inbox_ids),
        "applied_correction_refs": list(checkpoint.applied_correction_refs),
        "outbox": [_encode_outbox(item) for item in checkpoint.outbox],
        "projection_high_waters": [
            {"projection_name": item.projection_name, "sequence": item.sequence}
            for item in checkpoint.projection_high_waters
        ],
        "entry_frozen": checkpoint.entry_frozen,
        "unknown_deadline_utc": (
            None if checkpoint.unknown_deadline_utc is None
            else _time(checkpoint.unknown_deadline_utc)
        ),
        "captured_at_utc": _time(checkpoint.captured_at_utc),
    }
    return json.dumps(value, sort_keys=True, separators=(",", ":"),
                      ensure_ascii=False).encode("utf-8")


def decode_recovery_checkpoint(payload: bytes) -> RecoveryCheckpoint:
    """Decode and revalidate every domain invariant and content reference."""
    if type(payload) is not bytes:
        _fail("RECOVERY_SNAPSHOT_CORRUPT")
    try:
        value = json.loads(payload.decode("utf-8"))
        if type(value) is not dict or value.get("schema_version") != _SCHEMA:
            _fail("RECOVERY_SNAPSHOT_CORRUPT")
        account = value["account_snapshot"]
        checkpoint = RecoveryCheckpoint.create(
            authority_scope_id=value["authority_scope_id"],
            journal_high_water=value["journal_high_water"],
            account_snapshot=AccountState(
                account["account_id"], account["instrument_id"],
                _parse_number(account["cash_balance"]),
                _parse_number(account["position_quantity"]),
                _parse_number(account["fees_paid"]), _parse_number(account["taxes_paid"]),
                tuple(account["processed_fill_ids"]), account["revision"],
            ),
            settlement_entries=tuple(
                _decode_settlement(item) for item in value["settlement_entries"]
            ),
            order_states=tuple(_decode_order_state(item) for item in value["order_states"]),
            positions=tuple(_decode_position(item) for item in value["positions"]),
            policy_states=tuple(_decode_policy(item) for item in value["policy_states"]),
            preparations=tuple(
                _decode_preparation(item) for item in value["preparations"]
            ),
            pending_command_refs=tuple(value["pending_command_refs"]),
            inbox_ids=tuple(value["inbox_ids"]),
            applied_correction_refs=tuple(value["applied_correction_refs"]),
            outbox=tuple(_decode_outbox(item) for item in value["outbox"]),
            projection_high_waters=tuple(
                ProjectionHighWater(item["projection_name"], item["sequence"])
                for item in value["projection_high_waters"]
            ),
            entry_frozen=value["entry_frozen"],
            unknown_deadline_utc=(
                None if value["unknown_deadline_utc"] is None
                else _parse_time(value["unknown_deadline_utc"])
            ),
            captured_at_utc=_parse_time(value["captured_at_utc"]),
        )
        stored_ref = _parse_ref(value["checkpoint_ref"])
        if checkpoint.checkpoint_ref != stored_ref:
            _fail("RECOVERY_SNAPSHOT_CORRUPT")
        return checkpoint
    except RecoveryPersistenceError:
        raise
    except (KeyError, TypeError, ValueError, UnicodeError, json.JSONDecodeError) as error:
        raise RecoveryPersistenceError("RECOVERY_SNAPSHOT_CORRUPT") from error


def _is_append_only_successor(
    previous: RecoveryCheckpoint,
    current: RecoveryCheckpoint,
) -> bool:
    if (current.authority_scope_id != previous.authority_scope_id
            or current.journal_high_water != previous.journal_high_water + 1
            or current.captured_at_utc < previous.captured_at_utc
            or current.account_snapshot.account_id
            != previous.account_snapshot.account_id
            or current.account_snapshot.instrument_id
            != previous.account_snapshot.instrument_id
            or current.account_snapshot.processed_fill_ids[
                :len(previous.account_snapshot.processed_fill_ids)
            ] != previous.account_snapshot.processed_fill_ids
            or current.settlement_entries[:len(previous.settlement_entries)]
            != previous.settlement_entries
            or current.inbox_ids[:len(previous.inbox_ids)] != previous.inbox_ids
            or current.applied_correction_refs[
                :len(previous.applied_correction_refs)
            ] != previous.applied_correction_refs):
        return False

    new_entries = current.settlement_entries[len(previous.settlement_entries):]
    expected_cash = previous.account_snapshot.cash_balance
    expected_quantity = previous.account_snapshot.position_quantity
    expected_fees = previous.account_snapshot.fees_paid
    expected_taxes = previous.account_snapshot.taxes_paid
    for entry in new_entries:
        expected_cash = expected_cash.add(entry.cash_delta)
        expected_quantity = expected_quantity.add(entry.quantity_delta)
        expected_fees = expected_fees.add(entry.fee)
        expected_taxes = expected_taxes.add(entry.tax)
    account = current.account_snapshot
    expected_revision = previous.account_snapshot.revision + len({
        item.event_id for item in new_entries
    })
    if (account.cash_balance != expected_cash
            or account.position_quantity != expected_quantity
            or account.fees_paid != expected_fees
            or account.taxes_paid != expected_taxes
            or account.revision != expected_revision):
        return False

    current_orders = {
        item.order.order_id.key: item for item in current.order_states
    }
    for old in previous.order_states:
        new = current_orders.get(old.order.order_id.key)
        if (new is None or new.order != old.order
                or new.receipts[:len(old.receipts)] != old.receipts):
            return False

    current_positions = {item.position_id: item for item in current.positions}
    for old in previous.positions:
        new = current_positions.get(old.position_id)
        if (new is None or new.sequence < old.sequence
                or new.processed_exit_fill_ids[:len(old.processed_exit_fill_ids)]
                != old.processed_exit_fill_ids):
            return False

    old_policies = {
        ContentRef.v1("policy-state", item.to_canonical_value()).key
        for item in previous.policy_states
    }
    new_policies = {
        ContentRef.v1("policy-state", item.to_canonical_value()).key
        for item in current.policy_states
    }
    if not old_policies.issubset(new_policies):
        return False
    if not set(previous.preparations).issubset(set(current.preparations)):
        return False
    new_projections = {
        item.projection_name: item.sequence for item in current.projection_high_waters
    }
    return all(
        new_projections.get(item.projection_name, -1) >= item.sequence
        for item in previous.projection_high_waters
    )


class SQLiteRecoveryStore:
    """Persist and recover the exact latest lifecycle checkpoint under a fence."""

    def __init__(self, path: str | Path, *, busy_timeout_seconds: float = 0.0) -> None:
        if not isinstance(path, (str, Path)) or not str(path) or str(path) == ":memory:":
            _fail("SHARED_DURABLE_PATH_REQUIRED")
        if (type(busy_timeout_seconds) not in (int, float)
                or busy_timeout_seconds < 0):
            _fail("INVALID_BUSY_TIMEOUT")
        self.path = Path(path)
        self._timeout = float(busy_timeout_seconds)

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(
            self.path, timeout=self._timeout, isolation_level=None,
        )
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        return connection

    def initialize(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with closing(self._connect()) as connection:
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS writer_authority (
                    scope_id TEXT PRIMARY KEY,
                    active_epoch INTEGER NOT NULL CHECK (active_epoch >= 1),
                    lease_token TEXT NOT NULL CHECK (length(lease_token) > 0),
                    granted_at_us INTEGER NOT NULL,
                    expires_at_us INTEGER NOT NULL,
                    CHECK (expires_at_us > granted_at_us)
                );

                CREATE TABLE IF NOT EXISTS recovery_snapshots (
                    scope_id TEXT NOT NULL,
                    journal_high_water INTEGER NOT NULL CHECK (journal_high_water >= 0),
                    checkpoint_ref TEXT NOT NULL UNIQUE,
                    payload BLOB NOT NULL,
                    operation_id TEXT NOT NULL UNIQUE,
                    previous_checkpoint_ref TEXT,
                    committed_at_us INTEGER NOT NULL,
                    PRIMARY KEY (scope_id, journal_high_water)
                );

                CREATE TABLE IF NOT EXISTS recovery_heads (
                    scope_id TEXT PRIMARY KEY,
                    journal_high_water INTEGER NOT NULL,
                    checkpoint_ref TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS recovery_operations (
                    operation_id TEXT PRIMARY KEY,
                    scope_id TEXT NOT NULL,
                    epoch INTEGER NOT NULL,
                    lease_token TEXT NOT NULL,
                    current_time_us INTEGER NOT NULL,
                    expected_checkpoint_ref TEXT,
                    checkpoint_ref TEXT NOT NULL,
                    journal_high_water INTEGER NOT NULL,
                    payload BLOB NOT NULL,
                    correction_ref TEXT
                );

                CREATE TABLE IF NOT EXISTS recovery_corrections (
                    idempotency_ref TEXT PRIMARY KEY,
                    scope_id TEXT NOT NULL,
                    kind TEXT NOT NULL,
                    target_id TEXT NOT NULL,
                    evidence_ref TEXT NOT NULL,
                    approval_ref TEXT NOT NULL,
                    expected_journal_high_water INTEGER NOT NULL,
                    resulting_checkpoint_ref TEXT NOT NULL,
                    committed_at_us INTEGER NOT NULL
                );
                """
            )

    def _before_commit(self, operation_id: str) -> None:
        """Fault-injection seam used by crash-boundary contracts."""

    def _commit(self, connection: sqlite3.Connection) -> None:
        connection.execute("COMMIT")

    @staticmethod
    def _rollback(connection: sqlite3.Connection) -> None:
        if connection.in_transaction:
            connection.execute("ROLLBACK")

    @staticmethod
    def _busy(error: sqlite3.OperationalError) -> bool:
        code = getattr(error, "sqlite_errorcode", None)
        if isinstance(code, int):
            return (code & 0xFF) in (sqlite3.SQLITE_BUSY, sqlite3.SQLITE_LOCKED)
        return "locked" in str(error).lower() or "busy" in str(error).lower()

    @staticmethod
    def _operation_matches(
        row: sqlite3.Row,
        command: RecoveryCheckpointCommand,
        payload: bytes,
        correction_ref: str | None,
    ) -> bool:
        return (
            row["scope_id"] == command.scope_id
            and row["epoch"] == command.epoch
            and row["lease_token"] == command.lease_token
            and row["current_time_us"] == _microseconds(
                command.current_time_utc, "INVALID_RECOVERY_TIME"
            )
            and row["expected_checkpoint_ref"] == command.expected_checkpoint_ref
            and row["checkpoint_ref"] == command.checkpoint.checkpoint_ref.key
            and row["journal_high_water"] == command.checkpoint.journal_high_water
            and bytes(row["payload"]) == payload
            and row["correction_ref"] == correction_ref
        )

    def commit_checkpoint(
        self, command: RecoveryCheckpointCommand,
    ) -> RecoveryCommitResult:
        return self._write(command, None)

    def commit_correction(
        self,
        command: RecoveryCheckpointCommand,
        request: CorrectionRequest,
        *,
        venue_evidence: tuple[VenueOrderEvidence, ...],
        approval_verifier: CorrectionApprovalVerifier,
    ) -> RecoveryCommitResult:
        if type(command) is not RecoveryCheckpointCommand:
            raise TypeError("INVALID_RECOVERY_CHECKPOINT_COMMAND")
        if type(request) is not CorrectionRequest:
            raise TypeError("INVALID_CORRECTION_REQUEST")
        if not callable(getattr(approval_verifier, "verify_correction", None)):
            raise TypeError("INVALID_APPROVAL_VERIFIER")
        payload = encode_recovery_checkpoint(command.checkpoint)
        existing = self._existing_operation(
            command, payload, request.idempotency_ref,
        )
        if existing is not None:
            return existing
        current = self.load_latest(command.scope_id)
        if current is None or request.expected_journal_high_water != current.journal_high_water:
            return RecoveryCommitResult(
                RecoveryCommitStatus.HIGH_WATER_CONFLICT, command.operation_id,
            )
        if command.checkpoint.applied_correction_refs != (
            *current.applied_correction_refs,
            request.idempotency_ref,
        ):
            return RecoveryCommitResult(
                RecoveryCommitStatus.HISTORY_CONFLICT, command.operation_id,
            )
        plan_recovery(
            current, venue_evidence=venue_evidence, corrections=(request,),
        )
        # Approval resolution deliberately occurs before BEGIN IMMEDIATE: a verifier
        # may perform I/O, while the transaction below must remain local and short.
        if approval_verifier.verify_correction(request) is not True:
            return RecoveryCommitResult(
                RecoveryCommitStatus.AUTHORIZATION_REJECTED, command.operation_id,
            )
        return self._write(command, request)

    def _existing_operation(
        self,
        command: RecoveryCheckpointCommand,
        payload: bytes,
        correction_ref: str | None,
    ) -> RecoveryCommitResult | None:
        with closing(self._connect()) as connection:
            row = connection.execute(
                "SELECT * FROM recovery_operations WHERE operation_id = ?",
                (command.operation_id,),
            ).fetchone()
        if row is None:
            return None
        status = (
            RecoveryCommitStatus.IDEMPOTENT
            if self._operation_matches(row, command, payload, correction_ref)
            else RecoveryCommitStatus.IDENTITY_CONFLICT
        )
        return RecoveryCommitResult(
            status, command.operation_id, row["checkpoint_ref"],
            row["journal_high_water"],
        )

    def _write(
        self,
        command: RecoveryCheckpointCommand,
        correction: CorrectionRequest | None,
    ) -> RecoveryCommitResult:
        if type(command) is not RecoveryCheckpointCommand:
            raise TypeError("INVALID_RECOVERY_CHECKPOINT_COMMAND")
        payload = encode_recovery_checkpoint(command.checkpoint)
        correction_ref = None if correction is None else correction.idempotency_ref
        connection = self._connect()
        committed_maybe = False
        try:
            connection.execute("BEGIN IMMEDIATE")
            prior = connection.execute(
                "SELECT * FROM recovery_operations WHERE operation_id = ?",
                (command.operation_id,),
            ).fetchone()
            if prior is not None:
                status = (
                    RecoveryCommitStatus.IDEMPOTENT
                    if self._operation_matches(prior, command, payload, correction_ref)
                    else RecoveryCommitStatus.IDENTITY_CONFLICT
                )
                self._rollback(connection)
                return RecoveryCommitResult(
                    status, command.operation_id, prior["checkpoint_ref"],
                    prior["journal_high_water"],
                )

            authority = connection.execute(
                "SELECT * FROM writer_authority WHERE scope_id = ?",
                (command.scope_id,),
            ).fetchone()
            if authority is None:
                self._rollback(connection)
                return RecoveryCommitResult(
                    RecoveryCommitStatus.AUTHORITY_MISSING, command.operation_id,
                )
            if command.epoch != authority["active_epoch"]:
                status = (
                    RecoveryCommitStatus.STALE_EPOCH
                    if command.epoch < authority["active_epoch"]
                    else RecoveryCommitStatus.UNCLAIMED_EPOCH
                )
                self._rollback(connection)
                return RecoveryCommitResult(status, command.operation_id)
            if command.lease_token != authority["lease_token"]:
                self._rollback(connection)
                return RecoveryCommitResult(
                    RecoveryCommitStatus.FENCE_LOST, command.operation_id,
                )
            now_us = _microseconds(command.current_time_utc, "INVALID_RECOVERY_TIME")
            if now_us < authority["granted_at_us"]:
                self._rollback(connection)
                return RecoveryCommitResult(
                    RecoveryCommitStatus.CLOCK_ANOMALY, command.operation_id,
                )
            if now_us >= authority["expires_at_us"]:
                self._rollback(connection)
                return RecoveryCommitResult(
                    RecoveryCommitStatus.LEASE_EXPIRED, command.operation_id,
                )

            head = connection.execute(
                "SELECT * FROM recovery_heads WHERE scope_id = ?",
                (command.scope_id,),
            ).fetchone()
            if head is None:
                if (command.expected_checkpoint_ref is not None
                        or (correction is None
                            and command.checkpoint.applied_correction_refs)):
                    self._rollback(connection)
                    return RecoveryCommitResult(
                        RecoveryCommitStatus.HEAD_CONFLICT, command.operation_id,
                    )
            else:
                if command.expected_checkpoint_ref != head["checkpoint_ref"]:
                    self._rollback(connection)
                    return RecoveryCommitResult(
                        RecoveryCommitStatus.HEAD_CONFLICT, command.operation_id,
                        head["checkpoint_ref"], head["journal_high_water"],
                    )
                if command.checkpoint.journal_high_water != head["journal_high_water"] + 1:
                    self._rollback(connection)
                    return RecoveryCommitResult(
                        RecoveryCommitStatus.HIGH_WATER_CONFLICT, command.operation_id,
                        head["checkpoint_ref"], head["journal_high_water"],
                    )
                previous_row = connection.execute(
                    "SELECT payload FROM recovery_snapshots "
                    "WHERE scope_id = ? AND checkpoint_ref = ?",
                    (command.scope_id, head["checkpoint_ref"]),
                ).fetchone()
                if previous_row is None:
                    self._rollback(connection)
                    return RecoveryCommitResult(
                        RecoveryCommitStatus.HISTORY_CONFLICT,
                        command.operation_id,
                    )
                previous = decode_recovery_checkpoint(bytes(previous_row["payload"]))
                expected_corrections = (
                    previous.applied_correction_refs
                    if correction is None
                    else (
                        *previous.applied_correction_refs,
                        correction.idempotency_ref,
                    )
                )
                if (not _is_append_only_successor(previous, command.checkpoint)
                        or command.checkpoint.applied_correction_refs
                        != expected_corrections):
                    self._rollback(connection)
                    return RecoveryCommitResult(
                        RecoveryCommitStatus.HISTORY_CONFLICT,
                        command.operation_id, head["checkpoint_ref"],
                        head["journal_high_water"],
                    )

            connection.execute(
                "INSERT INTO recovery_snapshots "
                "(scope_id, journal_high_water, checkpoint_ref, payload, operation_id, "
                "previous_checkpoint_ref, committed_at_us) VALUES (?, ?, ?, ?, ?, ?, ?)",
                (command.scope_id, command.checkpoint.journal_high_water,
                 command.checkpoint.checkpoint_ref.key, payload, command.operation_id,
                 command.expected_checkpoint_ref, now_us),
            )
            if correction is not None:
                connection.execute(
                    "INSERT INTO recovery_corrections "
                    "(idempotency_ref, scope_id, kind, target_id, evidence_ref, "
                    "approval_ref, expected_journal_high_water, resulting_checkpoint_ref, "
                    "committed_at_us) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    (correction.idempotency_ref, command.scope_id,
                     correction.kind.value, correction.target_id,
                     correction.evidence_ref, correction.approval_ref,
                     correction.expected_journal_high_water,
                     command.checkpoint.checkpoint_ref.key, now_us),
                )
            connection.execute(
                "INSERT INTO recovery_operations "
                "(operation_id, scope_id, epoch, lease_token, current_time_us, "
                "expected_checkpoint_ref, checkpoint_ref, journal_high_water, payload, "
                "correction_ref) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (command.operation_id, command.scope_id, command.epoch,
                 command.lease_token, now_us, command.expected_checkpoint_ref,
                 command.checkpoint.checkpoint_ref.key,
                 command.checkpoint.journal_high_water, payload, correction_ref),
            )
            connection.execute(
                "INSERT INTO recovery_heads (scope_id, journal_high_water, checkpoint_ref) "
                "VALUES (?, ?, ?) ON CONFLICT(scope_id) DO UPDATE SET "
                "journal_high_water = excluded.journal_high_water, "
                "checkpoint_ref = excluded.checkpoint_ref",
                (command.scope_id, command.checkpoint.journal_high_water,
                 command.checkpoint.checkpoint_ref.key),
            )
            self._before_commit(command.operation_id)
            committed_maybe = True
            self._commit(connection)
            return RecoveryCommitResult(
                RecoveryCommitStatus.COMMITTED, command.operation_id,
                command.checkpoint.checkpoint_ref.key,
                command.checkpoint.journal_high_water,
            )
        except RecoveryIndeterminateCommit:
            self._rollback(connection)
            return self._reconcile(command, payload, correction_ref)
        except sqlite3.IntegrityError:
            self._rollback(connection)
            return RecoveryCommitResult(
                RecoveryCommitStatus.IDENTITY_CONFLICT, command.operation_id,
            )
        except sqlite3.OperationalError as error:
            self._rollback(connection)
            if self._busy(error):
                return RecoveryCommitResult(
                    RecoveryCommitStatus.BUSY, command.operation_id,
                )
            if committed_maybe:
                return self._reconcile(command, payload, correction_ref)
            raise
        except Exception:
            self._rollback(connection)
            raise
        finally:
            connection.close()

    def _reconcile(
        self,
        command: RecoveryCheckpointCommand,
        payload: bytes,
        correction_ref: str | None,
    ) -> RecoveryCommitResult:
        with closing(self._connect()) as connection:
            row = connection.execute(
                "SELECT * FROM recovery_operations WHERE operation_id = ?",
                (command.operation_id,),
            ).fetchone()
        if row is None:
            return RecoveryCommitResult(
                RecoveryCommitStatus.INDETERMINATE_COMMIT, command.operation_id,
            )
        if not self._operation_matches(row, command, payload, correction_ref):
            return RecoveryCommitResult(
                RecoveryCommitStatus.IDENTITY_CONFLICT, command.operation_id,
            )
        return RecoveryCommitResult(
            RecoveryCommitStatus.COMMITTED_AFTER_INDETERMINATE,
            command.operation_id, row["checkpoint_ref"], row["journal_high_water"],
        )

    def load_latest(self, scope_id: str) -> RecoveryCheckpoint | None:
        _text(scope_id, "INVALID_RECOVERY_SCOPE")
        with closing(self._connect()) as connection:
            row = connection.execute(
                "SELECT s.payload, s.checkpoint_ref, s.journal_high_water "
                "FROM recovery_heads h JOIN recovery_snapshots s "
                "ON s.scope_id = h.scope_id "
                "AND s.journal_high_water = h.journal_high_water "
                "AND s.checkpoint_ref = h.checkpoint_ref WHERE h.scope_id = ?",
                (scope_id,),
            ).fetchone()
        if row is None:
            return None
        checkpoint = decode_recovery_checkpoint(bytes(row["payload"]))
        if (checkpoint.authority_scope_id != scope_id
                or checkpoint.checkpoint_ref.key != row["checkpoint_ref"]
                or checkpoint.journal_high_water != row["journal_high_water"]):
            _fail("RECOVERY_SNAPSHOT_CORRUPT")
        return checkpoint

    def load_recovery_plan(
        self,
        scope_id: str,
        *,
        venue_evidence: tuple[VenueOrderEvidence, ...] = (),
        corrections: tuple[CorrectionRequest, ...] = (),
    ) -> tuple[RecoveryCheckpoint, RecoveryPlan]:
        checkpoint = self.load_latest(scope_id)
        if checkpoint is None:
            _fail("RECOVERY_CHECKPOINT_NOT_FOUND")
        return checkpoint, plan_recovery(
            checkpoint, venue_evidence=venue_evidence, corrections=corrections,
        )


__all__ = (
    "RecoveryCheckpointCommand",
    "RecoveryCommitResult",
    "RecoveryCommitStatus",
    "RecoveryIndeterminateCommit",
    "RecoveryPersistenceError",
    "SQLiteRecoveryStore",
    "decode_recovery_checkpoint",
    "encode_recovery_checkpoint",
)
