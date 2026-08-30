"""Commit-before-dispatch application handler for protective EXIT."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime

from autotrade_next.domain.content import ContentRef
from autotrade_next.domain.execution import DispatchEnvelope, ExecutionPreparation
from autotrade_next.domain.exit_protection import (
    ExitError,
    ExitEvaluation,
    ExitSignals,
    PositionProtectionStatus,
    build_exit_execution,
    evaluate_exit,
    exit_command_ref,
)
from autotrade_next.domain.numeric import ScaledInteger
from autotrade_next.ports.exit import ExitCommitBundle, ExitUnitOfWork


@dataclass(frozen=True, slots=True)
class EvaluateExitCommand:
    position_id: str
    expected_sequence: int
    current_price: ScaledInteger
    evaluated_at_utc: datetime
    signals: ExitSignals

    def __post_init__(self) -> None:
        if type(self.position_id) is not str or not self.position_id.strip():
            raise ExitError("INVALID_POSITION_ID")
        if type(self.expected_sequence) is not int or self.expected_sequence < 0:
            raise ExitError("INVALID_POSITION_SEQUENCE")
        if type(self.current_price) is not ScaledInteger or self.current_price.units <= 0:
            raise ExitError("INVALID_EXIT_PRICE")
        if (type(self.evaluated_at_utc) is not datetime
                or self.evaluated_at_utc.tzinfo is not UTC):
            raise ExitError("INVALID_EXIT_TIME")
        if type(self.signals) is not ExitSignals:
            raise ExitError("INVALID_EXIT_SIGNAL")

    def binding_value(self) -> dict[str, object]:
        return {
            "schema_version": "evaluate-exit-command:v1",
            "position_id": self.position_id,
            "expected_sequence": self.expected_sequence,
            "current_price": {
                "units": self.current_price.units,
                "scale": self.current_price.scale,
            },
            "evaluated_at_utc": self.evaluated_at_utc,
            "signals": self.signals.to_canonical_value(),
        }

    def content_ref(self) -> ContentRef:
        return exit_command_ref(
            position_id=self.position_id,
            expected_sequence=self.expected_sequence,
            current_price=self.current_price,
            evaluated_at_utc=self.evaluated_at_utc,
            signals=self.signals,
        )


@dataclass(frozen=True, slots=True)
class ExitCommandResult:
    evaluation: ExitEvaluation
    dispatch: DispatchEnvelope | None


def _dispatch(execution: ExecutionPreparation | None) -> DispatchEnvelope | None:
    if execution is None:
        return None
    return DispatchEnvelope(
        execution.intent.intent_id.key,
        execution.order.order_id.key,
        execution.order.order_ref,
    )


def _result(bundle: ExitCommitBundle) -> ExitCommandResult:
    return ExitCommandResult(bundle.evaluation, _dispatch(bundle.execution))


def _rollback_without_masking(uow: ExitUnitOfWork) -> None:
    try:
        uow.rollback()
    except BaseException:
        pass


def _close_without_masking(uow: ExitUnitOfWork) -> None:
    try:
        uow.close()
    except BaseException:
        pass


def prepare_protective_exit(command: EvaluateExitCommand,
                            uow: ExitUnitOfWork) -> ExitCommandResult:
    """Atomically bind Position transition, event, outbox, Intent and dispatch."""
    if type(command) is not EvaluateExitCommand:
        raise ExitError("INVALID_EXIT_COMMAND")
    command_ref = command.content_ref()
    try:
        existing = uow.get_exit_commit(command_ref)
        if existing is not None:
            if type(existing) is not ExitCommitBundle:
                raise ExitError("EXIT_COMMAND_CONFLICT")
            return _result(existing)
        state = uow.get_position(command.position_id)
        if state is None:
            raise ExitError("POSITION_NOT_FOUND")
        if state.sequence != command.expected_sequence:
            raise ExitError("POSITION_SEQUENCE_CONFLICT")
        evaluation = evaluate_exit(
            state,
            current_price=command.current_price,
            evaluated_at_utc=command.evaluated_at_utc,
            signals=command.signals,
        )
        if evaluation.is_noop:
            return ExitCommandResult(evaluation, None)
        execution = (
            build_exit_execution(evaluation, created_at_utc=command.evaluated_at_utc)
            if evaluation.next_state.status is PositionProtectionStatus.EXIT_PENDING
            else None
        )
        bundle = ExitCommitBundle(
            command_ref, command.expected_sequence, evaluation, execution,
        )
        uow.stage_exit(bundle)
        uow.commit()
        return _result(bundle)
    except BaseException:
        _rollback_without_masking(uow)
        raise
    finally:
        _close_without_masking(uow)


__all__ = (
    "EvaluateExitCommand", "ExitCommandResult", "prepare_protective_exit",
)
