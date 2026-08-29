from dataclasses import replace
from datetime import UTC, datetime
from hashlib import sha256
import json
import os
from pathlib import Path
import subprocess
import sys

import pytest

from autotrade_next.domain.candidate import (
    CandidateEligibility, CandidateProvenance, CandidateTrigger, ClockRead,
    RngRef, RuntimeManifestRef, SourceCursor, StableRef, capture_candidate,
)
from autotrade_next.domain.decision import (
    DecisionAction, DecisionBoundary, PositionContext, PositionState,
)
from autotrade_next.domain.numeric import ScaledInteger
from autotrade_next.domain.policy import (
    CalibrationEvidence, CalibrationStatus, GapBehavior, GrossReturnEvidence,
    PolicyState, ShortfallComponent, ShortfallComponentEvidence,
    ShortfallEvidence, build_margin_ref,
)
from autotrade_next.domain.replay import (
    DecisionReplayBundle, ReplayError, ReplayManifest, ReplayMode,
    ReplayComparison, ReplayObservability, SemanticDiff, SemanticProjectionProfile,
    compare_replay_results,
    clock_read_ref, policy_state_ref, regenerate_replay, semantic_hash,
    source_cursor_ref, stable_ref_key,
)

NOW = datetime(2026, 8, 27, tzinfo=UTC)


def candidate():
    provenance = CandidateProvenance(
        authority_scope_id="scope:dryrun", portfolio_id="portfolio:main",
        experiment_id="experiment:replay", strategy_version="strategy:v1",
        correlation_id="corr:replay", causation_id="cause:replay",
        ordered_input_ids=["input:1", "input:2"], event_at_utc=NOW, received_at_utc=NOW,
        source_cursors=[SourceCursor("source:1", "venue:1", "ingest:1", "VENUE_SEQUENCE", 0, "QUALIFIED")],
        eligibility=CandidateEligibility(True), universe_ref=StableRef("universe", "version:1"),
        instrument_rules_ref=StableRef("rules", "version:1"),
        scheduler_ref=StableRef("scheduler", "version:1"), clock_reads=[ClockRead("clock:1", NOW)],
        rng_ref=RngRef("pcg64", "rng-state:1"),
        runtime_ref=RuntimeManifestRef("python:3.12", "numeric:v1", "env:1", "commit:1", "image:1", "lock:1"),
        data_ref=StableRef("data", "version:1"), feature_ref=StableRef("feature", "version:1"),
        model_ref=StableRef("model", "version:1"), config_ref=StableRef("config", "version:1"),
        external_response_ids=["external:1"],
    )
    return capture_candidate(
        instrument_id="btc_idr", horizon_id="1H", trigger_kind=CandidateTrigger.CLOSED_BAR,
        trigger_at_utc=NOW, scan_trigger_version="scan:v1", data_revision="revision:1",
        provenance=provenance,
    )


def manifest(*, candidate_value=None, state_value=None, position_value=None, **changes):
    candidate_value = candidate() if candidate_value is None else candidate_value
    state_value = policy_state() if state_value is None else state_value
    position_value = (
        PositionContext(PositionState.FLAT, "position-snapshot:flat")
        if position_value is None else position_value
    )
    provenance = candidate_value.provenance
    values = dict(
        version="replay-manifest:v1", ordered_input_ids=["input:1", "input:2"],
        market_snapshot_ref=stable_ref_key(provenance.data_ref),
        universe_ref=stable_ref_key(provenance.universe_ref),
        initial_portfolio_state_ref=position_value.snapshot_ref,
        initial_risk_state_ref=policy_state_ref(state_value),
        cursor_refs=[source_cursor_ref(item) for item in provenance.source_cursors],
        fee_rules_ref="fees:1",
        instrument_rules_ref=stable_ref_key(provenance.instrument_rules_ref),
        strategy_ref=provenance.strategy_version,
        model_ref=stable_ref_key(provenance.model_ref),
        calibrator_ref="calibrator:v1", simulator_ref="simulator:v1", cost_model_ref="cost:v1",
        config_ref=stable_ref_key(provenance.config_ref), schema_ref="schema:v1",
        code_commit_ref=provenance.runtime_ref.code_commit,
        image_digest_ref=provenance.runtime_ref.image_digest,
        dependency_lock_ref=provenance.runtime_ref.dependency_lock_ref,
        runtime_numeric_ref=provenance.runtime_ref.numeric_version,
        rng_algorithm=provenance.rng_ref.algorithm, rng_state_ref=provenance.rng_ref.state_ref,
        clock_refs=[clock_read_ref(item) for item in provenance.clock_reads],
        external_response_refs=["external:1"],
    )
    values.update(changes)
    return ReplayManifest(**values)


