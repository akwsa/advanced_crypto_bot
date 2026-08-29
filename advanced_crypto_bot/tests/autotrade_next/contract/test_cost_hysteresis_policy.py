from dataclasses import replace
from datetime import UTC, datetime

import pytest

from autotrade_next.domain.candidate import (
    CandidateEligibility,
    CandidateProvenance,
    CandidateProvenanceV2,
    CandidateSourceV2,
    CandidateTrigger,
    ClockRead,
    EligibilityReason,
    RngRef,
    RuntimeManifestRef,
    SourceCursor,
    StableRef,
    capture_candidate,
    capture_candidate_v2,
)
from autotrade_next.domain.content import ContentRef
from autotrade_next.domain.decision import (
    DecisionAction,
    DecisionBoundary,
    DecisionError,
    DecisionReasonCode,
    PositionContext,
    PositionState,
    evaluate_decision,
)
from autotrade_next.domain.numeric import ScaledInteger
from autotrade_next.domain.market import (
    AffectedScope, EvidencePolicy, EvidenceRequirement, EvidenceRequirementSet,
    ProductFamily, ScopeKind,
)
from autotrade_next.adapters.indodax.capability_registry import INDODAX_CAPABILITY_REGISTRY
from autotrade_next.adapters.indodax.market_evidence import qualify_recorded_input
from autotrade_next.domain.policy import (
    CalibrationEvidence,
    CalibrationStatus,
    GapBehavior,
    GrossReturnEvidence,
    PolicyEvaluationError,
    PolicyState,
    PolicyTransition,
    ShortfallComponent,
    ShortfallComponentEvidence,
    ShortfallEvidence,
    build_margin_ref,
    evaluate_policy_transition,
)
from autotrade_next.projections.decision_provenance import (
    CandidateProjectionPayload,
    DecisionProjectionPayload,
)

NOW = datetime(2026, 8, 26, tzinfo=UTC)
LOGIC_TEST_REGISTRY = INDODAX_CAPABILITY_REGISTRY


def candidate(index=1, *, protective=False, executable=True, instrument_id="btc_idr", horizon_id="1H"):
    trigger = CandidateTrigger.PROTECTIVE_EVENT if protective else CandidateTrigger.CLOSED_BAR
    pair = "".join(character for character in instrument_id.casefold() if character.isalnum())
    scope = AffectedScope(
        ScopeKind.INSTRUMENT_CHANNEL, "scope:dryrun", instrument_id,
        f"market:order-book-{pair}",
    )
    evidence_policy = EvidencePolicy("market-policy:v1")
    admission = qualify_recorded_input(
        registry=LOGIC_TEST_REGISTRY,
        product=ProductFamily.MARKET_DATA_WEBSOCKET,
        resource="market:order-book-{pair}", effective_at=NOW,
        instrument_id=instrument_id, scope=scope,
        payload={
            "result": {
                "channel": f"market:order-book-{pair}",
                "data": {
                    "data": {"pair": pair, "ask": [], "bid": []},
                    "offset": index,
                },
            },
        },
        event_at_utc=NOW, received_at_utc=NOW, evaluated_at_utc=NOW,
        venue_cursor=index, ingest_cursor=f"ingest:{index}", policy=evidence_policy,
    )
    assert admission.evidence is not None
    entry = LOGIC_TEST_REGISTRY.lookup(
        ProductFamily.MARKET_DATA_WEBSOCKET, "market:order-book-{pair}", NOW
    ).entry
    assert entry is not None
    requirement = EvidenceRequirement(
        entry.capability_ref, entry.version, entry.resource,
        tuple(field.field for field in admission.evidence.authoritative_fields),
    )
    requirements = EvidenceRequirementSet.create(
        trigger=trigger.value, horizon_id=horizon_id, instrument_id=instrument_id,
        scope=scope, effective_at=NOW, requirements=(requirement,),
        policy_ref=ContentRef.v2("market.policy", "evidence-policy", evidence_policy.to_canonical_value()),
    )
    provenance = CandidateProvenanceV2(
        authority_scope_id="scope:dryrun", portfolio_id="portfolio:main",
        experiment_id="experiment:no-entry", strategy_version="strategy:v1",
        correlation_id=f"corr:{index}", causation_id=f"cause:{index}",
        ordered_input_ids=[f"input:{index}", admission.evidence.evidence_ref.key],
        event_at_utc=NOW, received_at_utc=NOW,
        sources=[CandidateSourceV2("indodax:market-ws", admission.evidence)],
        evidence_requirements=requirements,
        eligibility=(
            CandidateEligibility(True)
            if executable
            else CandidateEligibility(False, EligibilityReason.STALE, "eligibility:stale")
        ), universe_ref=StableRef("universe", "version:1"),
        instrument_rules_ref=StableRef("rules", "version:1"),
        scheduler_ref=StableRef("scheduler", "version:1"), clock_reads=[ClockRead("clock:1", NOW)],
        rng_ref=RngRef("pcg64", "state:1"),
        runtime_ref=RuntimeManifestRef("python:3.12", "numeric:v1", "env:1", "commit:1", "image:1", "lock:1"),
        data_ref=StableRef("data", "version:1"), feature_ref=StableRef("feature", "version:1"),
        model_ref=StableRef("model", "version:1"), config_ref=StableRef("config", "version:1"),
    )
    return capture_candidate_v2(
        instrument_id=instrument_id, horizon_id=horizon_id,
        trigger_kind=trigger, trigger_at_utc=NOW, scan_trigger_version=f"scan:v{index}",
        data_revision="revision:1", provenance=provenance,
        parent_position_id="position:1" if protective else None,
    )


