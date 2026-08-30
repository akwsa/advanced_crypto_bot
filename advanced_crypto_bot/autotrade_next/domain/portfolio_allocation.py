"""Frozen portfolio allocation and exact multi-dimensional reservations."""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import UTC, datetime
from enum import Enum

from .content import ContentRef
from .errors import DecisionError
from .numeric import ScaledInteger


MAX_RESERVATION_SCALE = 18


def _text(value: object, code: str) -> None:
    if type(value) is not str or not value.strip():
        raise DecisionError(code)


def _amount(value: object, code: str) -> ScaledInteger:
    if type(value) is not ScaledInteger:
        raise DecisionError(code)
    if value.scale > MAX_RESERVATION_SCALE:
        raise DecisionError("RESERVATION_SCALE_EXCEEDED")
    if value.units < 0:
        raise DecisionError("NEGATIVE_RESERVATION_AMOUNT")
    return value


def _aligned(values: tuple[ScaledInteger, ...]) -> tuple[int, tuple[int, ...]]:
    target = max(value.scale for value in values)
    if target > MAX_RESERVATION_SCALE:
        raise DecisionError("RESERVATION_SCALE_EXCEEDED")
    return target, tuple(
        value.units * (10 ** (target - value.scale)) for value in values
    )


def _add(left: ScaledInteger, right: ScaledInteger) -> ScaledInteger:
    target, units = _aligned((left, right))
    return ScaledInteger(units[0] + units[1], target)


def _subtract(left: ScaledInteger, right: ScaledInteger) -> ScaledInteger:
    target, units = _aligned((left, right))
    if units[1] > units[0]:
        raise DecisionError("RESERVATION_OVERCONSUMED")
    return ScaledInteger(units[0] - units[1], target)


def _amount_value(value: ScaledInteger) -> dict[str, int]:
    return {"units": value.units, "scale": value.scale}


@dataclass(frozen=True, slots=True)
class ReservationBucket:
    initial: ScaledInteger
    consumed: ScaledInteger
    active_remainder: ScaledInteger
    released: ScaledInteger

    def __post_init__(self) -> None:
        values = tuple(_amount(value, "INVALID_RESERVATION_BUCKET") for value in (
            self.initial, self.consumed, self.active_remainder, self.released,
        ))
        _, units = _aligned(values)
        if units[0] != units[1] + units[2] + units[3]:
            raise DecisionError("RESERVATION_CONSERVATION_BREACH")

    def consume(self, delta: ScaledInteger) -> ReservationBucket:
        delta = _amount(delta, "INVALID_RESERVATION_CONSUMPTION")
        return ReservationBucket(
            initial=self.initial,
            consumed=_add(self.consumed, delta),
            active_remainder=_subtract(self.active_remainder, delta),
            released=self.released,
        )

    def release_active(self) -> ReservationBucket:
        return ReservationBucket(
            initial=self.initial,
            consumed=self.consumed,
            active_remainder=ScaledInteger(0, self.active_remainder.scale),
            released=_add(self.released, self.active_remainder),
        )

    def to_canonical_value(self) -> dict[str, object]:
        return {
            "initial": _amount_value(self.initial),
            "consumed": _amount_value(self.consumed),
            "active_remainder": _amount_value(self.active_remainder),
            "released": _amount_value(self.released),
        }


@dataclass(frozen=True, slots=True)
class ReservationConsumption:
    notional: ScaledInteger
    planned_loss: ScaledInteger
    fees: ScaledInteger
    slippage_impact: ScaledInteger
    turnover: ScaledInteger

    def __post_init__(self) -> None:
        for value in self.values:
            _amount(value, "INVALID_RESERVATION_CONSUMPTION")

    @property
    def values(self) -> tuple[ScaledInteger, ...]:
        return (self.notional, self.planned_loss, self.fees,
                self.slippage_impact, self.turnover)

    def to_canonical_value(self) -> dict[str, object]:
        return {
            "notional": _amount_value(self.notional),
            "planned_loss": _amount_value(self.planned_loss),
            "fees": _amount_value(self.fees),
            "slippage_impact": _amount_value(self.slippage_impact),
            "turnover": _amount_value(self.turnover),
        }


