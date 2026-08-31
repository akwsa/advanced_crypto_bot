"""Atomic persistence boundary for unified protective EXIT."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from autotrade_next.domain.content import ContentRef
from autotrade_next.domain.execution import ExecutionPreparation, ExecutionSide
from autotrade_next.domain.exit_protection import (
    ExitEvaluation,
    PositionProtectionState,
    exit_command_ref,
)


@dataclass(frozen=True, slots=True)
class ExitCommitBundle:
    command_ref: ContentRef
    expected_sequence: int
    evaluation: ExitEvaluation
    execution: ExecutionPreparation | None

    def __post_init__(self) -> None:
        if type(self.command_ref) is not ContentRef:
            raise TypeError("INVALID_EXIT_COMMAND_REF")
        if type(self.expected_sequence) is not int or self.expected_sequence < 0:
            raise TypeError("INVALID_EXIT_EXPECTED_SEQUENCE")
        if type(self.evaluation) is not ExitEvaluation or self.evaluation.is_noop:
            raise TypeError("INVALID_EXIT_EVALUATION")
        if (self.evaluation.expected_sequence != self.expected_sequence
                or self.evaluation.next_state.sequence != self.expected_sequence + 1
                or self.evaluation.outbox is None):
            raise TypeError("EXIT_COMMIT_MISMATCH")
        expected_command_ref = exit_command_ref(
            position_id=self.evaluation.previous_state.position_id,
            expected_sequence=self.expected_sequence,
            current_price=self.evaluation.current_price,
            evaluated_at_utc=self.evaluation.evaluated_at_utc,
            signals=self.evaluation.signals,
        )
        if self.command_ref != expected_command_ref:
            raise TypeError("EXIT_COMMIT_MISMATCH")
        requires_execution = (
            self.evaluation.next_state.status.value == "EXIT_PENDING"
        )
        if requires_execution:
            if type(self.execution) is not ExecutionPreparation:
                raise TypeError("MISSING_EXIT_EXECUTION")
            state = self.evaluation.next_state
            if (self.evaluation.event_id is None
                    or self.execution.intent.side is not ExecutionSide.SELL
                    or self.execution.intent.decision_id != self.evaluation.event_id.key
                    or self.execution.intent.authority_scope_id != state.authority_scope_id
                    or self.execution.intent.account_id != state.account_id
                    or self.execution.intent.instrument_id != state.instrument_id
                    or self.execution.intent.requested_quantity
                    != self.evaluation.target_quantity
                    or self.execution.intent.created_at_utc
                    != self.evaluation.evaluated_at_utc
                    or self.execution.order.created_at_utc
                    != self.evaluation.evaluated_at_utc
                    or self.execution.outbox.created_at_utc
                    != self.evaluation.evaluated_at_utc):
                raise TypeError("EXIT_COMMIT_MISMATCH")
        elif self.execution is not None:
            raise TypeError("UNEXPECTED_EXIT_EXECUTION")

    @classmethod
    def create(cls, command: object, evaluation: ExitEvaluation,
               execution: ExecutionPreparation | None) -> ExitCommitBundle:
        command_ref_method = getattr(command, "content_ref", None)
        if not callable(command_ref_method):
            raise TypeError("INVALID_EXIT_COMMAND")
        return cls(
            command_ref_method(), evaluation.expected_sequence,
            evaluation, execution,
        )


class ExitUnitOfWork(Protocol):
    def get_position(self, position_id: str) -> PositionProtectionState | None: ...

    def get_exit_commit(self, command_ref: ContentRef) -> ExitCommitBundle | None: ...

    def stage_exit(self, bundle: ExitCommitBundle) -> None: ...

    def commit(self) -> None: ...

    def rollback(self) -> None: ...

    def close(self) -> None: ...


__all__ = ("ExitCommitBundle", "ExitUnitOfWork")
