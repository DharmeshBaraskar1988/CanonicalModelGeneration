"""State and result contracts for the ACORD Alignment Agent."""

from __future__ import annotations

from typing import Any, Literal, TypedDict

AlignmentStatus = Literal["running", "awaiting_review", "failed"]


class AlignmentState(TypedDict, total=False):
    """JSON-serializable state persisted after every LangGraph boundary."""

    run_id: str
    input_digest: str
    region: str
    regional_source: dict[str, Any]
    regional_domain_tree: list[dict[str, Any]]
    regional_endpoints: list[dict[str, Any]]
    acord_model: dict[str, Any]
    acord_run_id: str
    canonical_baseline: dict[str, Any] | None
    baseline_version: int | None
    proposal: dict[str, Any]
    decisions: dict[str, Any]
    status: AlignmentStatus
    stop_reason: str
    errors: list[str]
    events: list[dict[str, Any]]


class AlignmentAgentError(RuntimeError):
    """A failed run that can be retried from its latest durable checkpoint."""

    def __init__(self, run_id: str, message: str, state: AlignmentState) -> None:
        super().__init__(message)
        self.run_id = run_id
        self.state = state
