"""Best-effort shadow runtime hook for Strategy 2."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping

from autotrade.contracts import ACTIONABLE_RECOMMENDATIONS, TradeIntent

from .contracts import Strategy2Decision, StrategyVersion
from .repository import Strategy2Repository
from .taxonomy import DecisionStatus, PositionState, ReasonCode


EXPERIMENT_ID = "shadow-runtime"


@dataclass(frozen=True)
class ShadowObservation:
    decision: Strategy2Decision
    decision_row_id: int
    event_row_id: int | None
    replay_event_row_id: int | None = None
    replayed: bool = False


def prepare_runtime_signal(intent: TradeIntent, source_signal: Mapping[str, Any]) -> dict[str, Any]:
    """Build the worker/runtime payload while preserving source snapshot identity."""
    runtime_signal = dict(intent.signal)
    runtime_signal["_intent"] = intent.to_dict()
    source_signal_id = (
        source_signal.get("signal_id")
        or source_signal.get("snapshot_id")
        or source_signal.get("id")
    )
    if source_signal_id is not None:
        source_text = str(source_signal_id).strip()
        if source_text:
            runtime_signal["_shadow_signal_id"] = source_text
    return runtime_signal


def _snapshot_id(intent: TradeIntent, signal: Mapping[str, Any]) -> str:
    for key in ("_shadow_signal_id", "_source_signal_id", "snapshot_id", "signal_id", "id"):
        value = signal.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return intent.idempotency_key


def observe_intent(*, database, intent: TradeIntent, signal: Mapping[str, Any],
                   strategy_version: str, initial_cash: float,
                   experiment_id: str = EXPERIMENT_ID) -> ShadowObservation:
    """Record one additive Strategy 2 shadow decision for a validated intent."""
    if intent.recommendation not in ACTIONABLE_RECOMMENDATIONS:
        raise ValueError("shadow observation requires a validated actionable intent")

    strategy = StrategyVersion(strategy_version=strategy_version, experiment_id=experiment_id)
    repo = Strategy2Repository(
        database,
        strategy_version=strategy.strategy_version,
        experiment_id=strategy.experiment_id,
        initial_cash=initial_cash,
    )
    operation_identity = f"{intent.idempotency_key}:shadow"
    namespaced_key = strategy.idempotency_key(operation_identity)
    with database.get_connection() as conn:
        prior = conn.execute(
            """SELECT id FROM strategy2_decisions
               WHERE strategy_version=? AND experiment_id=? AND idempotency_key=?""",
            (strategy.strategy_version, strategy.experiment_id, namespaced_key),
        ).fetchone()
    replayed = prior is not None

    user_id = intent.user_id if isinstance(intent.user_id, int) and intent.user_id > 0 else None
    position = repo.get_position(user_id, intent.pair) if user_id is not None else None
    current_state = PositionState(position["state"]) if position else PositionState.CANDIDATE
    enter_path = str(intent.recommendation).upper() in {"BUY", "STRONG_BUY"}
    status = DecisionStatus.ENTER if enter_path else DecisionStatus.NO_ENTRY
    reason_code = ReasonCode.ENTER_CANDIDATE if enter_path else ReasonCode.SHADOW_SKIPPED
    next_state = current_state
    decision = Strategy2Decision.create(
        strategy=strategy,
        operation_identity=operation_identity,
        correlation_id=intent.correlation_id,
        snapshot_id=_snapshot_id(intent, signal),
        pair=intent.pair,
        status=status,
        reason_code=reason_code,
        current_state=current_state,
        next_state=next_state,
        event_time=float(intent.created_at),
        reason="Shadow observation only; Strategy 1 remains authoritative.",
        evidence={
            "shadow_runtime": True,
            "baseline_intent_idempotency_key": intent.idempotency_key,
            "baseline_recommendation": intent.recommendation,
        },
    )
    row = repo.record_decision(
        operation_identity=decision.operation_identity,
        idempotency_key=decision.idempotency_key,
        correlation_id=decision.correlation_id,
        snapshot_id=decision.snapshot_id,
        pair=decision.pair,
        status=decision.status,
        reason_code=decision.reason_code,
        reason=decision.reason,
        evidence=decision.evidence,
    )
    event_row_id = None
    replay_event_row_id = None
    if not replayed and enter_path and user_id is not None and position is None:
        event = repo.transition(
            user_id=user_id,
            pair=intent.pair,
            event_key=f"{decision.idempotency_key}:candidate",
            correlation_id=decision.correlation_id,
            snapshot_id=decision.snapshot_id,
            to_state=PositionState.CANDIDATE,
            reason_code=ReasonCode.ENTER_CANDIDATE,
            event={"operation": "shadow_candidate", "decision_idempotency_key": decision.idempotency_key},
        )
        event_row_id = int(event["id"])
    if replayed:
        replay_event = repo.record_audit_event(
            user_id=None,
            pair=intent.pair,
            event_key=f"{decision.idempotency_key}:replay",
            correlation_id=decision.correlation_id,
            snapshot_id=decision.snapshot_id,
            state=decision.current_state,
            reason_code=ReasonCode.REPLAY,
            event={"operation": "shadow_replay", "decision_idempotency_key": decision.idempotency_key},
        )
        replay_event_row_id = int(replay_event["id"])
    return ShadowObservation(
        decision=decision,
        decision_row_id=int(row["id"]),
        event_row_id=event_row_id,
        replay_event_row_id=replay_event_row_id,
        replayed=replayed,
    )


def observe_intent_safely(*, database, intent: TradeIntent, signal: Mapping[str, Any], config, logger=None):
    """Fail-closed wrapper for the worker seam."""
    if not getattr(config, "AUTOTRADE_STRATEGY2_ENABLED", False):
        return None
    if getattr(config, "AUTOTRADE_STRATEGY2_MODE", "off") != "shadow":
        return None
    try:
        return observe_intent(
            database=database,
            intent=intent,
            signal=signal,
            strategy_version=getattr(config, "AUTOTRADE_STRATEGY2_VERSION", "patient-swing-v1"),
            initial_cash=getattr(config, "AUTOTRADE_STRATEGY2_INITIAL_CASH_IDR", 10_000_000),
        )
    except Exception as exc:
        if logger is not None:
            logger.warning("Strategy 2 shadow observe skipped: %s", exc)
        return None
