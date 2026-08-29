from base64 import urlsafe_b64decode, urlsafe_b64encode
from dataclasses import replace
from datetime import UTC, datetime
from hashlib import sha256
from itertools import permutations
import json

import pytest

from autotrade_next.domain.candidate import (
    CandidateEligibility, CandidateProvenance, CandidateTrigger, CandidateUse, ClockRead,
    RngRef, RuntimeManifestRef, SourceCursor, StableRef, capture_candidate,
)
from autotrade_next.domain.decision import (
    DecisionAction, DecisionBoundary, PositionContext, PositionState,
)
from autotrade_next.domain.numeric import ScaledInteger
from autotrade_next.domain.encoding import canonical_bytes
from autotrade_next.domain.policy import (
    CalibrationEvidence, CalibrationStatus, GapBehavior, GrossReturnEvidence,
    PolicyState, ShortfallComponent, ShortfallComponentEvidence,
    ShortfallEvidence, build_margin_ref, evaluate_policy_transition,
)
from autotrade_next.projections.decision_provenance import (
    CandidateProjectionPayload, DecisionProjectionPayload, DeliveryDisposition,
    DecisionProvenanceQuery, ProjectionDeliveryFailure, ProjectionError,
    ProjectionEvent, ProjectionEventType, ProjectionState, consume_projection_event,
    decide_delivery_failure, projection_event_id, projection_outbox_ref,
    projection_payload_hash,
)

NOW = datetime(2026, 8, 27, tzinfo=UTC)


def candidate(instrument="btc_idr", correlation="corr:1"):
    provenance = CandidateProvenance(
        authority_scope_id="scope:dryrun", portfolio_id="portfolio:main",
        experiment_id="experiment:1", strategy_version="strategy:v1",
        correlation_id=correlation, causation_id="cause:scan",
        ordered_input_ids=[f"input:{instrument}"], event_at_utc=NOW, received_at_utc=NOW,
        source_cursors=[SourceCursor("source:1", "venue:1", "ingest:1", "VENUE_SEQUENCE", 0, "QUALIFIED")],
        eligibility=CandidateEligibility(True), universe_ref=StableRef("universe", "version:1"),
        instrument_rules_ref=StableRef("rules", "version:1"),
        scheduler_ref=StableRef("scheduler", "version:1"),
        clock_reads=[ClockRead("clock:1", NOW)], rng_ref=RngRef("pcg64", "rng:1"),
        runtime_ref=RuntimeManifestRef("python:3.12", "numeric:v1", "env:1", "commit:1", "image:1", "lock:1"),
        data_ref=StableRef("data", "version:1"), feature_ref=StableRef("feature", "version:1"),
        model_ref=StableRef("model", "version:1"), config_ref=StableRef("config", "version:1"),
        external_response_ids=[],
    )
    return capture_candidate(
        instrument_id=instrument, horizon_id="1H", trigger_kind=CandidateTrigger.CLOSED_BAR,
        trigger_at_utc=NOW, scan_trigger_version="scan:v1", data_revision="revision:1",
        provenance=provenance,
    )


def policy_state(instrument="btc_idr", policy_version="policy:v1"):
    margin = ScaledInteger(50, 6)
    return PolicyState(
        policy_version, "boundary:v1", instrument, "1H", margin,
        build_margin_ref(policy_version, "boundary:v1", margin), 0, 0,
        None, None, False, None, None, False, 2, 1, 2,
        GapBehavior.RESET_ENTER_ONLY, "high:1", "protection:1",
    )