@dataclass(frozen=True, slots=True)
class ReservationVector:
    notional: ReservationBucket
    planned_loss: ReservationBucket
    fees: ReservationBucket
    slippage_impact: ReservationBucket
    turnover: ReservationBucket

    def __post_init__(self) -> None:
        if any(type(value) is not ReservationBucket for value in self.values):
            raise DecisionError("INVALID_RESERVATION_VECTOR")

    @property
    def values(self) -> tuple[ReservationBucket, ...]:
        return (self.notional, self.planned_loss, self.fees,
                self.slippage_impact, self.turnover)

    def consume(self, delta: ReservationConsumption) -> ReservationVector:
        if type(delta) is not ReservationConsumption:
            raise DecisionError("INVALID_RESERVATION_CONSUMPTION")
        return ReservationVector(*(
            bucket.consume(amount)
            for bucket, amount in zip(self.values, delta.values, strict=True)
        ))

    def release_active(self) -> ReservationVector:
        return ReservationVector(*(bucket.release_active() for bucket in self.values))

    def to_canonical_value(self) -> dict[str, object]:
        return {
            "notional": self.notional.to_canonical_value(),
            "planned_loss": self.planned_loss.to_canonical_value(),
            "fees": self.fees.to_canonical_value(),
            "slippage_impact": self.slippage_impact.to_canonical_value(),
            "turnover": self.turnover.to_canonical_value(),
        }


class ReservationLifecycle(str, Enum):
    ACTIVE = "ACTIVE"
    PARTIAL = "PARTIAL"
    UNKNOWN = "UNKNOWN"
    FILLED = "FILLED"
    CANCELLED = "CANCELLED"
    REJECTED = "REJECTED"
    EXPIRED = "EXPIRED"


_TERMINAL_RESERVATION_STATES = frozenset({
    ReservationLifecycle.FILLED,
    ReservationLifecycle.CANCELLED,
    ReservationLifecycle.REJECTED,
    ReservationLifecycle.EXPIRED,
})


@dataclass(frozen=True, slots=True)
class AppliedFill:
    fill_id: str
    consumption: ReservationConsumption

    def __post_init__(self) -> None:
        _text(self.fill_id, "INVALID_FILL_ID")
        if type(self.consumption) is not ReservationConsumption:
            raise DecisionError("INVALID_RESERVATION_CONSUMPTION")

    def to_canonical_value(self) -> dict[str, object]:
        return {"fill_id": self.fill_id,
                "consumption": self.consumption.to_canonical_value()}


