from dataclasses import FrozenInstanceError, replace
from datetime import UTC, datetime
from decimal import Decimal
from hashlib import sha256

import pytest

from autotrade_next.domain.candidate import (
    CandidateEligibility, CandidateProvenance, CandidateTrigger, ClockRead,
    EligibilityReason,
    RngRef, RuntimeManifestRef, SourceCursor, StableRef, capture_candidate,
)
from autotrade_next.domain.decision import (
    CanonicalDecision, CommitStatus, DecisionAction, DecisionBoundary,
    DecisionCommitResult, DecisionError, DecisionReason, DecisionReasonCode,
    IntegrityIncident, PositionContext, PositionState, commit_decision,
    evaluate_decision,
)
from autotrade_next.domain.identity import build_identity
from autotrade_next.domain.numeric import ScaledInteger

NOW = datetime(2026, 8, 26, tzinfo=UTC)


def candidate(*, executable=True, parent_position_id=None):
    provenance = CandidateProvenance(
        authority_scope_id="scope:dryrun", portfolio_id="portfolio:main",
        experiment_id="experiment:no-entry", strategy_version="strategy:v1",
        correlation_id="corr:1", causation_id="cause:1",
        ordered_input_ids=["input:1"], event_at_utc=NOW, received_at_utc=NOW,
        source_cursors=[SourceCursor("source:1", None, "ingest:1", "LOCAL_ONLY", 0, "QUALIFIED")],
        eligibility=(CandidateEligibility(True) if executable else
            CandidateEligibility(False, reason=EligibilityReason.STALE, evidence_ref="stale:1")),
        universe_ref=StableRef("universe", "version:1"),
        instrument_rules_ref=StableRef("rules", "version:1"),
        scheduler_ref=StableRef("scheduler", "version:1"),
        clock_reads=[ClockRead("clock:1", NOW)], rng_ref=RngRef("pcg64", "state:1"),
        runtime_ref=RuntimeManifestRef("python:3.12", "numeric:v1", "env:1", "commit:1", "image:1", "lock:1"),
        data_ref=StableRef("data", "version:1"), feature_ref=StableRef("feature", "version:1"),
        model_ref=StableRef("model", "version:1"), config_ref=StableRef("config", "version:1"),
        external_response_ids=[],
    )
    return capture_candidate(
        instrument_id="btc_idr",
        horizon_id="1H",
        trigger_kind=(
            CandidateTrigger.PROTECTIVE_EVENT
            if parent_position_id is not None
            else CandidateTrigger.CLOSED_BAR
        ),
        trigger_at_utc=NOW,
        scan_trigger_version="scan:v1",
        data_revision="revision:1",
        provenance=provenance,
        parent_position_id=parent_position_id,
    )


def boundary():
    return DecisionBoundary("boundary:v1", "ref:policy-boundary", ["evidence:1"])


@pytest.mark.parametrize("state,action", [
    (PositionState.FLAT, DecisionAction.ENTER),
    (PositionState.FLAT, DecisionAction.ABSTAIN),
    (PositionState.EXPOSED, DecisionAction.HOLD),
    (PositionState.EXPOSED, DecisionAction.EXIT),
])
def test_legal_matrix_and_deterministic_identity(state, action):
    position = PositionContext(state, "position-snapshot:1", "position:1" if state is PositionState.EXPOSED else None)
    target = ScaledInteger(0, 8) if action is DecisionAction.EXIT else None
    decision = evaluate_decision(candidate(), policy_version="policy:v1", position=position,
        proposed_action=action, boundary=boundary(), exit_target=target)
    assert decision.decision_id == build_identity("decision", {"candidate_id": decision.candidate_id.key, "policy_version": "policy:v1"})
    expected = (
        DecisionAction.ABSTAIN
        if state is PositionState.FLAT and action is DecisionAction.ENTER
        else action
    )
    assert decision.action is expected
    assert decision.canonical_bytes() == evaluate_decision(candidate(), policy_version="policy:v1", position=position,
        proposed_action=action, boundary=boundary(), exit_target=target).canonical_bytes()