def transition(item=None, policy_version="policy:v1"):
    item = candidate() if item is None else item
    size = ScaledInteger(100, 6)
    gross = GrossReturnEvidence(ScaledInteger(120, 6), size, "gross:1", policy_version, "boundary:v1")
    shortfall = ShortfallEvidence(
        ScaledInteger(50, 6), size, "shortfall:1", policy_version, "boundary:v1",
        [ShortfallComponentEvidence(kind, f"cost:{kind.value.lower()}") for kind in ShortfallComponent],
    )
    calibration = CalibrationEvidence(CalibrationStatus.FRESH, "cal:1", "1H", policy_version, "boundary:v1")
    result = evaluate_policy_transition(
        item, position=PositionContext(PositionState.FLAT, "position:flat"),
        proposed_action=DecisionAction.ENTER,
        boundary=DecisionBoundary("boundary:v1", "boundary:ref", ["boundary:evidence"]),
        state=policy_state(item.instrument_id, policy_version), gross=gross, shortfall=shortfall,
        calibration=calibration, candidate_use=CandidateUse.PROJECTION_REBUILD,
    )
    return result, gross, shortfall, calibration


def event(
    event_type, seq, item=None, *, event_id=None, aggregate_seq=1,
    policy_version="policy:v1", **changes,
):
    item = candidate() if item is None else item
    if event_type is ProjectionEventType.CANDIDATE_COMMITTED:
        payload = CandidateProjectionPayload(item)
        aggregate_id = item.candidate_id.key
        causation = item.provenance.causation_id
    else:
        result, gross, shortfall, calibration = transition(item, policy_version)
        payload = DecisionProjectionPayload(result, gross, shortfall, calibration)
        aggregate_id = result.decision.decision_id.key
        causation = result.decision.causation_id
    values = dict(
        version="decision-projection-event:v1", event_type=event_type,
        authority_scope_id="scope:dryrun", journal_seq=seq,
        aggregate_id=aggregate_id, aggregate_seq=aggregate_seq,
        correlation_id=item.provenance.correlation_id, causation_id=causation,
        event_at_utc=NOW, recorded_at_utc=NOW,
        payload_hash=projection_payload_hash(payload), payload=payload,
    )
    values.update(changes)
    values["outbox_ref"] = projection_outbox_ref(**values)
    values["event_id"] = projection_event_id(**values) if event_id is None else event_id
    return ProjectionEvent(**values)


def reduce(*events):
    state = ProjectionState.empty("scope:dryrun")
    outcomes = []
    for item in events:
        outcome = consume_projection_event(state, item)
        state = outcome.state
        outcomes.append(outcome)
    return state, outcomes


def test_red_contract_module_exists_and_empty_state_is_read_only():
    state = ProjectionState.empty("scope:dryrun")
    assert state.high_water == 0
    assert state.views == ()


def test_decision_first_and_all_valid_permutations_converge_exactly():
    candidate_event = event(ProjectionEventType.CANDIDATE_COMMITTED, 1)
    decision_event = event(ProjectionEventType.DECISION_COMMITTED, 2)
    states = [reduce(*items)[0] for items in permutations((candidate_event, decision_event))]
    assert len({state.canonical_bytes() for state in states}) == 1
    assert states[0].high_water == 2
    view = states[0].views[0]
    assert view.action is decision_event.payload.transition.decision.action
    assert view.candidate_snapshot_ref == candidate_event.payload.candidate.candidate_id.key
    assert view.policy_version == "policy:v1"
    assert view.previous_policy_state == decision_event.payload.transition.prior_state
    assert view.next_policy_state == decision_event.payload.transition.next_state
    assert view.gross_evidence_ref == "gross:1"
    assert view.shortfall_evidence_ref == "shortfall:1"
    assert view.calibration_evidence_ref == "cal:1"
    assert view.shortfall_component_refs
    assert view.reason_evidence_refs == decision_event.payload.transition.decision.reason.evidence_refs
    assert view.reason == decision_event.payload.transition.decision.reason
    assert view.boundary == decision_event.payload.transition.decision.boundary
    assert view.position == decision_event.payload.transition.decision.position
    assert view.conservative_edge == decision_event.payload.transition.conservative_edge
    assert view.instrument_id == "btc_idr"
    assert view.horizon_id == "1H"
    assert view.correlation_id == "corr:1"
    assert view.causation_id == "cause:scan"
    assert view.candidate_event_at_utc == NOW
    assert view.decision_recorded_at_utc == NOW