@dataclass(frozen=True, slots=True)
class RiskReservation:
    reservation_id: str
    instrument_id: str
    pair_id: str
    horizon: str
    balances: ReservationVector
    lifecycle: ReservationLifecycle = ReservationLifecycle.ACTIVE
    applied_fills: tuple[AppliedFill, ...] = ()
    state_evidence_ref: ContentRef | None = None

    def __post_init__(self) -> None:
        for value, code in (
            (self.reservation_id, "INVALID_RESERVATION_ID"),
            (self.instrument_id, "INVALID_INSTRUMENT_ID"),
            (self.pair_id, "INVALID_PAIR_ID"),
            (self.horizon, "INVALID_HORIZON"),
        ):
            _text(value, code)
        if type(self.balances) is not ReservationVector:
            raise DecisionError("INVALID_RESERVATION_VECTOR")
        if type(self.lifecycle) is not ReservationLifecycle:
            raise DecisionError("INVALID_RESERVATION_LIFECYCLE")
        if type(self.applied_fills) is not tuple or any(
                type(item) is not AppliedFill for item in self.applied_fills):
            raise DecisionError("INVALID_APPLIED_FILLS")
        fill_ids = tuple(item.fill_id for item in self.applied_fills)
        if len(fill_ids) != len(set(fill_ids)):
            raise DecisionError("DUPLICATE_FILL_ID")
        needs_evidence = (self.lifecycle is ReservationLifecycle.UNKNOWN
                          or self.lifecycle in _TERMINAL_RESERVATION_STATES)
        if needs_evidence != (type(self.state_evidence_ref) is ContentRef):
            raise DecisionError("RESERVATION_EVIDENCE_MISMATCH")
        if self.lifecycle is ReservationLifecycle.ACTIVE and self.applied_fills:
            raise DecisionError("ACTIVE_RESERVATION_HAS_FILLS")
        if self.lifecycle is ReservationLifecycle.PARTIAL and not self.applied_fills:
            raise DecisionError("PARTIAL_RESERVATION_WITHOUT_FILL")
        if (self.lifecycle in _TERMINAL_RESERVATION_STATES
                and any(bucket.active_remainder.units != 0
                        for bucket in self.balances.values)):
            raise DecisionError("TERMINAL_RESERVATION_HAS_REMAINDER")

    def apply_fill(self, *, fill_id: str,
                   consumption: ReservationConsumption) -> RiskReservation:
        _text(fill_id, "INVALID_FILL_ID")
        if type(consumption) is not ReservationConsumption:
            raise DecisionError("INVALID_RESERVATION_CONSUMPTION")
        for applied in self.applied_fills:
            if applied.fill_id == fill_id:
                if applied.consumption == consumption:
                    return self
                raise DecisionError("FILL_IDENTITY_CONFLICT")
        if self.lifecycle not in (ReservationLifecycle.ACTIVE,
                                  ReservationLifecycle.PARTIAL):
            raise DecisionError("RESERVATION_NOT_FILLABLE")
        return replace(
            self,
            balances=self.balances.consume(consumption),
            lifecycle=ReservationLifecycle.PARTIAL,
            applied_fills=(*self.applied_fills, AppliedFill(fill_id, consumption)),
        )

    def mark_unknown(self, evidence_ref: ContentRef) -> RiskReservation:
        if self.lifecycle not in (ReservationLifecycle.ACTIVE,
                                  ReservationLifecycle.PARTIAL):
            raise DecisionError("INVALID_UNKNOWN_TRANSITION")
        if type(evidence_ref) is not ContentRef:
            raise DecisionError("INVALID_RESERVATION_EVIDENCE")
        return replace(self, lifecycle=ReservationLifecycle.UNKNOWN,
                       state_evidence_ref=evidence_ref)

    def terminalize(self, lifecycle: ReservationLifecycle,
                    evidence_ref: ContentRef) -> RiskReservation:
        if lifecycle not in _TERMINAL_RESERVATION_STATES:
            raise DecisionError("INVALID_TERMINAL_RESERVATION_STATE")
        if self.lifecycle in _TERMINAL_RESERVATION_STATES:
            raise DecisionError("RESERVATION_ALREADY_TERMINAL")
        if type(evidence_ref) is not ContentRef:
            raise DecisionError("INVALID_RESERVATION_EVIDENCE")
        return replace(self, balances=self.balances.release_active(),
                       lifecycle=lifecycle, state_evidence_ref=evidence_ref)

    def to_canonical_value(self) -> dict[str, object]:
        return {
            "reservation_id": self.reservation_id,
            "instrument_id": self.instrument_id,
            "pair_id": self.pair_id,
            "horizon": self.horizon,
            "balances": self.balances.to_canonical_value(),
            "lifecycle": self.lifecycle.value,
            "applied_fills": tuple(item.to_canonical_value() for item in self.applied_fills),
            "state_evidence_ref": (None if self.state_evidence_ref is None
                                   else self.state_evidence_ref.to_canonical_value()),
        }


@dataclass(frozen=True, slots=True)
class ConstituentCheckpoint:
    kind: str
    constituent_id: str
    sequence: int
    reference: ContentRef

    def __post_init__(self) -> None:
        _text(self.kind, "INVALID_CONSTITUENT_KIND")
        _text(self.constituent_id, "INVALID_CONSTITUENT_ID")
        if type(self.sequence) is not int or self.sequence < 0:
            raise DecisionError("INVALID_CONSTITUENT_SEQUENCE")
        if type(self.reference) is not ContentRef:
            raise DecisionError("INVALID_CONSTITUENT_REFERENCE")

    @property
    def key(self) -> tuple[str, str]:
        return self.kind, self.constituent_id

    def to_canonical_value(self) -> dict[str, object]:
        return {
            "kind": self.kind,
            "constituent_id": self.constituent_id,
            "sequence": self.sequence,
            "reference": self.reference.to_canonical_value(),
        }


