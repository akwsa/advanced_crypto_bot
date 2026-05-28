from dataclasses import is_dataclass

from signals.signal_decision_layer import (
    AVOID_BUY,
    BUY_CANDIDATE,
    BUY_CONFIRMED,
    DecisionContext,
    DecisionResult,
    FinalAction,
    IGNORE,
    PositionState,
    RawSignal,
    ReasonCode,
    SELL_CONFIRMED,
    SELL_STOP_LOSS,
    SELL_TAKE_PROFIT,
    SELL_TRAILING_PROFIT,
    WAIT_CONFIRMATION,
    HOLD_POSITION,
)


def test_final_action_taxonomy_is_complete():
    expected = {
        "BUY_CONFIRMED",
        "BUY_CANDIDATE",
        "HOLD_POSITION",
        "SELL_CONFIRMED",
        "SELL_STOP_LOSS",
        "SELL_TAKE_PROFIT",
        "SELL_TRAILING_PROFIT",
        "AVOID_BUY",
        "WAIT_CONFIRMATION",
        "IGNORE",
    }
    actual = {item.value for item in FinalAction}
    assert expected <= actual


def test_raw_signal_enum_stays_compatible_with_legacy_literals():
    assert RawSignal.BUY.value == "BUY"
    assert RawSignal.STRONG_BUY.value == "STRONG_BUY"
    assert RawSignal.HOLD.value == "HOLD"
    assert RawSignal.SELL.value == "SELL"
    assert RawSignal.STRONG_SELL.value == "STRONG_SELL"


def test_position_state_has_fail_safe_unknown_state():
    assert PositionState.NO_POSITION.value == "NO_POSITION"
    assert PositionState.HAS_POSITION.value == "HAS_POSITION"
    assert PositionState.UNKNOWN_POSITION.value == "UNKNOWN_POSITION"


def test_decision_context_is_pure_dataclass_with_safe_defaults():
    ctx = DecisionContext(
        pair="BTCIDR",
        raw_signal=RawSignal.SELL,
        ml_confidence=0.81,
        position_state=PositionState.UNKNOWN_POSITION,
    )

    assert is_dataclass(ctx)
    assert ctx.pair == "BTCIDR"
    assert ctx.raw_signal is RawSignal.SELL
    assert ctx.position_state is PositionState.UNKNOWN_POSITION
    assert ctx.history_available is None
    assert ctx.three_hour_trend is None
    assert ctx.sell_count_last_3 is None
    assert ctx.sl_hit is None
    assert ctx.tp_hit is None
    assert ctx.trailing_hit is None


def test_decision_result_serializes_domain_contract_for_adapters():
    result = DecisionResult(
        raw_signal=RawSignal.SELL,
        final_action=AVOID_BUY,
        reason_codes=[ReasonCode.NO_POSITION_FOR_SELL, ReasonCode.THRESHOLD_NOT_MET],
        reason_text="SELL tanpa posisi harus jadi avoid-buy dashboard-only.",
        score=0.42,
        telegram_actionable=False,
        execution_allowed=False,
        audit_payload={"source": "unit-test", "position_qty": 0},
    )

    payload = result.to_dict()

    assert payload["raw_signal"] == "SELL"
    assert payload["final_action"] == "AVOID_BUY"
    assert payload["reason_codes"] == ["NO_POSITION_FOR_SELL", "THRESHOLD_NOT_MET"]
    assert payload["reason_text"]
    assert payload["telegram_actionable"] is False
    assert payload["execution_allowed"] is False
    assert payload["audit_payload"]["source"] == "unit-test"


def test_reason_code_covers_core_branching_cases():
    values = {item.value for item in ReasonCode}
    assert "NO_POSITION_FOR_SELL" in values
    assert "INSUFFICIENT_HISTORY" in values
    assert "HARD_RISK_GATE" in values
    assert "THRESHOLD_MET" in values
    assert "THRESHOLD_NOT_MET" in values


def test_contract_constants_alias_enum_members_for_readable_imports():
    assert BUY_CONFIRMED is FinalAction.BUY_CONFIRMED
    assert BUY_CANDIDATE is FinalAction.BUY_CANDIDATE
    assert HOLD_POSITION is FinalAction.HOLD_POSITION
    assert SELL_CONFIRMED is FinalAction.SELL_CONFIRMED
    assert SELL_STOP_LOSS is FinalAction.SELL_STOP_LOSS
    assert SELL_TAKE_PROFIT is FinalAction.SELL_TAKE_PROFIT
    assert SELL_TRAILING_PROFIT is FinalAction.SELL_TRAILING_PROFIT
    assert WAIT_CONFIRMATION is FinalAction.WAIT_CONFIRMATION
    assert IGNORE is FinalAction.IGNORE