def legacy_candidate(index=1):
    provenance = CandidateProvenance(
        authority_scope_id="scope:dryrun", portfolio_id="portfolio:main",
        experiment_id="experiment:no-entry", strategy_version="strategy:v1",
        correlation_id=f"corr:{index}", causation_id=f"cause:{index}",
        ordered_input_ids=[f"input:{index}"], event_at_utc=NOW, received_at_utc=NOW,
        source_cursors=[SourceCursor("source:1", None, f"ingest:{index}", "LOCAL_ONLY", 0, "QUALIFIED")],
        eligibility=CandidateEligibility(True), universe_ref=StableRef("universe", "version:1"),
        instrument_rules_ref=StableRef("rules", "version:1"),
        scheduler_ref=StableRef("scheduler", "version:1"), clock_reads=[ClockRead("clock:1", NOW)],
        rng_ref=RngRef("pcg64", "state:1"),
        runtime_ref=RuntimeManifestRef("python:3.12", "numeric:v1", "env:1", "commit:1", "image:1", "lock:1"),
        data_ref=StableRef("data", "version:1"), feature_ref=StableRef("feature", "version:1"),
        model_ref=StableRef("model", "version:1"), config_ref=StableRef("config", "version:1"),
        external_response_ids=[],
    )
    return capture_candidate(
        instrument_id="btc_idr", horizon_id="1H",
        trigger_kind=CandidateTrigger.CLOSED_BAR,
        trigger_at_utc=NOW, scan_trigger_version=f"scan:v{index}", data_revision="revision:1",
        provenance=provenance,
    )


def boundary():
    return DecisionBoundary("boundary:v1", "boundary-ref:1", ["boundary-evidence:1"])


def state(**changes):
    margin = changes.get("required_margin", ScaledInteger(50, 6))
    policy_version = changes.get("policy_version", "policy:v1")
    boundary_version = changes.get("boundary_version", "boundary:v1")
    values = dict(
        policy_version=policy_version, boundary_version=boundary_version,
        instrument_id="btc_idr", horizon_id="1H",
        required_margin=margin,
        margin_ref=build_margin_ref(policy_version, boundary_version, margin),
        enter_confirmations=0, alpha_exit_confirmations=0,
        last_enter_candidate_ref=None, last_enter_input_ref=None,
        last_enter_completed=False,
        last_alpha_exit_candidate_ref=None, last_alpha_exit_input_ref=None,
        last_alpha_exit_completed=False,
        enter_required=2, protective_exit_required=1, alpha_exit_required=2,
        gap_behavior=GapBehavior.RESET_ENTER_ONLY,
        high_water_ref="high-water:1", protection_ref="protection:1",
    )
    values.update(changes)
    if values["enter_confirmations"] and values["last_enter_candidate_ref"] is None:
        values["last_enter_candidate_ref"] = "candidate:previous-enter"
        values["last_enter_input_ref"] = "policy-input:previous-enter"
    if values["alpha_exit_confirmations"] and values["last_alpha_exit_candidate_ref"] is None:
        values["last_alpha_exit_candidate_ref"] = "candidate:previous-exit"
        values["last_alpha_exit_input_ref"] = "policy-input:previous-exit"
    return PolicyState(**values)