@pytest.mark.parametrize("state,action", [
    (PositionState.FLAT, DecisionAction.HOLD), (PositionState.FLAT, DecisionAction.EXIT),
    (PositionState.EXPOSED, DecisionAction.ENTER), (PositionState.EXPOSED, DecisionAction.ABSTAIN),
])
def test_illegal_matrix_rejects_with_incident(state, action):
    position = PositionContext(state, "position-snapshot:1", "position:1" if state is PositionState.EXPOSED else None)
    with pytest.raises(DecisionError) as caught:
        evaluate_decision(candidate(), policy_version="policy:v1", position=position,
            proposed_action=action, boundary=boundary(), exit_target=ScaledInteger(0, 8) if action is DecisionAction.EXIT else None)
    assert caught.value.error_code == "ILLEGAL_DECISION_TRANSITION"
    assert caught.value.partial_decision is None
    assert caught.value.incident.code == "ILLEGAL_DECISION_TRANSITION"


def test_entry_veto_and_ineligible_candidate_abstain():
    position = PositionContext(PositionState.FLAT, "position-snapshot:flat")
    vetoed = evaluate_decision(candidate(), policy_version="policy:v1", position=position,
        proposed_action=DecisionAction.ENTER, boundary=boundary(), entry_veto=True)
    assert (vetoed.action, vetoed.reason.code) == (DecisionAction.ABSTAIN, DecisionReasonCode.ENTRY_VETO)
    ineligible = evaluate_decision(candidate(executable=False), policy_version="policy:v1", position=position,
        proposed_action=DecisionAction.ENTER, boundary=boundary())
    assert (ineligible.action, ineligible.reason.code) == (DecisionAction.ABSTAIN, DecisionReasonCode.CANDIDATE_INELIGIBLE)


def test_v1_executable_self_claim_cannot_increase_exposure() -> None:
    decision = evaluate_decision(
        candidate(executable=True),
        policy_version="policy:v1",
        position=PositionContext(PositionState.FLAT, "position-snapshot:flat"),
        proposed_action=DecisionAction.ENTER,
        boundary=boundary(),
    )
    assert decision.action is DecisionAction.ABSTAIN
    assert decision.reason.code is DecisionReasonCode.CANDIDATE_INELIGIBLE


@pytest.mark.parametrize("proposed", list(DecisionAction))
def test_protective_exit_dominates_every_proposal_even_when_candidate_ineligible(proposed):
    decision = evaluate_decision(candidate(executable=False), policy_version="policy:v1",
        position=PositionContext(PositionState.EXPOSED, "position-snapshot:1", "position:1"),
        proposed_action=proposed, boundary=boundary(), entry_veto=True, protective_exit=True,
        exit_target=ScaledInteger(0, 8))
    assert (decision.action, decision.reason.code) == (DecisionAction.EXIT, DecisionReasonCode.PROTECTIVE_EXIT)


def test_exit_target_contract_and_immutability():
    flat = PositionContext(PositionState.FLAT, "position-snapshot:flat")
    with pytest.raises(DecisionError) as extra:
        evaluate_decision(candidate(), policy_version="policy:v1", position=flat,
            proposed_action=DecisionAction.ENTER, boundary=boundary(), exit_target=ScaledInteger(0, 8))
    assert extra.value.error_code == "INVALID_EXIT_TARGET"
    exposed = PositionContext(PositionState.EXPOSED, "position-snapshot:1", "position:1")
    with pytest.raises(DecisionError):
        evaluate_decision(candidate(), policy_version="policy:v1", position=exposed,
            proposed_action=DecisionAction.EXIT, boundary=boundary())
    decision = evaluate_decision(candidate(), policy_version="policy:v1", position=flat,
        proposed_action=DecisionAction.ABSTAIN, boundary=boundary())
    with pytest.raises(FrozenInstanceError):
        decision.policy_version = "changed"  # type: ignore[misc]


def test_commit_created_idempotent_and_conflict_preserves_original():
    position = PositionContext(PositionState.FLAT, "position-snapshot:flat")
    original = evaluate_decision(candidate(), policy_version="policy:v1", position=position,
        proposed_action=DecisionAction.ABSTAIN, boundary=boundary())
    created = commit_decision(None, original)
    duplicate = commit_decision(original, original)
    conflicting = evaluate_decision(candidate(), policy_version="policy:v1", position=position,
        proposed_action=DecisionAction.ENTER, boundary=boundary())
    before = original.canonical_bytes()
    conflict = commit_decision(original, conflicting)
    assert created.status is CommitStatus.CREATED
    assert duplicate.status is CommitStatus.IDEMPOTENT
    assert conflict.status is CommitStatus.CONFLICT
    assert conflict.decision is original
    assert conflict.incident.code == "DECISION_CONFLICT"
    assert original.canonical_bytes() == before


