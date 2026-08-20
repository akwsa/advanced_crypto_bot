import math

import pytest

from autotrade.strategy2.contracts import (
    CostAssumptions,
    FeatureSnapshot,
    MarketSnapshot,
    Strategy2Decision,
    StrategyVersion,
    stable_idempotency_key,
)
from autotrade.strategy2.taxonomy import DecisionStatus, PositionState, ReasonCode
from autotrade.strategy2.state_machine import InvalidTransitionError


def test_strategy_identity_is_stable_and_namespaced():
    version = StrategyVersion(strategy_version="patient-swing-v1", experiment_id="shadow-a")

    first = version.idempotency_key("snapshot-1:decision")
    second = stable_idempotency_key("patient-swing-v1", "shadow-a", "snapshot-1:decision")

    assert first == second
    assert first != StrategyVersion("patient-swing-v2", "shadow-a").idempotency_key(
        "snapshot-1:decision"
    )
    assert first != StrategyVersion("patient-swing-v1", "shadow-b").idempotency_key(
        "snapshot-1:decision"
    )


def test_snapshot_and_decision_evidence_are_deeply_immutable():
    source = {"trend": {"healthy": True}, "windows": [5, 20]}
    features = FeatureSnapshot("snap-1", 10.0, source)
    source["trend"]["healthy"] = False
    source["windows"].append(50)

    assert features.features["trend"]["healthy"] is True
    assert features.features["windows"] == (5, 20)
    with pytest.raises(TypeError):
        features.features["new"] = 1

    decision = Strategy2Decision.create(
        strategy=StrategyVersion("patient-swing-v1", "shadow-a"),
        operation_identity="snap-1:decision",
        correlation_id="corr-1",
        snapshot_id="snap-1",
        pair="BTCIDR",
        status=DecisionStatus.NO_ENTRY,
        reason_code=ReasonCode.TREND_NOT_HEALTHY,
        current_state=PositionState.CANDIDATE,
        next_state=PositionState.CANDIDATE,
        event_time=10.0,
        evidence={"score": 0.4},
    )
    assert decision.idempotency_key == StrategyVersion(
        "patient-swing-v1", "shadow-a"
    ).idempotency_key("snap-1:decision")


@pytest.mark.parametrize("bad", [math.nan, math.inf, -math.inf])
def test_numeric_contracts_reject_non_finite_values(bad):
    with pytest.raises(ValueError):
        CostAssumptions(buy_fee_rate=bad)
    with pytest.raises(ValueError):
        MarketSnapshot("snap", "BTCIDR", bad, 10.0, 11.0, 10.5)
    with pytest.raises(ValueError):
        FeatureSnapshot("snap", 10.0, {"score": bad})


def test_cost_and_market_invariants_fail_closed():
    with pytest.raises(ValueError):
        CostAssumptions(sell_fee_rate=-0.01)
    with pytest.raises(ValueError):
        CostAssumptions(*(1e308 for _ in range(5))).round_trip_rate
    with pytest.raises(ValueError):
        MarketSnapshot("snap", "BTCIDR", 10.0, 12.0, 11.0, 11.5)
    with pytest.raises(ValueError):
        MarketSnapshot("snap", "", 10.0, 10.0, 11.0, 10.5)
    with pytest.raises(ValueError):
        MarketSnapshot("snap", "/", 10.0, 10.0, 11.0, 10.5)


def test_contract_payload_rejects_unsupported_values_and_non_string_keys():
    with pytest.raises(TypeError):
        FeatureSnapshot("snap", 10.0, {1: "collides", "1": "other"})
    with pytest.raises(TypeError):
        FeatureSnapshot("snap", 10.0, {"mutable": object()})
    with pytest.raises(TypeError):
        FeatureSnapshot("snap", 10.0, ["not", "a", "mapping"])
    with pytest.raises(TypeError):
        MarketSnapshot("snap", "BTCIDR", 10.0, 10.0, 11.0, 10.5, source=object())


def test_decision_rejects_illegal_state_transition():
    with pytest.raises(InvalidTransitionError):
        Strategy2Decision.create(
            strategy=StrategyVersion("patient-swing-v1", "shadow-a"),
            operation_identity="illegal", correlation_id="corr", snapshot_id="snap",
            pair="btc/idr", status=DecisionStatus.ENTER,
            reason_code=ReasonCode.ENTRY_APPROVED,
            current_state=PositionState.CLOSED, next_state=PositionState.OPEN_RISK,
            event_time=10,
        )


def test_decision_rejects_separator_only_pair_and_non_text_reason():
    with pytest.raises(ValueError):
        Strategy2Decision.create(
            strategy=StrategyVersion("patient-swing-v1", "shadow-a"),
            operation_identity="empty-pair",
            correlation_id="corr",
            snapshot_id="snap",
            pair="/",
            status=DecisionStatus.NO_ENTRY,
            reason_code=ReasonCode.TREND_NOT_HEALTHY,
            current_state=PositionState.CANDIDATE,
            next_state=PositionState.CANDIDATE,
            event_time=10,
        )
    with pytest.raises(TypeError):
        Strategy2Decision.create(
            strategy=StrategyVersion("patient-swing-v1", "shadow-a"),
            operation_identity="bad-reason",
            correlation_id="corr",
            snapshot_id="snap",
            pair="btcidr",
            status=DecisionStatus.NO_ENTRY,
            reason_code=ReasonCode.TREND_NOT_HEALTHY,
            current_state=PositionState.CANDIDATE,
            next_state=PositionState.CANDIDATE,
            event_time=10,
            reason=[],
        )