def policy_state(**changes):
    margin = ScaledInteger(50, 6)
    values = dict(
        policy_version="policy:v1", boundary_version="boundary:v1",
        instrument_id="btc_idr", horizon_id="1H", required_margin=margin,
        margin_ref=build_margin_ref("policy:v1", "boundary:v1", margin),
        enter_confirmations=0, alpha_exit_confirmations=0,
        last_enter_candidate_ref=None, last_enter_input_ref=None, last_enter_completed=False,
        last_alpha_exit_candidate_ref=None, last_alpha_exit_input_ref=None, last_alpha_exit_completed=False,
        enter_required=2, protective_exit_required=1, alpha_exit_required=2,
        gap_behavior=GapBehavior.RESET_ENTER_ONLY,
        high_water_ref="high-water:1", protection_ref="protection:1",
    )
    values.update(changes)
    return PolicyState(**values)


def cost_inputs():
    size = ScaledInteger(100, 6)
    components = [
        ShortfallComponentEvidence(item, f"cost:{item.value.lower()}")
        for item in ShortfallComponent
    ]
    return dict(
        gross=GrossReturnEvidence(ScaledInteger(120, 6), size, "gross:1", "policy:v1", "boundary:v1"),
        shortfall=ShortfallEvidence(ScaledInteger(50, 6), size, "shortfall:1", "policy:v1", "boundary:v1", components),
        calibration=CalibrationEvidence(CalibrationStatus.FRESH, "calibration:1", "1H", "policy:v1", "boundary:v1"),
    )


def bundle(**changes):
    candidate_value = changes.get("candidate", candidate())
    state_value = changes.get("initial_policy_state", policy_state())
    position_value = changes.get(
        "position", PositionContext(PositionState.FLAT, "position-snapshot:flat")
    )
    values = dict(
        version="decision-replay-bundle:v1",
        manifest=manifest(
            candidate_value=candidate_value,
            state_value=state_value,
            position_value=position_value,
        ),
        candidate=candidate_value, initial_policy_state=state_value,
        position=position_value,
        proposed_action=DecisionAction.ENTER,
        boundary=DecisionBoundary("boundary:v1", "boundary-ref:1", ["boundary-evidence:1"]),
        data_gap=False, protective_exit=False, exit_target=None,
        **cost_inputs(),
    )
    values.update(changes)
    return DecisionReplayBundle(**values)


def observation(run="run:1", trace="trace:1"):
    return ReplayObservability(run, trace)


def profile(*excluded):
    return SemanticProjectionProfile("replay-semantic:v1", excluded)


def test_manifest_freezes_lists_and_is_content_addressed():
    ordered = ["input:1", "input:2"]
    item = manifest(ordered_input_ids=ordered)
    before = item.canonical_bytes()
    ordered.append("input:late")
    assert item.ordered_input_ids == ("input:1", "input:2")
    assert item.canonical_bytes() == before
    assert item.manifest_ref.startswith("replay-manifest:v1:")


@pytest.mark.parametrize("changes,code", [
    ({"version": "replay-manifest:v2"}, "UNSUPPORTED_REPLAY_MANIFEST_VERSION"),
    ({"ordered_input_ids": ["input:1", "input:1"]}, "DUPLICATE_REPLAY_REFERENCE"),
    ({"clock_refs": []}, "MISSING_REPLAY_REFERENCE"),
    ({"external_response_refs": ["external:1", "external:1"]}, "DUPLICATE_REPLAY_REFERENCE"),
])
def test_manifest_invalid_versions_missing_and_duplicates_fail_typed(changes, code):
    with pytest.raises(ReplayError) as caught:
        manifest(**changes)
    assert caught.value.error_code == code
    assert caught.value.partial_result is None


def test_bundle_rejects_ordered_input_scope_and_boundary_mismatch():
    cases = [
        {"manifest": manifest(ordered_input_ids=["input:2", "input:1"])},
        {"initial_policy_state": policy_state(horizon_id="4H")},
        {"boundary": DecisionBoundary("boundary:other", "boundary-ref:other", [])},
    ]
    for changes in cases:
        with pytest.raises(ReplayError):
            bundle(**changes)


