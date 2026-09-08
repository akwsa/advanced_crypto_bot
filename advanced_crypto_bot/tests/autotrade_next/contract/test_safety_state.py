"""Contracts for Story 3.4 additive safety cause lattice."""

from dataclasses import replace
from datetime import UTC, datetime, timedelta

import pytest

from autotrade_next.domain.content import ContentRef
from autotrade_next.domain.errors import DecisionError
from autotrade_next.domain.safety_state import (
    ClearPredicate,
    ProtectiveAction,
    SafetyCause,
    SafetyCauseKind,
    SafetyClearProof,
    SafetyClearRecord,
    SafetyScope,
    SafetyScopeLevel,
    SafetySeverity,
    SafetyStateLattice,
)


NOW = datetime(2026, 8, 30, 10, 0, tzinfo=UTC)


def ref(kind: str, value: str) -> ContentRef:
    return ContentRef.v2("autotrade-next", kind, {"value": value})


def stale() -> SafetyCause:
    return SafetyCause.create(
        kind=SafetyCauseKind.STALE_DATA,
        scope=SafetyScope(SafetyScopeLevel.INSTRUMENT, "BTC-IDR"),
        severity=SafetySeverity.ENTRY_FREEZE,
        evidence_refs=(ref("SafetyEvidence", "stale-book"),),
        expected_sequence=0,
        recorded_at_utc=NOW,
    )


def fence() -> SafetyCause:
    return SafetyCause.create(
        kind=SafetyCauseKind.FENCE_LOSS,
        scope=SafetyScope(SafetyScopeLevel.AUTHORITY, "global-writer"),
        severity=SafetySeverity.AUTHORITY_HALT,
        evidence_refs=(ref("SafetyEvidence", "lost-lease"),),
        expected_sequence=1,
        recorded_at_utc=NOW + timedelta(seconds=1),
    )


def proof(cause: SafetyCause, *, sequence: int, predicate: ClearPredicate | None = None,
          evidence: str = "recovered") -> SafetyClearProof:
    return SafetyClearProof(
        cause_id=cause.cause_id,
        predicate=cause.clear_predicate if predicate is None else predicate,
        evidence_refs=(ref("RecoveryEvidence", evidence),),
        expected_sequence=sequence,
        observed_at_utc=NOW + timedelta(seconds=2),
        authority_ref=ref("ClearAuthority", "operator-approval"),
    )


def test_cause_identity_is_deterministic_and_caller_cannot_forge_it() -> None:
    first = stale()
    assert first == stale()
    with pytest.raises(DecisionError, match="SAFETY_CAUSE_ID_MISMATCH"):
        replace(first, cause_id="caller-id")


def test_domain_package_exports_complete_safety_contract() -> None:
    from autotrade_next.domain import (  # pylint: disable=import-outside-toplevel
        ClearPredicate as exported_predicate,
        ProtectiveAction as exported_action,
        SafetyClearProof as exported_proof,
        SafetyClearRecord as exported_record,
        SafetyScope as exported_scope,
        SafetySeverity as exported_severity,
    )

    assert exported_predicate is ClearPredicate
    assert exported_action is ProtectiveAction
    assert exported_proof is SafetyClearProof
    assert exported_record is SafetyClearRecord
    assert exported_scope is SafetyScope
    assert exported_severity is SafetySeverity


def test_scope_severity_join_and_protective_intersection_are_canonical() -> None:
    lattice = SafetyStateLattice.empty().add_cause(stale(), expected_sequence=0)
    lattice = lattice.add_cause(fence(), expected_sequence=1)
    assert lattice.sequence == 2
    assert lattice.highest_effective_level is SafetyScopeLevel.AUTHORITY
    assert lattice.effective_severity is SafetySeverity.AUTHORITY_HALT
    assert lattice.is_entry_frozen
    assert lattice.allowed_protective_actions == (
        ProtectiveAction.CANCEL,
        ProtectiveAction.EXIT,
        ProtectiveAction.RECONCILE,
    )


def test_clear_is_additive_and_never_clears_another_active_cause() -> None:
    stale_cause, fence_cause = stale(), fence()
    lattice = SafetyStateLattice.empty().add_cause(stale_cause, expected_sequence=0)
    lattice = lattice.add_cause(fence_cause, expected_sequence=1)
    cleared = lattice.clear_cause(proof(stale_cause, sequence=2))
    assert cleared.sequence == 3
    assert tuple(item.cause_id for item in cleared.active_causes) == (fence_cause.cause_id,)
    assert len(cleared.clear_history) == 1
    assert cleared.is_entry_frozen
    assert cleared.clear_cause(proof(stale_cause, sequence=2)) is cleared