def test_gap_buffers_without_advancing_then_drains_contiguously():
    first = event(ProjectionEventType.CANDIDATE_COMMITTED, 1)
    third = event(ProjectionEventType.DECISION_COMMITTED, 3)
    state, _ = reduce(first, third)
    assert state.high_water == 1
    assert tuple(item.journal_seq for item in state.pending_events) == (3,)
    second_item = candidate("eth_idr", "corr:2")
    second = event(ProjectionEventType.CANDIDATE_COMMITTED, 2, second_item)
    outcome = consume_projection_event(state, second)
    assert outcome.state.high_water == 3
    assert outcome.state.pending_events == ()


def test_canonical_decision_before_candidate_waits_for_link_then_converges():
    item = candidate()
    decision_first = event(ProjectionEventType.DECISION_COMMITTED, 1, item)
    candidate_second = event(ProjectionEventType.CANDIDATE_COMMITTED, 2, item)
    waiting = consume_projection_event(
        ProjectionState.empty("scope:dryrun"), decision_first
    ).state
    assert waiting.high_water == 0
    assert waiting.views == ()
    completed = consume_projection_event(waiting, candidate_second).state
    assert completed.high_water == 2
    assert len(completed.views) == 1


def test_aggregate_sequence_gap_is_rejected_before_checkpoint_advance():
    gap = event(
        ProjectionEventType.CANDIDATE_COMMITTED, 1, aggregate_seq=2
    )
    with pytest.raises(ProjectionError) as caught:
        consume_projection_event(ProjectionState.empty("scope:dryrun"), gap)
    assert caught.value.error_code == "PROJECTION_AGGREGATE_SEQUENCE_GAP"


def test_exact_duplicate_is_noop_and_conflicting_event_id_preserves_state():
    original = event(ProjectionEventType.CANDIDATE_COMMITTED, 1)
    state, _ = reduce(original)
    duplicate = consume_projection_event(state, original)
    assert duplicate.duplicate is True
    assert duplicate.state is state
    other = candidate("eth_idr", "corr:2")
    with pytest.raises(ProjectionError):
        conflicting = event(
            ProjectionEventType.CANDIDATE_COMMITTED, 2, other,
            event_id=original.event_id,
        )
        consume_projection_event(state, conflicting)
    assert state.high_water == 1


def test_same_aggregate_sequence_conflict_fails_closed():
    original = event(ProjectionEventType.CANDIDATE_COMMITTED, 1)
    state, _ = reduce(original)
    changed = event(ProjectionEventType.CANDIDATE_COMMITTED, 2)
    with pytest.raises(ProjectionError):
        consume_projection_event(state, changed)


def test_same_aggregate_sequence_conflict_is_detected_while_both_are_pending():
    later = event(ProjectionEventType.CANDIDATE_COMMITTED, 3)
    earlier = event(ProjectionEventType.CANDIDATE_COMMITTED, 2)
    state = consume_projection_event(ProjectionState.empty("scope:dryrun"), later).state
    with pytest.raises(ProjectionError) as caught:
        consume_projection_event(state, earlier)
    assert caught.value.error_code == "PROJECTION_AGGREGATE_SEQUENCE_CONFLICT"
    assert state.high_water == 0


def test_later_aggregate_sequence_cannot_replace_same_candidate_identity():
    original_candidate = candidate()
    original = event(ProjectionEventType.CANDIDATE_COMMITTED, 1, original_candidate)
    state = consume_projection_event(ProjectionState.empty("scope:dryrun"), original).state
    changed = replace(
        original_candidate,
        provenance=replace(original_candidate.provenance, correlation_id="corr:changed"),
    )
    replacement = event(
        ProjectionEventType.CANDIDATE_COMMITTED, 2, changed, aggregate_seq=2
    )
    with pytest.raises(ProjectionError) as caught:
        consume_projection_event(state, replacement)
    assert caught.value.error_code == "PROJECTION_ENTITY_CONFLICT"