def components():
    return [ShortfallComponentEvidence(item, f"cost:{item.value.lower()}") for item in ShortfallComponent]


def cost_inputs(*, gross=120, cost=50, status=CalibrationStatus.FRESH):
    requested_size = ScaledInteger(100, 6)
    return dict(
        gross=GrossReturnEvidence(
            ScaledInteger(gross, 6), requested_size, "gross-distribution:1",
            "policy:v1", "boundary:v1",
        ),
        shortfall=ShortfallEvidence(
            ScaledInteger(cost, 6), requested_size, "shortfall-distribution:1",
            "policy:v1", "boundary:v1", components(),
        ),
        calibration=CalibrationEvidence(
            status, "calibration:1", "1H", "policy:v1", "boundary:v1"
        ),
    )


def evaluate(flat_candidate, policy_state, **changes):
    inputs = cost_inputs()
    inputs.update(changes)
    return evaluate_policy_transition(
        flat_candidate,
        position=PositionContext(PositionState.FLAT, "position-snapshot:flat"),
        proposed_action=DecisionAction.ENTER,
        boundary=boundary(), state=policy_state, **inputs,
    )


@pytest.mark.parametrize("gross,expected_reason", [
    (100, DecisionReasonCode.COST_MARGIN_NOT_MET),
    (101, DecisionReasonCode.ENTER_CONFIRMATION_PENDING),
])
def test_edge_must_strictly_exceed_margin(gross, expected_reason):
    result = evaluate(candidate(), state(), **cost_inputs(gross=gross, cost=50))
    assert result.decision.action is DecisionAction.ABSTAIN
    assert result.decision.reason.code is expected_reason


@pytest.mark.parametrize("calibration,reason", [
    (None, DecisionReasonCode.CALIBRATION_MISSING),
    (CalibrationEvidence(CalibrationStatus.STALE, "calibration:stale", "1H", "policy:v1", "boundary:v1"),
     DecisionReasonCode.CALIBRATION_STALE),
])
def test_missing_or_stale_calibration_abstains(calibration, reason):
    result = evaluate(candidate(), state(), calibration=calibration)
    assert result.decision.action is DecisionAction.ABSTAIN
    assert result.decision.reason.code is reason


def test_enter_requires_two_consecutive_confirmations_and_duplicate_is_idempotent():
    first = evaluate(candidate(1), state())
    duplicate = evaluate(candidate(1), first.next_state)
    second = evaluate(candidate(2), duplicate.next_state)
    assert first.decision.action is DecisionAction.ABSTAIN
    assert duplicate.next_state == first.next_state
    assert second.decision.action is DecisionAction.ENTER
    assert second.next_state.enter_confirmations == 0


def test_failed_edge_and_gap_reset_enter_only_and_preserve_protection():
    first = evaluate(candidate(1), state(alpha_exit_confirmations=1))
    failed = evaluate(candidate(2), first.next_state, **cost_inputs(gross=99))
    again = evaluate(candidate(3), failed.next_state)
    gap = evaluate(candidate(4), again.next_state, data_gap=True)
    assert failed.next_state.enter_confirmations == 0
    assert gap.next_state.enter_confirmations == 0
    assert gap.next_state.alpha_exit_confirmations == 1
    assert (gap.next_state.high_water_ref, gap.next_state.protection_ref) == ("high-water:1", "protection:1")