def test_forged_decision_identity_is_rejected():
    decision = evaluate_decision(candidate(), policy_version="policy:v1",
        position=PositionContext(PositionState.FLAT, "position-snapshot:flat"),
        proposed_action=DecisionAction.ABSTAIN, boundary=boundary())
    wrong = build_identity("decision", {"candidate_id": decision.candidate_id.key, "policy_version": "other"})
    with pytest.raises(DecisionError):
        replace(decision, decision_id=wrong)


@pytest.mark.parametrize(
    "state,action,reason",
    [
        (PositionState.FLAT, DecisionAction.HOLD, DecisionReasonCode.MAINTAIN_EXPOSURE),
        (PositionState.EXPOSED, DecisionAction.ENTER, DecisionReasonCode.ENTER_APPROVED),
        (PositionState.FLAT, DecisionAction.ABSTAIN, DecisionReasonCode.PROTECTIVE_EXIT),
    ],
)
def test_constructor_rejects_illegal_state_action_and_reason(state, action, reason):
    base = evaluate_decision(
        candidate(),
        policy_version="policy:v1",
        position=PositionContext(PositionState.FLAT, "position-snapshot:flat"),
        proposed_action=DecisionAction.ABSTAIN,
        boundary=boundary(),
    )
    position = PositionContext(
        state,
        "position-snapshot:1",
        "position:1" if state is PositionState.EXPOSED else None,
    )
    with pytest.raises(DecisionError) as caught:
        replace(base, position=position, action=action, reason=DecisionReason(reason, (base.candidate_id.key,)))
    assert caught.value.incident is not None


def test_protective_candidate_must_match_exposed_position():
    protective = candidate(parent_position_id="position:expected")
    with pytest.raises(DecisionError) as caught:
        evaluate_decision(
            protective,
            policy_version="policy:v1",
            position=PositionContext(PositionState.EXPOSED, "position-snapshot:1", "position:other"),
            proposed_action=DecisionAction.HOLD,
            boundary=boundary(),
            protective_exit=True,
            exit_target=ScaledInteger(0, 8),
        )
    assert caught.value.error_code == "POSITION_REFERENCE_MISMATCH"
    assert caught.value.path == ("position", "position_id")
    assert caught.value.incident.decision_key == build_identity(
        "decision", {"candidate_id": protective.candidate_id.key, "policy_version": "policy:v1"}
    ).key


@pytest.mark.parametrize("target", [None, True, 0, 0.0, Decimal("0"), object(), ScaledInteger(-1, 8)])
def test_exit_rejects_missing_foreign_and_negative_target_with_incident(target):
    with pytest.raises(DecisionError) as caught:
        evaluate_decision(
            candidate(),
            policy_version="policy:v1",
            position=PositionContext(PositionState.EXPOSED, "position-snapshot:1", "position:1"),
            proposed_action=DecisionAction.EXIT,
            boundary=boundary(),
            exit_target=target,
        )
    assert caught.value.error_code == "INVALID_EXIT_TARGET"
    assert caught.value.path == ("exit_target",)
    assert caught.value.incident.code == "INVALID_EXIT_TARGET"


@pytest.mark.parametrize("proposal", ["ENTER", 1, True, object()])
def test_invalid_proposal_rejects_typed_with_incident(proposal):
    with pytest.raises(DecisionError) as caught:
        evaluate_decision(
            candidate(),
            policy_version="policy:v1",
            position=PositionContext(PositionState.FLAT, "position-snapshot:flat"),
            proposed_action=proposal,
            boundary=boundary(),
        )
    assert caught.value.error_code == "INVALID_DECISION_ACTION"
    assert caught.value.path == ("proposed_action",)
    assert caught.value.incident.code == "INVALID_DECISION_ACTION"