def test_envelope_rejects_payload_hash_linkage_scope_and_foreign_version():
    original = event(ProjectionEventType.CANDIDATE_COMMITTED, 1)
    changes = [
        {"version": "decision-projection-event:v2"},
        {"payload_hash": "sha256:" + "0" * 64},
        {"aggregate_id": "candidate:v1:wrong"},
        {"authority_scope_id": "scope:other"},
    ]
    for change in changes:
        with pytest.raises(ProjectionError):
            replace(original, **change)


def test_trusted_outbox_and_recorded_timestamps_are_content_bound():
    original = event(ProjectionEventType.CANDIDATE_COMMITTED, 1)
    with pytest.raises(ProjectionError) as outbox:
        replace(original, outbox_ref="trusted-outbox:v1:" + "0" * 64)
    assert outbox.value.error_code == "PROJECTION_OUTBOX_REFERENCE_MISMATCH"
    later = datetime(2026, 8, 27, 0, 0, 1, tzinfo=UTC)
    with pytest.raises(ProjectionError) as timestamp:
        event(
            ProjectionEventType.CANDIDATE_COMMITTED, 1,
            event_at_utc=later, recorded_at_utc=later,
        )
    assert timestamp.value.error_code == "PROJECTION_TIMESTAMP_MISMATCH"


def test_decision_payload_rejects_semantically_unbound_evidence():
    result, gross, shortfall, calibration = transition()
    with pytest.raises(ProjectionError) as horizon:
        DecisionProjectionPayload(
            result, gross, shortfall,
            replace(calibration, horizon_id="4H"),
        )
    assert horizon.value.error_code == "PROJECTION_CALIBRATION_HORIZON_MISMATCH"
    with pytest.raises(ProjectionError) as edge:
        DecisionProjectionPayload(
            result, replace(gross, lower_bound=ScaledInteger(121, 6)),
            shortfall, calibration,
        )
    assert edge.value.error_code == "PROJECTION_CONSERVATIVE_EDGE_MISMATCH"
    with pytest.raises(ProjectionError) as evidence:
        DecisionProjectionPayload(
            result, replace(gross, distribution_ref="gross:other"),
            shortfall, calibration,
        )
    assert evidence.value.error_code == "PROJECTION_EVIDENCE_LINK_MISMATCH"


def test_candidate_decision_correlation_conflict_never_publishes_or_advances_failure():
    original_candidate = candidate()
    changed_provenance = replace(
        original_candidate.provenance, correlation_id="corr:changed"
    )
    contradictory_candidate = replace(
        original_candidate, provenance=changed_provenance
    )
    candidate_event = event(
        ProjectionEventType.CANDIDATE_COMMITTED, 1, contradictory_candidate
    )
    decision_event = event(
        ProjectionEventType.DECISION_COMMITTED, 2, original_candidate
    )
    state = consume_projection_event(
        ProjectionState.empty("scope:dryrun"), candidate_event
    ).state
    before = state.canonical_bytes()
    with pytest.raises(ProjectionError) as caught:
        consume_projection_event(state, decision_event)
    assert caught.value.error_code == "PROJECTION_CORRELATION_MISMATCH"
    assert state.canonical_bytes() == before
    assert state.high_water == 1
    assert state.views == ()