def test_alpha_exit_requires_two_confirmations():
    exposed = PositionContext(PositionState.EXPOSED, "position-snapshot:1", "position:1")
    first = evaluate_policy_transition(
        candidate(1), position=exposed, proposed_action=DecisionAction.EXIT,
        boundary=boundary(), state=state(), exit_target=ScaledInteger(0, 8),
    )
    second = evaluate_policy_transition(
        candidate(2), position=exposed, proposed_action=DecisionAction.EXIT,
        boundary=boundary(), state=first.next_state, exit_target=ScaledInteger(0, 8),
    )
    assert (first.decision.action, first.decision.reason.code) == (
        DecisionAction.HOLD, DecisionReasonCode.ALPHA_EXIT_CONFIRMATION_PENDING)
    assert second.decision.action is DecisionAction.EXIT


def test_gap_and_duplicate_do_not_advance_alpha_exit_confirmation():
    exposed = PositionContext(PositionState.EXPOSED, "position-snapshot:1", "position:1")
    first = evaluate_policy_transition(
        candidate(1), position=exposed, proposed_action=DecisionAction.EXIT,
        boundary=boundary(), state=state(), exit_target=ScaledInteger(0, 8),
    )
    duplicate = evaluate_policy_transition(
        candidate(1), position=exposed, proposed_action=DecisionAction.EXIT,
        boundary=boundary(), state=first.next_state, exit_target=ScaledInteger(0, 8),
    )
    gap = evaluate_policy_transition(
        candidate(2), position=exposed, proposed_action=DecisionAction.EXIT,
        boundary=boundary(), state=duplicate.next_state, data_gap=True,
        exit_target=ScaledInteger(0, 8),
    )
    assert duplicate.next_state == first.next_state
    assert gap.decision.action is DecisionAction.HOLD
    assert gap.next_state == first.next_state


@pytest.mark.parametrize("status", [None, CalibrationStatus.STALE])
def test_protective_exit_is_immediate_under_gap_and_bad_calibration(status):
    calibration = None if status is None else CalibrationEvidence(
        status, "calibration:stale", "1H", "policy:v1", "boundary:v1"
    )
    result = evaluate_policy_transition(
        candidate(1, protective=True),
        position=PositionContext(PositionState.EXPOSED, "position-snapshot:1", "position:1"),
        proposed_action=DecisionAction.HOLD, boundary=boundary(), state=state(),
        calibration=calibration, data_gap=True, protective_exit=True,
        exit_target=ScaledInteger(0, 8),
    )
    assert (result.decision.action, result.decision.reason.code) == (
        DecisionAction.EXIT, DecisionReasonCode.PROTECTIVE_EXIT)
    assert result.next_state.high_water_ref == "high-water:1"


def test_complete_shortfall_taxonomy_scale_size_and_version_fail_closed():
    missing = components()[:-1]
    constructors = [
        lambda: dict(shortfall=ShortfallEvidence(ScaledInteger(50, 6), ScaledInteger(1, 6), "shortfall:1", "policy:v1", "boundary:v1", missing)),
        lambda: dict(shortfall=ShortfallEvidence(ScaledInteger(50, 5), ScaledInteger(1, 6), "shortfall:1", "policy:v1", "boundary:v1", components())),
        lambda: dict(shortfall=ShortfallEvidence(ScaledInteger(50, 6), ScaledInteger(0, 6), "shortfall:1", "policy:v1", "boundary:v1", components())),
        lambda: dict(state=state(boundary_version="boundary:other")),
    ]
    for construct in constructors:
        with pytest.raises(PolicyEvaluationError) as caught:
            overrides = construct()
            evaluate(candidate(), overrides.pop("state", state()), **overrides)
        assert caught.value.partial_transition is None


def test_state_and_transition_are_canonical_immutable_and_repeatable():
    original = state()
    results = [evaluate(candidate(1), original) for _ in range(100)]
    assert len({item.canonical_bytes() for item in results}) == 1
    assert original.enter_confirmations == 0
    assert all(item.prior_state is original for item in results)


def test_completed_enter_duplicate_replays_identical_decision_and_input_drift_rejects():
    first = evaluate(candidate(1), state())
    completed = evaluate(candidate(2), first.next_state)
    duplicate = evaluate(candidate(2), completed.next_state)
    assert duplicate.decision.action is DecisionAction.ENTER
    assert duplicate.decision.canonical_bytes() == completed.decision.canonical_bytes()
    assert duplicate.next_state == completed.next_state
    with pytest.raises(PolicyEvaluationError) as caught:
        evaluate(candidate(2), completed.next_state, **cost_inputs(gross=121))
    assert caught.value.error_code == "DUPLICATE_POLICY_INPUT_MISMATCH"