@pytest.mark.parametrize("field,value", [
    ("market_snapshot_ref", "data:changed"),
    ("universe_ref", "universe:changed"),
    ("initial_portfolio_state_ref", "position:changed"),
    ("initial_risk_state_ref", "policy-state:v1:" + "0" * 64),
    ("cursor_refs", ["source-cursor:v1:" + "0" * 64]),
    ("instrument_rules_ref", "rules:changed"),
    ("strategy_ref", "strategy:changed"),
    ("model_ref", "model:changed"),
    ("config_ref", "config:changed"),
    ("code_commit_ref", "commit:changed"),
    ("image_digest_ref", "image:changed"),
    ("dependency_lock_ref", "lock:changed"),
    ("runtime_numeric_ref", "numeric:changed"),
    ("rng_algorithm", "rng:changed"),
    ("rng_state_ref", "rng-state:changed"),
    ("clock_refs", ["clock-read:v1:" + "0" * 64]),
    ("external_response_refs", ["external:changed"]),
])
def test_bundle_rejects_every_candidate_or_state_bound_manifest_mismatch(field, value):
    with pytest.raises(ReplayError) as caught:
        bundle(manifest=manifest(**{field: value}))
    assert caught.value.error_code in {
        "REPLAY_MANIFEST_MISMATCH", "REPLAY_ORDERED_INPUT_MISMATCH"
    }


def test_complete_clock_and_cursor_records_are_manifest_bound():
    original = candidate()
    changed_clock = replace(
        original.provenance,
        clock_reads=[ClockRead("clock:1", datetime(2026, 8, 27, 0, 0, 1, tzinfo=UTC))],
    )
    changed_cursor = replace(
        original.provenance,
        source_cursors=[SourceCursor(
            "source:1", "venue:2", "ingest:1", "VENUE_SEQUENCE", 0, "QUALIFIED"
        )],
    )
    for provenance in (changed_clock, changed_cursor):
        changed = replace(original, provenance=provenance)
        with pytest.raises(ReplayError) as caught:
            bundle(candidate=changed, manifest=manifest())
        assert caught.value.error_code == "REPLAY_MANIFEST_MISMATCH"


@pytest.mark.parametrize("name,evidence", [
    ("gross", GrossReturnEvidence(
        ScaledInteger(120, 6), ScaledInteger(100, 6), "gross:1",
        "policy:other", "boundary:v1",
    )),
    ("shortfall", ShortfallEvidence(
        ScaledInteger(50, 6), ScaledInteger(100, 6), "shortfall:1",
        "policy:v1", "boundary:other",
        [ShortfallComponentEvidence(item, f"cost:{item.value.lower()}")
         for item in ShortfallComponent],
    )),
])
def test_bundle_rejects_evidence_versions_before_regeneration(name, evidence):
    with pytest.raises(ReplayError):
        bundle(**{name: evidence})


def test_bundle_rejects_wrong_exit_target_type_and_protective_trigger():
    with pytest.raises(ReplayError) as target:
        bundle(exit_target="100")
    assert target.value.path == ("bundle", "exit_target")
    with pytest.raises(ReplayError) as protective:
        bundle(protective_exit=True)
    assert protective.value.error_code == "REPLAY_PROTECTIVE_MISMATCH"


def test_regeneration_wraps_policy_or_decision_rejection_as_replay_error():
    invalid_calibration = CalibrationEvidence(
        CalibrationStatus.FRESH, "calibration:1", "4H", "policy:v1", "boundary:v1"
    )
    replay_bundle = bundle(calibration=invalid_calibration)
    with pytest.raises(ReplayError) as caught:
        regenerate_replay(
            replay_bundle, ReplayMode.DECISION_LIFECYCLE_REGENERATION, observation()
        )
    assert caught.value.error_code == "REPLAY_REGENERATION_REJECTED"
    assert isinstance(caught.value.__cause__, Exception)


def test_hundred_regenerations_have_exact_transition_bytes_hash_and_zero_external_calls():
    frozen = bundle()
    before = frozen.canonical_bytes()
    results = [regenerate_replay(frozen, ReplayMode.DECISION_LIFECYCLE_REGENERATION, observation()) for _ in range(100)]
    assert len({item.transition.canonical_bytes() for item in results}) == 1
    assert len({semantic_hash(item, profile()) for item in results}) == 1
    assert {item.external_call_count for item in results} == {0}
    assert frozen.canonical_bytes() == before


@pytest.mark.parametrize("mode", [ReplayMode.CANONICAL_STATE_REHYDRATION, ReplayMode.PROJECTION_REBUILD])
def test_unavailable_replay_modes_reject_instead_of_simulating_store(mode):
    with pytest.raises(ReplayError) as caught:
        regenerate_replay(bundle(), mode, observation())
    assert caught.value.error_code == "UNSUPPORTED_REPLAY_MODE"


def test_explicit_observability_exclusions_match_but_default_comparison_diffs():
    expected = regenerate_replay(bundle(), ReplayMode.DECISION_LIFECYCLE_REGENERATION, observation("run:1", "trace:1"))
    actual = regenerate_replay(bundle(), ReplayMode.DECISION_LIFECYCLE_REGENERATION, observation("run:2", "trace:2"))
    strict = compare_replay_results(expected, actual, profile())
    relaxed = compare_replay_results(
        expected, actual, profile("observability.run_ref", "observability.trace_ref")
    )
    assert not strict.matches
    assert [item.path for item in strict.diffs] == [
        ("observability", "run_ref"), ("observability", "trace_ref")]
    assert relaxed.matches
    assert relaxed.expected_hash == relaxed.actual_hash