@dataclass(frozen=True, slots=True)
class PortfolioConsistencyCut:
    cutoff_at_utc: datetime
    total_equity: ScaledInteger
    opportunity_set_ref: ContentRef
    market_cutoff_ref: ContentRef
    journal_high_water: int
    positions_ref: ContentRef
    working_orders_ref: ContentRef
    risk_state_ref: ContentRef
    constituents: tuple[ConstituentCheckpoint, ...]

    def __post_init__(self) -> None:
        if (type(self.cutoff_at_utc) is not datetime
                or self.cutoff_at_utc.tzinfo is None
                or self.cutoff_at_utc.utcoffset() != UTC.utcoffset(self.cutoff_at_utc)):
            raise DecisionError("INVALID_PORTFOLIO_CUTOFF")
        _amount(self.total_equity, "INVALID_TOTAL_EQUITY")
        if self.total_equity.units <= 0:
            raise DecisionError("INVALID_TOTAL_EQUITY")
        refs = (self.opportunity_set_ref, self.market_cutoff_ref,
                self.positions_ref, self.working_orders_ref, self.risk_state_ref)
        if any(type(value) is not ContentRef for value in refs):
            raise DecisionError("INVALID_CONSISTENCY_REFERENCE")
        if type(self.journal_high_water) is not int or self.journal_high_water < 0:
            raise DecisionError("INVALID_JOURNAL_HIGH_WATER")
        if (type(self.constituents) is not tuple or not self.constituents
                or any(type(item) is not ConstituentCheckpoint for item in self.constituents)):
            raise DecisionError("INVALID_CONSTITUENT_CHECKPOINTS")
        mapping = {item.key: item for item in self.constituents}
        if len(mapping) != len(self.constituents):
            raise DecisionError("DUPLICATE_CONSTITUENT_CHECKPOINT")
        required = {
            ("positions", "portfolio"): self.positions_ref,
            ("working-orders", "portfolio"): self.working_orders_ref,
            ("risk-state", "portfolio"): self.risk_state_ref,
        }
        if any(key not in mapping or mapping[key].reference != reference
               for key, reference in required.items()):
            raise DecisionError("CONSISTENCY_REFERENCE_MISMATCH")

    def to_canonical_value(self) -> dict[str, object]:
        ordered = tuple(sorted(self.constituents, key=lambda item: item.key))
        return {
            "cutoff_at_utc": self.cutoff_at_utc,
            "total_equity": _amount_value(self.total_equity),
            "opportunity_set_ref": self.opportunity_set_ref.to_canonical_value(),
            "market_cutoff_ref": self.market_cutoff_ref.to_canonical_value(),
            "journal_high_water": self.journal_high_water,
            "positions_ref": self.positions_ref.to_canonical_value(),
            "working_orders_ref": self.working_orders_ref.to_canonical_value(),
            "risk_state_ref": self.risk_state_ref.to_canonical_value(),
            "constituents": tuple(item.to_canonical_value() for item in ordered),
        }


@dataclass(frozen=True, slots=True)
class AllocationProposal:
    decision_ref: ContentRef
    pair_id: str
    instrument_id: str
    horizon: str
    risk_increasing: bool
    reservation: RiskReservation

    def __post_init__(self) -> None:
        if type(self.decision_ref) is not ContentRef:
            raise DecisionError("INVALID_DECISION_REFERENCE")
        for value, code in ((self.pair_id, "INVALID_PAIR_ID"),
                            (self.instrument_id, "INVALID_INSTRUMENT_ID"),
                            (self.horizon, "INVALID_HORIZON")):
            _text(value, code)
        if type(self.risk_increasing) is not bool:
            raise DecisionError("INVALID_RISK_DIRECTION")
        if type(self.reservation) is not RiskReservation:
            raise DecisionError("INVALID_RISK_RESERVATION")
        if (self.reservation.pair_id != self.pair_id
                or self.reservation.instrument_id != self.instrument_id
                or self.reservation.horizon != self.horizon):
            raise DecisionError("PROPOSAL_RESERVATION_MISMATCH")

    def to_canonical_value(self) -> dict[str, object]:
        return {
            "decision_ref": self.decision_ref.to_canonical_value(),
            "pair_id": self.pair_id,
            "instrument_id": self.instrument_id,
            "horizon": self.horizon,
            "risk_increasing": self.risk_increasing,
            "reservation": self.reservation.to_canonical_value(),
        }


