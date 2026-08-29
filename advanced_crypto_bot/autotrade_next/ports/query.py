"""Read-only query capability marker without implementation dependencies."""

from typing import Protocol, TypeVar


ViewT = TypeVar("ViewT", covariant=True)
PageT = TypeVar("PageT", covariant=True)


class ReadOnlyQueryPort(Protocol[ViewT, PageT]):
    """A capability that can only retrieve immutable projection values."""

    def get_by_decision_id(self, authority_scope_id: str, decision_id: str) -> ViewT | None: ...

    def get_by_candidate_id(self, authority_scope_id: str, candidate_id: str) -> tuple[ViewT, ...]: ...

    def list_views(
        self,
        authority_scope_id: str,
        *,
        page_size: int,
        cursor: str | None = None,
        instrument_id: str | None = None,
    ) -> PageT: ...


__all__ = ("ReadOnlyQueryPort",)