def test_query_lookup_and_stable_keyset_page_are_scope_bound():
    first_candidate = candidate()
    second_candidate = candidate("eth_idr", "corr:2")
    state, _ = reduce(
        event(ProjectionEventType.CANDIDATE_COMMITTED, 1, first_candidate),
        event(ProjectionEventType.DECISION_COMMITTED, 2, first_candidate),
        event(ProjectionEventType.CANDIDATE_COMMITTED, 3, second_candidate),
        event(ProjectionEventType.DECISION_COMMITTED, 4, second_candidate),
    )
    query = DecisionProvenanceQuery(state)
    first_page = query.list_views("scope:dryrun", page_size=1)
    assert len(first_page.items) == 1
    assert first_page.as_of_high_water == 4
    assert first_page.next_cursor is not None
    third_candidate = candidate("sol_idr", "corr:3")
    grown = consume_projection_event(
        state, event(ProjectionEventType.CANDIDATE_COMMITTED, 5, third_candidate)
    ).state
    grown = consume_projection_event(
        grown, event(ProjectionEventType.DECISION_COMMITTED, 6, third_candidate)
    ).state
    second_page = DecisionProvenanceQuery(grown).list_views(
        "scope:dryrun", page_size=1, cursor=first_page.next_cursor,
    )
    assert len(second_page.items) == 1
    assert {first_page.items[0].decision_id, second_page.items[0].decision_id} == {
        item.decision_id for item in state.views
    }
    third_decision_id = transition(third_candidate)[0].decision.decision_id.key
    assert all(item.decision_id != third_decision_id for item in second_page.items)
    assert query.get_by_decision_id("scope:dryrun", state.views[0].decision_id) is not None
    with pytest.raises(ProjectionError):
        query.list_views("scope:other", page_size=1)


def test_candidate_lookup_returns_all_policy_version_decisions_without_ambiguity():
    item = candidate()
    state, _ = reduce(
        event(ProjectionEventType.CANDIDATE_COMMITTED, 1, item),
        event(ProjectionEventType.DECISION_COMMITTED, 2, item),
        event(
            ProjectionEventType.DECISION_COMMITTED, 3, item,
            policy_version="policy:v2",
        ),
    )
    found = DecisionProvenanceQuery(state).get_by_candidate_id(
        "scope:dryrun", item.candidate_id.key
    )
    assert type(found) is tuple
    assert {view.policy_version for view in found} == {"policy:v1", "policy:v2"}


@pytest.mark.parametrize("page_size", [0, 101, True])
def test_query_rejects_invalid_page_bounds(page_size):
    with pytest.raises(ProjectionError):
        DecisionProvenanceQuery(ProjectionState.empty("scope:dryrun")).list_views(
            "scope:dryrun", page_size=page_size,
        )


def test_query_cursor_rejects_tamper_and_filter_mismatch():
    state, _ = reduce(
        event(ProjectionEventType.CANDIDATE_COMMITTED, 1),
        event(ProjectionEventType.DECISION_COMMITTED, 2),
    )
    query = DecisionProvenanceQuery(state)
    cursor = query.list_views("scope:dryrun", page_size=1).next_cursor
    assert cursor is None
    first = candidate()
    second = candidate("eth_idr", "corr:2")
    state, _ = reduce(
        event(ProjectionEventType.CANDIDATE_COMMITTED, 1, first),
        event(ProjectionEventType.DECISION_COMMITTED, 2, first),
        event(ProjectionEventType.CANDIDATE_COMMITTED, 3, second),
        event(ProjectionEventType.DECISION_COMMITTED, 4, second),
    )
    query = DecisionProvenanceQuery(state)
    cursor = query.list_views("scope:dryrun", page_size=1).next_cursor
    with pytest.raises(ProjectionError):
        query.list_views("scope:dryrun", page_size=1, cursor=cursor + "x")
    with pytest.raises(ProjectionError):
        query.list_views("scope:dryrun", page_size=1, cursor="!!!!")
    with pytest.raises(ProjectionError):
        query.list_views(
            "scope:dryrun", page_size=1, cursor=cursor, instrument_id="btc_idr"
        )
    padding = "=" * (-len(cursor) % 4)
    body = json.loads(urlsafe_b64decode(cursor + padding).decode("utf-8"))

    def forged_cursor(**changes):
        changed = dict(body)
        changed.update(changes)
        changed["checksum"] = sha256(canonical_bytes({
            key: value for key, value in changed.items() if key != "checksum"
        })).hexdigest()
        return urlsafe_b64encode(
            json.dumps(changed, sort_keys=True, separators=(",", ":")).encode("utf-8")
        ).decode("ascii").rstrip("=")

    with pytest.raises(ProjectionError) as future:
        query.list_views(
            "scope:dryrun", page_size=1, cursor=forged_cursor(as_of=99)
        )
    assert future.value.error_code == "PROJECTION_CURSOR_FUTURE_HIGH_WATER"
    with pytest.raises(ProjectionError) as version:
        query.list_views(
            "scope:dryrun", page_size=1,
            cursor=forged_cursor(version="decision-provenance-cursor:v2"),
        )
    assert version.value.error_code == "INVALID_PROJECTION_CURSOR"
    with pytest.raises(ProjectionError) as scope:
        query.list_views(
            "scope:dryrun", page_size=1,
            cursor=forged_cursor(scope="scope:other"),
        )
    assert scope.value.error_code == "PROJECTION_CURSOR_SCOPE_MISMATCH"
    with pytest.raises(ProjectionError) as negative:
        query.list_views(
            "scope:dryrun", page_size=1,
            cursor=forged_cursor(last_high_water=-1),
        )
    assert negative.value.error_code == "INVALID_PROJECTION_CURSOR"
    with pytest.raises(ProjectionError) as order:
        query.list_views(
            "scope:dryrun", page_size=1,
            cursor=forged_cursor(last_decision_id="decision:v1:missing"),
        )
    assert order.value.error_code == "PROJECTION_CURSOR_ORDER_KEY_MISMATCH"