def test_reason_preserves_applicable_evidence_and_freezes_mutable_input():
    evidence = ["evidence:mutable"]
    mutable_boundary = DecisionBoundary("boundary:v1", "ref:policy-boundary", evidence)
    evidence.append("evidence:late")
    ineligible = evaluate_decision(
        candidate(executable=False),
        policy_version="policy:v1",
        position=PositionContext(PositionState.FLAT, "position-snapshot:flat"),
        proposed_action=DecisionAction.ENTER,
        boundary=mutable_boundary,
    )
    assert ineligible.reason.evidence_refs[-1] == "stale:1"
    assert mutable_boundary.evidence_refs == ("evidence:mutable",)
    vetoed = evaluate_decision(
        candidate(),
        policy_version="policy:v1",
        position=PositionContext(PositionState.FLAT, "position-snapshot:flat"),
        proposed_action=DecisionAction.ENTER,
        boundary=mutable_boundary,
        entry_veto=True,
    )
    assert vetoed.reason.evidence_refs[-2:] == ("ref:policy-boundary", "evidence:mutable")


def test_key_mismatch_has_incident_and_commit_result_rejects_forged_incident():
    position = PositionContext(PositionState.FLAT, "position-snapshot:flat")
    first = evaluate_decision(candidate(), policy_version="policy:v1", position=position,
                              proposed_action=DecisionAction.ABSTAIN, boundary=boundary())
    second = evaluate_decision(candidate(), policy_version="policy:v2", position=position,
                               proposed_action=DecisionAction.ABSTAIN, boundary=boundary())
    with pytest.raises(DecisionError) as caught:
        commit_decision(first, second)
    assert caught.value.incident.code == "DECISION_KEY_MISMATCH"
    with pytest.raises(DecisionError):
        DecisionCommitResult(
            CommitStatus.CONFLICT,
            first,
            IntegrityIncident("WRONG_CONFLICT", first.semantic_key, ("evidence:1",)),
        )


def test_decision_golden_vector_and_hundred_run_stability():
    position = PositionContext(PositionState.FLAT, "position-snapshot:flat")
    decisions = [
        evaluate_decision(candidate(), policy_version="policy:v1", position=position,
                          proposed_action=DecisionAction.ABSTAIN, boundary=boundary())
        for _ in range(100)
    ]
    expected_id = "decision:v1:3b3f2b7d506a039e0e413b43367efb0a002faed32a07c7776f3f953ac56ccc78"
    expected_bytes_sha256 = "5625dceca7568139ede15dc4912984ef98ae78abed50e2ba0a53fecc4a0aea8e"
    expected_bytes = (
        b'{"action":"ABSTAIN","boundary":{"evidence_refs":["evidence:1"],'
        b'"reference":"ref:policy-boundary","version":"boundary:v1"},'
        b'"candidate_id":"candidate:v1:40bc5d1010cd93867b9a41e79afcd685dfdc4057406fb216f180889a255e1852",'
        b'"candidate_snapshot_ref":"candidate:v1:40bc5d1010cd93867b9a41e79afcd685dfdc4057406fb216f180889a255e1852",'
        b'"causation_id":"cause:1","correlation_id":"corr:1",'
        b'"decision_id":"decision:v1:3b3f2b7d506a039e0e413b43367efb0a002faed32a07c7776f3f953ac56ccc78",'
        b'"exit_target":null,"policy_version":"policy:v1",'
        b'"position":{"position_id":null,"snapshot_ref":"position-snapshot:flat","state":"FLAT"},'
        b'"reason":{"code":"POLICY_ABSTAIN","evidence_refs":['
        b'"candidate:v1:40bc5d1010cd93867b9a41e79afcd685dfdc4057406fb216f180889a255e1852"]},'
        b'"schema_version":"canonical-decision:v1"}'
    )
    assert {item.decision_id.key for item in decisions} == {expected_id}
    assert {item.canonical_bytes() for item in decisions} == {expected_bytes}
    assert {sha256(item.canonical_bytes()).hexdigest() for item in decisions} == {expected_bytes_sha256}


def test_public_package_exports_decision_reason():
    from autotrade_next.domain import DecisionReason as PublicDecisionReason

    assert PublicDecisionReason is DecisionReason