class AllocationRejectCode(str, Enum):
    EMPTY_BATCH = "EMPTY_BATCH"
    STALE_CONSTITUENT = "STALE_CONSTITUENT"
    DUPLICATE_DECISION = "DUPLICATE_DECISION"
    DUPLICATE_RESERVATION = "DUPLICATE_RESERVATION"
    DUPLICATE_PAIR_OWNERSHIP = "DUPLICATE_PAIR_OWNERSHIP"
    EQUITY_CAP_EXCEEDED = "EQUITY_CAP_EXCEEDED"


@dataclass(frozen=True, slots=True)
class AllocationRejection:
    code: AllocationRejectCode
    details: tuple[str, ...]

    def __post_init__(self) -> None:
        if type(self.code) is not AllocationRejectCode:
            raise DecisionError("INVALID_ALLOCATION_REJECTION")
        if type(self.details) is not tuple or any(type(value) is not str for value in self.details):
            raise DecisionError("INVALID_ALLOCATION_REJECTION")


def _accepted_references(
    cut: PortfolioConsistencyCut,
    observed: tuple[ConstituentCheckpoint, ...],
    expected_sequence: int,
    proposals: tuple[AllocationProposal, ...],
    ownership: tuple[tuple[str, str], ...],
    next_risk_state_ref: ContentRef,
) -> tuple[ContentRef, ContentRef, ContentRef]:
    batch_value = {
        "cut": cut.to_canonical_value(),
        "observed_constituents": tuple(
            item.to_canonical_value() for item in observed),
        "expected_sequence": expected_sequence,
        "resulting_sequence": expected_sequence + 1,
        "proposals": tuple(item.to_canonical_value() for item in proposals),
        "pair_horizon_ownership": ownership,
        "next_risk_state_ref": next_risk_state_ref.to_canonical_value(),
    }
    batch_ref = ContentRef.v2("autotrade-next", "PortfolioAllocationBatch", batch_value)
    event_ref = ContentRef.v2(
        "autotrade-next", "PortfolioAllocationCommitted",
        {"batch_ref": batch_ref.to_canonical_value(),
         "sequence": expected_sequence + 1},
    )
    outbox_ref = ContentRef.v2(
        "autotrade-next", "PortfolioAllocationOutbox",
        {"event_ref": event_ref.to_canonical_value(), "status": "PENDING"},
    )
    return batch_ref, event_ref, outbox_ref


def _rejection_reference(cut: PortfolioConsistencyCut,
                         observed: tuple[ConstituentCheckpoint, ...],
                         expected_sequence: int,
                         rejection: AllocationRejection) -> ContentRef:
    return ContentRef.v2(
        "autotrade-next", "PortfolioAllocationRejected",
        {
            "cut": cut.to_canonical_value(),
            "observed_constituents": tuple(
                item.to_canonical_value() for item in observed),
            "expected_sequence": expected_sequence,
            "code": rejection.code.value,
            "details": rejection.details,
        },
    )