def test_completed_alpha_exit_duplicate_replays_identical_decision():
    exposed = PositionContext(PositionState.EXPOSED, "position-snapshot:1", "position:1")
    first = evaluate_policy_transition(
        candidate(1), position=exposed, proposed_action=DecisionAction.EXIT,
        boundary=boundary(), state=state(), exit_target=ScaledInteger(0, 8),
    )
    completed = evaluate_policy_transition(
        candidate(2), position=exposed, proposed_action=DecisionAction.EXIT,
        boundary=boundary(), state=first.next_state, exit_target=ScaledInteger(0, 8),
    )
    duplicate = evaluate_policy_transition(
        candidate(2), position=exposed, proposed_action=DecisionAction.EXIT,
        boundary=boundary(), state=completed.next_state, exit_target=ScaledInteger(0, 8),
    )
    assert duplicate.decision.action is DecisionAction.EXIT
    assert duplicate.decision.canonical_bytes() == completed.decision.canonical_bytes()


def test_ineligible_candidate_never_advances_confirmation():
    rejected = evaluate(candidate(1, executable=False), state())
    eligible = evaluate(candidate(2), rejected.next_state)
    assert rejected.decision.reason.code is DecisionReasonCode.CANDIDATE_INELIGIBLE
    assert rejected.next_state.enter_confirmations == 0
    assert eligible.decision.action is DecisionAction.ABSTAIN
    assert eligible.next_state.enter_confirmations == 1


def test_v1_executable_self_claim_is_rejected_before_confirmation_state_changes():
    original = state(enter_confirmations=1)
    rejected = evaluate(legacy_candidate(), original)
    assert rejected.decision.action is DecisionAction.ABSTAIN
    assert rejected.decision.reason.code is DecisionReasonCode.CANDIDATE_INELIGIBLE
    assert rejected.next_state.enter_confirmations == 0


def test_v2_candidate_policy_decision_projection_contract_end_to_end():
    first_inputs = cost_inputs()
    first = evaluate_policy_transition(
        candidate(1), position=PositionContext(PositionState.FLAT, "position-snapshot:flat"),
        proposed_action=DecisionAction.ENTER, boundary=boundary(), state=state(), **first_inputs,
    )
    second_candidate = candidate(2)
    second_inputs = cost_inputs()
    second = evaluate_policy_transition(
        second_candidate, position=PositionContext(PositionState.FLAT, "position-snapshot:flat"),
        proposed_action=DecisionAction.ENTER, boundary=boundary(), state=first.next_state, **second_inputs,
    )
    candidate_payload = CandidateProjectionPayload(second_candidate)
    decision_payload = DecisionProjectionPayload(second, **second_inputs)
    source_evidence = second_candidate.provenance.sources[0].evidence
    assert source_evidence.disposition.value == "QUALIFIED"
    assert source_evidence.venue_cursor == "2"
    assert source_evidence.ingest_cursor == "ingest:2"
    assert tuple(field.field for field in source_evidence.authoritative_fields) == (
        "result.channel",
        "result.data.data.ask",
        "result.data.data.bid",
        "result.data.data.pair",
        "result.data.offset",
    )
    assert second.decision.action is DecisionAction.ENTER
    assert candidate_payload.candidate.provenance_version == "v2"
    assert decision_payload.transition.decision.candidate_id == second_candidate.candidate_id
    assert candidate_payload.candidate.canonical_bytes() == second_candidate.canonical_bytes()
    assert decision_payload.transition.canonical_bytes() == second.canonical_bytes()


@pytest.mark.parametrize(
    "changes",
    [
        {"enter_required": 1},
        {"protective_exit_required": 2},
        {"alpha_exit_required": 1},
        {"margin_ref": "forged-margin:1"},
    ],
)
def test_baseline_confirmation_and_content_addressed_margin_are_locked(changes):
    with pytest.raises(PolicyEvaluationError):
        state(**changes)