def test_delivery_failure_retries_then_dead_letters_without_mutating_event():
    original = event(ProjectionEventType.CANDIDATE_COMMITTED, 1)
    before = original.canonical_bytes()
    retry = decide_delivery_failure(ProjectionDeliveryFailure(original, 1, 2, "QUERY_DOWN", ["error:1"]))
    exhausted = decide_delivery_failure(ProjectionDeliveryFailure(original, 2, 2, "QUERY_DOWN", ["error:1"]))
    assert retry.disposition is DeliveryDisposition.RETRY
    assert exhausted.disposition is DeliveryDisposition.DEAD_LETTER
    assert exhausted.event_id == original.event_id
    assert exhausted.event is original
    assert exhausted.max_attempts == 2
    assert original.canonical_bytes() == before


def test_public_state_constructor_rejects_duplicate_pending_sequences():
    pending = event(ProjectionEventType.CANDIDATE_COMMITTED, 2)
    state = ProjectionState.empty("scope:dryrun")
    with pytest.raises(ProjectionError):
        replace(state, pending_events=(pending, pending))


def test_projection_query_surface_has_no_mutation_methods():
    public = {name for name in dir(DecisionProvenanceQuery) if not name.startswith("_")}
    assert public == {"get_by_candidate_id", "get_by_decision_id", "list_views"}


def _golden_projection():
    state, _ = reduce(
        event(ProjectionEventType.CANDIDATE_COMMITTED, 1),
        event(ProjectionEventType.DECISION_COMMITTED, 2),
    )
    return {
        "state_sha256": sha256(state.canonical_bytes()).hexdigest(),
        "view_sha256": sha256(state.views[0].canonical_bytes()).hexdigest(),
        "high_water": state.high_water,
        "decision_id": state.views[0].decision_id,
    }


def test_projection_golden_and_hundred_run_stability():
    assert _golden_projection() == PROJECTION_GOLDEN
    assert {
        tuple(sorted(_golden_projection().items())) for _ in range(100)
    } == {tuple(sorted(PROJECTION_GOLDEN.items()))}


PROJECTION_GOLDEN = {
    "decision_id": "decision:v1:d258a72b77be0d2891ce5837a06529a1b409adec8271ceaf3d544263d077adc8",
    "high_water": 2,
    "state_sha256": "c62d93ce48ea650de99a197fb42f26bac942e736fabfca62c64e054643bb0be0",
    "view_sha256": "f6ceaf1b3849f4957fa85df7ba5c047b58a0f33a7b1d1ef29306ddabd58d8d1d",
}