@pytest.mark.parametrize("excluded", [
    "transition.decision.action", "transition.next_state", "observability.unknown",
])
def test_semantic_or_unknown_exclusion_is_rejected(excluded):
    with pytest.raises(ReplayError) as caught:
        profile(excluded)
    assert caught.value.error_code == "FORBIDDEN_SEMANTIC_EXCLUSION"


def test_semantic_change_reports_exact_ordered_diff_without_tolerance():
    expected = regenerate_replay(bundle(), ReplayMode.DECISION_LIFECYCLE_REGENERATION, observation())
    changed_bundle = bundle(initial_policy_state=policy_state(high_water_ref="high-water:changed"))
    actual = regenerate_replay(changed_bundle, ReplayMode.DECISION_LIFECYCLE_REGENERATION, observation())
    comparison = compare_replay_results(expected, actual, profile())
    assert not comparison.matches
    paths = [item.path for item in comparison.diffs]
    assert paths == sorted(paths)
    assert ("transition", "next_state", "high_water_ref") in paths
    assert comparison.expected_hash != comparison.actual_hash


def test_foreign_mode_profile_and_observability_types_fail_typed():
    with pytest.raises(ReplayError):
        regenerate_replay(bundle(), "DECISION_LIFECYCLE_REGENERATION", observation())
    with pytest.raises(ReplayError):
        SemanticProjectionProfile("replay-semantic:v2", ())
    with pytest.raises(ReplayError):
        ReplayObservability("run:1", 1)


def test_comparison_and_diff_public_contracts_reject_forged_values():
    valid_hash = "replay-semantic:v1:" + "0" * 64
    with pytest.raises(ReplayError):
        ReplayComparison(True, "replay-semantic:v2", valid_hash, valid_hash, ())
    with pytest.raises(ReplayError):
        ReplayComparison(False, "replay-semantic:v1", "bad", valid_hash, ())
    with pytest.raises(ReplayError):
        ReplayComparison(False, "replay-semantic:v1", valid_hash, valid_hash, ("bad",))
    with pytest.raises(ReplayError):
        SemanticDiff((object(),), None, None)


def test_missing_mapping_key_is_distinct_from_present_none_in_diff_evidence():
    missing = SemanticDiff(("field",), None, None, False, True)
    present = SemanticDiff(("field",), None, "changed", True, True)
    assert missing.to_canonical_value()["expected_present"] is False
    assert present.to_canonical_value()["expected_present"] is True


def _golden_values():
    replay_bundle = bundle()
    result = regenerate_replay(
        replay_bundle, ReplayMode.DECISION_LIFECYCLE_REGENERATION, observation()
    )
    return {
        "bundle_sha256": sha256(replay_bundle.canonical_bytes()).hexdigest(),
        "transition_sha256": sha256(result.transition.canonical_bytes()).hexdigest(),
        "semantic_hash": semantic_hash(result, profile()),
        "manifest_ref": replay_bundle.manifest.manifest_ref,
        "decision_id": result.transition.decision.decision_id.key,
    }


def test_replay_golden_vector_is_stable_across_fresh_hash_seeded_processes():
    expected = _golden_values()
    assert expected == REPLAY_GOLDEN_VECTOR
    test_path = Path(__file__).resolve()
    script = (
        "import json,runpy; n=runpy.run_path(" + repr(str(test_path)) + "); "
        "print(json.dumps(n['_golden_values'](),sort_keys=True))"
    )
    for seed in ("1", "8675309"):
        environment = dict(os.environ, PYTHONHASHSEED=seed)
        completed = subprocess.run(
            [sys.executable, "-c", script], check=True, capture_output=True,
            text=True, env=environment,
        )
        assert json.loads(completed.stdout) == REPLAY_GOLDEN_VECTOR


REPLAY_GOLDEN_VECTOR = {
    "bundle_sha256": "179bba834e3ef61f9124cba3d2c8e19398dce1b2edad0f09c596595b677ad798",
    "decision_id": "decision:v1:d258a72b77be0d2891ce5837a06529a1b409adec8271ceaf3d544263d077adc8",
    "manifest_ref": "replay-manifest:v1:a5b3b5ff3f848e8a95d38639849fd6358201f642b06c34a0e72351ab89f6cdf3",
    "semantic_hash": "replay-semantic:v1:ae8770cbfe5390bb525afcd7ca004217690a94926e71c6d2e5ba654685b45917",
    "transition_sha256": "94dc645be6c09b1d9898ef494087da681a6a6fdad2e758fce92f51073ecc0504",
}