def test_shortfall_component_permutation_is_canonical():
    ordered = components()
    left = ShortfallEvidence(
        ScaledInteger(50, 6), ScaledInteger(100, 6), "shortfall:1",
        "policy:v1", "boundary:v1", ordered,
    )
    right = ShortfallEvidence(
        ScaledInteger(50, 6), ScaledInteger(100, 6), "shortfall:1",
        "policy:v1", "boundary:v1", list(reversed(ordered)),
    )
    assert left.to_canonical_value() == right.to_canonical_value()


@pytest.mark.parametrize(
    "override,error_code",
    [
        ({"gross": GrossReturnEvidence(ScaledInteger(120, 6), ScaledInteger(101, 6),
                                       "gross:1", "policy:v1", "boundary:v1")},
         "REQUESTED_SIZE_MISMATCH"),
        ({"gross": GrossReturnEvidence(ScaledInteger(120, 6), ScaledInteger(100, 6),
                                       "gross:1", "policy:foreign", "boundary:v1")},
         "POLICY_VERSION_MISMATCH"),
        ({"shortfall": ShortfallEvidence(ScaledInteger(50, 6), ScaledInteger(100, 5),
                                         "shortfall:1", "policy:v1", "boundary:v1", components())},
         "REQUESTED_SIZE_MISMATCH"),
    ],
)
def test_requested_size_scale_and_evidence_version_drift_reject(override, error_code):
    with pytest.raises(PolicyEvaluationError) as caught:
        evaluate(candidate(), state(), **override)
    assert caught.value.error_code == error_code


@pytest.mark.parametrize(
    "scope",
    [
        {"instrument_id": "eth_idr"},
        {"horizon_id": "4H"},
    ],
)
def test_confirmation_state_cannot_cross_instrument_or_horizon(scope):
    with pytest.raises(PolicyEvaluationError) as caught:
        evaluate(candidate(**scope), state())
    assert caught.value.error_code == "POLICY_SCOPE_MISMATCH"


def test_edge_overflow_and_transition_invariant_fail_typed():
    huge = 1 << 2047
    gross = GrossReturnEvidence(
        ScaledInteger(-huge, 6), ScaledInteger(100, 6), "gross:huge",
        "policy:v1", "boundary:v1",
    )
    shortfall = ShortfallEvidence(
        ScaledInteger(huge, 6), ScaledInteger(100, 6), "shortfall:huge",
        "policy:v1", "boundary:v1", components(),
    )
    with pytest.raises(PolicyEvaluationError) as caught:
        evaluate(candidate(), state(), gross=gross, shortfall=shortfall)
    assert caught.value.error_code == "INVALID_POLICY_NUMERIC"

    valid = evaluate(candidate(), state())
    with pytest.raises(PolicyEvaluationError) as invariant:
        PolicyTransition(
            valid.prior_state,
            replace(valid.next_state, high_water_ref="high-water:forged"),
            valid.conservative_edge,
            valid.decision,
        )
    assert invariant.value.error_code == "POLICY_STATE_INVARIANT_CHANGED"


def test_closed_bar_cannot_claim_protective_precedence():
    with pytest.raises(PolicyEvaluationError) as caught:
        evaluate_policy_transition(
            candidate(),
            position=PositionContext(PositionState.EXPOSED, "position-snapshot:1", "position:1"),
            proposed_action=DecisionAction.HOLD,
            boundary=boundary(), state=state(), protective_exit=True,
            exit_target=ScaledInteger(0, 8),
        )
    assert caught.value.error_code == "INVALID_PROTECTIVE_TRIGGER"


def test_policy_reason_override_requires_policy_evidence():
    with pytest.raises(DecisionError) as caught:
        evaluate_decision(
            candidate(), policy_version="policy:v1",
            position=PositionContext(PositionState.FLAT, "position-snapshot:flat"),
            proposed_action=DecisionAction.ABSTAIN, boundary=boundary(),
            reason_override=DecisionReasonCode.COST_MARGIN_NOT_MET,
        )
    assert caught.value.error_code == "INVALID_DECISION_REASON"