@dataclass(frozen=True, slots=True)
class PortfolioAllocation:
    consistency_cut: PortfolioConsistencyCut
    observed_constituents: tuple[ConstituentCheckpoint, ...]
    expected_sequence: int
    proposals: tuple[AllocationProposal, ...]
    pair_horizon_ownership: tuple[tuple[str, str], ...]
    next_risk_state_ref: ContentRef | None
    batch_ref: ContentRef
    event_ref: ContentRef | None
    outbox_ref: ContentRef | None
    rejection: AllocationRejection | None = None

    def __post_init__(self) -> None:
        if type(self.consistency_cut) is not PortfolioConsistencyCut:
            raise DecisionError("INVALID_CONSISTENCY_CUT")
        if (type(self.observed_constituents) is not tuple
                or any(type(item) is not ConstituentCheckpoint
                       for item in self.observed_constituents)):
            raise DecisionError("INVALID_OBSERVED_CHECKPOINTS")
        observed_map = {item.key: item for item in self.observed_constituents}
        if len(observed_map) != len(self.observed_constituents):
            raise DecisionError("DUPLICATE_OBSERVED_CHECKPOINT")
        canonical_observed = tuple(sorted(
            self.observed_constituents, key=lambda item: item.key))
        if self.observed_constituents != canonical_observed:
            raise DecisionError("NON_CANONICAL_CHECKPOINT_ORDER")
        if type(self.expected_sequence) is not int or self.expected_sequence < 0:
            raise DecisionError("INVALID_EXPECTED_SEQUENCE")
        if type(self.batch_ref) is not ContentRef:
            raise DecisionError("INVALID_ALLOCATION_BATCH_REF")
        if self.rejection is None:
            if (not self.proposals or type(self.next_risk_state_ref) is not ContentRef
                    or type(self.event_ref) is not ContentRef
                    or type(self.outbox_ref) is not ContentRef):
                raise DecisionError("INCOMPLETE_EXECUTABLE_ALLOCATION")
            if (type(self.proposals) is not tuple
                    or any(type(item) is not AllocationProposal for item in self.proposals)):
                raise DecisionError("INVALID_ALLOCATION_PROPOSALS")
            ordered = tuple(sorted(
                self.proposals,
                key=lambda item: (item.pair_id, item.horizon, item.instrument_id,
                                  item.decision_ref.key),
            ))
            if self.proposals != ordered:
                raise DecisionError("NON_CANONICAL_PROPOSAL_ORDER")
            decisions = tuple(item.decision_ref.key for item in self.proposals)
            reservations = tuple(item.reservation.reservation_id for item in self.proposals)
            pairs = tuple(item.pair_id for item in self.proposals)
            if (len(decisions) != len(set(decisions))
                    or len(reservations) != len(set(reservations))
                    or len(pairs) != len(set(pairs))):
                raise DecisionError("DUPLICATE_EXECUTABLE_ALLOCATION_MEMBER")
            mismatches = _checkpoint_mismatches(
                self.consistency_cut.constituents, self.observed_constituents)
            if mismatches and any(item.risk_increasing for item in self.proposals):
                raise DecisionError("STALE_EXECUTABLE_ALLOCATION")
            notionals = tuple(
                item.reservation.balances.notional.initial
                for item in self.proposals if item.risk_increasing)
            if notionals:
                _, aligned = _aligned((*notionals, self.consistency_cut.total_equity))
                if sum(aligned[:-1]) > aligned[-1]:
                    raise DecisionError("EXECUTABLE_ALLOCATION_EXCEEDS_EQUITY")
            expected_ownership = tuple((item.pair_id, item.horizon)
                                       for item in self.proposals)
            if self.pair_horizon_ownership != expected_ownership:
                raise DecisionError("PAIR_HORIZON_OWNERSHIP_MISMATCH")
            expected_refs = _accepted_references(
                self.consistency_cut, self.observed_constituents,
                self.expected_sequence, self.proposals,
                self.pair_horizon_ownership, self.next_risk_state_ref,
            )
            if (self.batch_ref, self.event_ref, self.outbox_ref) != expected_refs:
                raise DecisionError("ALLOCATION_CONTENT_REFERENCE_MISMATCH")
        elif (self.proposals or self.pair_horizon_ownership
              or self.next_risk_state_ref is not None
              or self.event_ref is not None or self.outbox_ref is not None):
            raise DecisionError("REJECTED_ALLOCATION_HAS_EXECUTABLE_EFFECTS")
        elif (type(self.rejection) is not AllocationRejection
              or self.batch_ref != _rejection_reference(
                  self.consistency_cut, self.observed_constituents,
                  self.expected_sequence, self.rejection)):
            raise DecisionError("REJECTION_CONTENT_REFERENCE_MISMATCH")

    @property
    def executable(self) -> bool:
        return self.rejection is None


def _checkpoint_mismatches(
    frozen: tuple[ConstituentCheckpoint, ...],
    observed: tuple[ConstituentCheckpoint, ...],
) -> tuple[str, ...]:
    if type(observed) is not tuple or any(
            type(item) is not ConstituentCheckpoint for item in observed):
        raise DecisionError("INVALID_OBSERVED_CHECKPOINTS")
    frozen_map = {item.key: item for item in frozen}
    observed_map = {item.key: item for item in observed}
    if len(observed_map) != len(observed):
        raise DecisionError("DUPLICATE_OBSERVED_CHECKPOINT")
    keys = sorted(set(frozen_map) | set(observed_map))
    return tuple(f"{kind}:{identifier}" for kind, identifier in keys
                 if frozen_map.get((kind, identifier)) != observed_map.get((kind, identifier)))