@pytest.mark.parametrize(
    "bad_proof",
    (
        lambda cause: proof(cause, sequence=99),
        lambda cause: proof(cause, sequence=1, predicate=ClearPredicate.FENCE_REACQUIRED),
        lambda cause: SafetyClearProof(
            cause.cause_id, cause.clear_predicate, cause.evidence_refs, 1,
            NOW + timedelta(seconds=2), ref("ClearAuthority", "operator"),
        ),
        lambda cause: replace(proof(cause, sequence=1), observed_at_utc=NOW - timedelta(microseconds=1)),
    ),
)
def test_clear_requires_exact_sequence_predicate_new_evidence_and_causal_time(bad_proof) -> None:
    cause = stale()
    lattice = SafetyStateLattice.empty().add_cause(cause, expected_sequence=0)
    with pytest.raises(DecisionError):
        lattice.clear_cause(bad_proof(cause))
    assert lattice.is_entry_frozen and lattice.clear_history == ()


def test_clear_rejects_evidence_at_the_same_instant_as_the_cause() -> None:
    cause = stale()
    lattice = SafetyStateLattice.empty().add_cause(cause, expected_sequence=0)
    same_instant_proof = replace(proof(cause, sequence=1), observed_at_utc=NOW)

    with pytest.raises(DecisionError, match="CLEAR_EVIDENCE_PRECEDES_CAUSE"):
        lattice.clear_cause(same_instant_proof)


@pytest.mark.parametrize(
    "authority_ref",
    (
        ref("WrongAuthorityKind", "operator-approval"),
        ContentRef.v1("ClearAuthority", {"value": "operator-approval"}),
        ContentRef.v2("foreign-domain", "ClearAuthority", {"value": "operator-approval"}),
    ),
)
def test_clear_proof_requires_a_typed_canonical_authority_reference(authority_ref) -> None:
    cause = stale()

    with pytest.raises(DecisionError, match="INVALID_CLEAR_AUTHORITY"):
        replace(proof(cause, sequence=1), authority_ref=authority_ref)


def test_lattice_rejects_forged_or_inconsistent_additive_history() -> None:
    cause = stale()
    lattice = SafetyStateLattice.empty().add_cause(cause, expected_sequence=0)
    record = SafetyClearRecord(
        cause_id=cause.cause_id,
        proof_ref=proof(cause, sequence=1).reference,
        cleared_sequence=2,
    )
    future_cause = SafetyCause.create(
        kind=SafetyCauseKind.STALE_DATA,
        scope=SafetyScope(SafetyScopeLevel.INSTRUMENT, "BTC-IDR"),
        severity=SafetySeverity.ENTRY_FREEZE,
        evidence_refs=(ref("SafetyEvidence", "future-book"),),
        expected_sequence=1,
        recorded_at_utc=NOW,
    )

    with pytest.raises(DecisionError, match="INVALID_ACTIVE_CAUSE_SEQUENCE"):
        SafetyStateLattice(1, (future_cause,), ())
    with pytest.raises(DecisionError, match="INVALID_CLEAR_HISTORY"):
        SafetyStateLattice(1, lattice.active_causes, (record,))
    with pytest.raises(DecisionError, match="INVALID_CLEAR_RECORD_PROOF"):
        SafetyClearRecord(cause.cause_id, ref("OtherProof", "forged"), 1)


def test_kind_matrix_rejects_under_scoped_or_under_severity_cause() -> None:
    with pytest.raises(DecisionError, match="SAFETY_SCOPE_BELOW_MATRIX_MINIMUM"):
        SafetyCause.create(
            kind=SafetyCauseKind.FENCE_LOSS,
            scope=SafetyScope(SafetyScopeLevel.ORDER, "order-1"),
            severity=SafetySeverity.AUTHORITY_HALT,
            evidence_refs=(ref("Evidence", "fence"),), expected_sequence=0,
            recorded_at_utc=NOW,
        )
    with pytest.raises(DecisionError, match="SAFETY_SEVERITY_BELOW_MATRIX_MINIMUM"):
        SafetyCause.create(
            kind=SafetyCauseKind.FENCE_LOSS,
            scope=SafetyScope(SafetyScopeLevel.AUTHORITY, "global"),
            severity=SafetySeverity.ENTRY_FREEZE,
            evidence_refs=(ref("Evidence", "fence"),), expected_sequence=0,
            recorded_at_utc=NOW,
        )


def test_duplicate_add_is_idempotent_but_sequence_jump_is_denied() -> None:
    cause = stale()
    lattice = SafetyStateLattice.empty().add_cause(cause, expected_sequence=0)
    assert lattice.add_cause(cause, expected_sequence=0) is lattice
    with pytest.raises(DecisionError, match="SAFETY_SEQUENCE_CONFLICT"):
        lattice.add_cause(fence(), expected_sequence=9)