def _rejected(cut: PortfolioConsistencyCut,
              observed: tuple[ConstituentCheckpoint, ...],
              expected_sequence: int,
              code: AllocationRejectCode, details: tuple[str, ...]) -> PortfolioAllocation:
    rejection = AllocationRejection(code, details)
    return PortfolioAllocation(
        cut, observed, expected_sequence, (), (), None,
        _rejection_reference(cut, observed, expected_sequence, rejection),
        None, None, rejection,
    )


def build_portfolio_allocation(
    *,
    consistency_cut: PortfolioConsistencyCut,
    proposals: tuple[AllocationProposal, ...],
    observed_constituents: tuple[ConstituentCheckpoint, ...],
    expected_sequence: int,
    next_risk_state_ref: ContentRef,
) -> PortfolioAllocation:
    if type(consistency_cut) is not PortfolioConsistencyCut:
        raise DecisionError("INVALID_CONSISTENCY_CUT")
    if type(expected_sequence) is not int or expected_sequence < 0:
        raise DecisionError("INVALID_EXPECTED_SEQUENCE")
    if type(next_risk_state_ref) is not ContentRef:
        raise DecisionError("INVALID_NEXT_RISK_STATE_REFERENCE")
    if type(proposals) is not tuple or any(
            type(item) is not AllocationProposal for item in proposals):
        raise DecisionError("INVALID_ALLOCATION_PROPOSALS")
    mismatches = _checkpoint_mismatches(consistency_cut.constituents,
                                        observed_constituents)
    canonical_observed = tuple(sorted(
        observed_constituents, key=lambda item: item.key))
    if not proposals:
        return _rejected(consistency_cut, canonical_observed, expected_sequence,
                         AllocationRejectCode.EMPTY_BATCH, ())

    ordered = tuple(sorted(
        proposals,
        key=lambda item: (item.pair_id, item.horizon, item.instrument_id,
                          item.decision_ref.key),
    ))
    if mismatches and any(item.risk_increasing for item in ordered):
        return _rejected(consistency_cut, canonical_observed, expected_sequence,
                         AllocationRejectCode.STALE_CONSTITUENT, mismatches)

    decisions = tuple(item.decision_ref.key for item in ordered)
    if len(decisions) != len(set(decisions)):
        return _rejected(consistency_cut, canonical_observed, expected_sequence,
                         AllocationRejectCode.DUPLICATE_DECISION, ())
    reservations = tuple(item.reservation.reservation_id for item in ordered)
    if len(reservations) != len(set(reservations)):
        return _rejected(consistency_cut, canonical_observed, expected_sequence,
                         AllocationRejectCode.DUPLICATE_RESERVATION, ())

    ownership: dict[str, str] = {}
    for item in ordered:
        if item.pair_id in ownership:
            return _rejected(
                consistency_cut, canonical_observed, expected_sequence,
                AllocationRejectCode.DUPLICATE_PAIR_OWNERSHIP,
                (item.pair_id, ownership[item.pair_id], item.horizon),
            )
        ownership[item.pair_id] = item.horizon

    notionals = tuple(item.reservation.balances.notional.initial
                      for item in ordered if item.risk_increasing)
    if notionals:
        target, aligned = _aligned((*notionals, consistency_cut.total_equity))
        del target
        if sum(aligned[:-1]) > aligned[-1]:
            return _rejected(consistency_cut, canonical_observed, expected_sequence,
                             AllocationRejectCode.EQUITY_CAP_EXCEEDED, ())

    ownership_tuple = tuple(sorted(ownership.items()))
    batch_ref, event_ref, outbox_ref = _accepted_references(
        consistency_cut, canonical_observed, expected_sequence, ordered, ownership_tuple,
        next_risk_state_ref,
    )
    return PortfolioAllocation(
        consistency_cut, canonical_observed, expected_sequence, ordered, ownership_tuple,
        next_risk_state_ref, batch_ref, event_ref, outbox_ref,
    )


__all__ = (
    "AllocationProposal",
    "AllocationRejectCode",
    "AllocationRejection",
    "AppliedFill",
    "ConstituentCheckpoint",
    "MAX_RESERVATION_SCALE",
    "PortfolioAllocation",
    "PortfolioConsistencyCut",
    "ReservationBucket",
    "ReservationConsumption",
    "ReservationLifecycle",
    "ReservationVector",
    "RiskReservation",
    "build_portfolio_allocation",
)
