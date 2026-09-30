"""Resumable LangGraph orchestration for deterministic ACORD alignment."""

from __future__ import annotations

import json
import sqlite3
from collections.abc import Callable
from hashlib import sha256
from pathlib import Path
from typing import Any

from langgraph.graph import END, START, StateGraph
from langgraph.types import RetryPolicy

from canonical_model_generator.alignment_agent.contracts import (
    AlignmentAgentError,
    AlignmentState,
)
from canonical_model_generator.alignment_agent.persistence import (
    alignment_checkpointer,
    load_review_draft,
    save_review_draft,
)
from canonical_model_generator.alignment_agent.services import (
    default_alignment_decisions,
    propose_acord_alignment,
)

ProposalBuilder = Callable[..., dict[str, Any]]
ProgressCallback = Callable[[str], None]
MAX_NODE_ATTEMPTS = 3


def alignment_input_digest(
    *,
    region: str,
    regional_source: dict[str, Any],
    regional_domain_tree: list[dict[str, Any]],
    regional_endpoints: list[dict[str, Any]],
    acord_model: dict[str, Any],
    acord_run_id: str,
    canonical_baseline: dict[str, Any] | None = None,
    baseline_version: int | None = None,
) -> str:
    """Create the stable identity used to safely reuse a completed run."""
    payload = {
        "region": region,
        "regionalSource": regional_source,
        "regionalDomainTree": regional_domain_tree,
        "regionalEndpoints": regional_endpoints,
        "acordModel": acord_model,
        "acordRunId": acord_run_id,
        "canonicalBaseline": canonical_baseline,
        "baselineVersion": baseline_version,
    }
    return sha256(json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def build_alignment_graph(
    *,
    checkpointer: Any,
    proposal_builder: ProposalBuilder = propose_acord_alignment,
    progress: ProgressCallback | None = None,
    max_node_attempts: int = MAX_NODE_ATTEMPTS,
) -> Any:
    """Build the Alignment Agent with bounded retry at each material node."""
    builder = StateGraph(AlignmentState)
    retry = RetryPolicy(
        max_attempts=max_node_attempts,
        retry_on=lambda exc: not isinstance(exc, (KeyError, TypeError, ValueError)),
    )

    def notify(message: str) -> None:
        if progress is not None:
            progress(message)

    def validate_inputs(state: AlignmentState) -> dict[str, Any]:
        errors: list[str] = []
        if not str(state.get("region", "")).strip():
            errors.append("Alignment region is required")
        if not str(state.get("acord_run_id", "")).strip():
            errors.append("A completed ACORD ingestion run is required")
        if not isinstance(state.get("regional_source"), dict):
            errors.append("Regional entity and attribute source is required")
        if not isinstance(state.get("regional_domain_tree"), list):
            errors.append("Regional domain and capability source is required")
        if not isinstance(state.get("regional_endpoints"), list):
            errors.append("Regional endpoint source is required")
        if not isinstance(state.get("acord_model"), dict):
            errors.append("ACORD model is required")
        expected_digest = alignment_input_digest(
            region=state.get("region", ""),
            regional_source=state.get("regional_source", {}),
            regional_domain_tree=state.get("regional_domain_tree", []),
            regional_endpoints=state.get("regional_endpoints", []),
            acord_model=state.get("acord_model", {}),
            acord_run_id=state.get("acord_run_id", ""),
            canonical_baseline=state.get("canonical_baseline"),
            baseline_version=state.get("baseline_version"),
        )
        if state.get("input_digest") != expected_digest:
            errors.append("Alignment input digest does not match the supplied evidence")
        if errors:
            raise ValueError("; ".join(errors))
        notify("Alignment inputs validated.")
        return _event(state, "validate_inputs", "ok")

    def propose(state: AlignmentState) -> dict[str, Any]:
        notify("Comparing the canonical baseline first, then using ACORD as fallback.")
        proposal = proposal_builder(
            region=state["region"],
            regional_source=state["regional_source"],
            regional_domain_tree=state["regional_domain_tree"],
            regional_endpoints=state["regional_endpoints"],
            acord_model=state["acord_model"],
            acord_run_id=state["acord_run_id"],
            canonical_baseline=state.get("canonical_baseline"),
            baseline_version=state.get("baseline_version"),
        )
        notify("Alignment proposal generated.")
        return _event(state, "propose_alignment", "ok", proposal=proposal)

    def validate_proposal(state: AlignmentState) -> dict[str, Any]:
        proposal = state["proposal"]
        if proposal.get("region") != state["region"]:
            raise ValueError("Alignment proposal changed the selected region")
        expected_ids = _regional_ids(state["regional_source"], state["regional_domain_tree"])
        proposed_ids = _proposal_ids(proposal)
        missing = sorted(expected_ids - proposed_ids)
        duplicates = _duplicate_proposal_ids(proposal)
        if missing or duplicates:
            details = []
            if missing:
                details.append(f"missing regional IDs: {', '.join(missing)}")
            if duplicates:
                details.append(f"duplicate regional IDs: {', '.join(duplicates)}")
            raise ValueError("Invalid alignment proposal: " + "; ".join(details))
        notify(f"Validated {len(proposed_ids)} alignment nodes against regional inventory.")
        return _event(state, "validate_proposal", "ok")

    def prepare_review(state: AlignmentState) -> dict[str, Any]:
        decisions = default_alignment_decisions(state["proposal"])
        notify("Alignment is ready for explicit human review.")
        return _event(
            state,
            "prepare_review",
            "ok",
            decisions=decisions,
            status="awaiting_review",
            stop_reason="review_required",
            errors=[],
        )

    builder.add_node("validate_inputs", validate_inputs, retry_policy=retry)
    builder.add_node("propose_alignment", propose, retry_policy=retry)
    builder.add_node("validate_proposal", validate_proposal, retry_policy=retry)
    builder.add_node("prepare_review", prepare_review, retry_policy=retry)
    builder.add_edge(START, "validate_inputs")
    builder.add_edge("validate_inputs", "propose_alignment")
    builder.add_edge("propose_alignment", "validate_proposal")
    builder.add_edge("validate_proposal", "prepare_review")
    builder.add_edge("prepare_review", END)
    return builder.compile(checkpointer=checkpointer)


def run_alignment_agent(
    database: Path,
    *,
    run_id: str,
    region: str,
    regional_source: dict[str, Any],
    regional_domain_tree: list[dict[str, Any]],
    regional_endpoints: list[dict[str, Any]],
    acord_model: dict[str, Any],
    acord_run_id: str,
    canonical_baseline: dict[str, Any] | None = None,
    baseline_version: int | None = None,
    progress: ProgressCallback | None = None,
    proposal_builder: ProposalBuilder = propose_acord_alignment,
    max_node_attempts: int = MAX_NODE_ATTEMPTS,
) -> AlignmentState:
    """Start or reuse one durable alignment run."""
    digest = alignment_input_digest(
        region=region,
        regional_source=regional_source,
        regional_domain_tree=regional_domain_tree,
        regional_endpoints=regional_endpoints,
        acord_model=acord_model,
        acord_run_id=acord_run_id,
        canonical_baseline=canonical_baseline,
        baseline_version=baseline_version,
    )
    with alignment_checkpointer(database) as checkpointer:
        graph = build_alignment_graph(
            checkpointer=checkpointer,
            progress=progress,
            proposal_builder=proposal_builder,
            max_node_attempts=max_node_attempts,
        )
        config = _config(run_id)
        existing = _state_values(graph, config)
        if existing:
            if existing.get("input_digest") != digest:
                raise ValueError("Alignment run ID already belongs to different input evidence")
            if existing.get("status") == "awaiting_review":
                return _with_review_draft(database, run_id, existing)
            return _resume_graph(graph, config, database, run_id)
        initial: AlignmentState = {
            "run_id": run_id,
            "input_digest": digest,
            "region": region,
            "regional_source": regional_source,
            "regional_domain_tree": regional_domain_tree,
            "regional_endpoints": regional_endpoints,
            "acord_model": acord_model,
            "acord_run_id": acord_run_id,
            "canonical_baseline": canonical_baseline,
            "baseline_version": baseline_version,
            "status": "running",
            "stop_reason": "",
            "errors": [],
            "events": [],
        }
        try:
            result = graph.invoke(initial, config=config)
        except Exception as exc:
            failed = _state_values(graph, config)
            failed.update(
                status="failed",
                stop_reason="node_error",
                errors=[*failed.get("errors", []), _safe_error(exc)],
            )
            raise AlignmentAgentError(run_id, _safe_error(exc), failed) from exc
    save_review_draft(database, run_id, result["decisions"])
    return result


def resume_alignment_agent(
    database: Path,
    run_id: str,
    *,
    progress: ProgressCallback | None = None,
    proposal_builder: ProposalBuilder = propose_acord_alignment,
    max_node_attempts: int = MAX_NODE_ATTEMPTS,
) -> AlignmentState:
    """Resume the failed node from the latest durable checkpoint."""
    with alignment_checkpointer(database) as checkpointer:
        graph = build_alignment_graph(
            checkpointer=checkpointer,
            progress=progress,
            proposal_builder=proposal_builder,
            max_node_attempts=max_node_attempts,
        )
        config = _config(run_id)
        if not _state_values(graph, config):
            raise ValueError(f"No Alignment Agent checkpoint exists for run {run_id}")
        return _resume_graph(graph, config, database, run_id)


def load_alignment_agent_state(database: Path, run_id: str) -> AlignmentState | None:
    """Read the latest persisted state without executing the graph."""
    if not database.is_file():
        return None
    with alignment_checkpointer(database) as checkpointer:
        graph = build_alignment_graph(checkpointer=checkpointer)
        values = _state_values(graph, _config(run_id))
    return _with_review_draft(database, run_id, values) if values else None


def persist_alignment_decisions(database: Path, run_id: str, decisions: dict[str, Any]) -> None:
    """Persist an operator's in-progress review so browser restarts do not lose it."""
    state = load_alignment_agent_state(database, run_id)
    if state is None:
        raise ValueError(f"No Alignment Agent checkpoint exists for run {run_id}")
    if state.get("status") != "awaiting_review":
        raise ValueError("Alignment decisions can only be saved for a review-ready run")
    save_review_draft(database, run_id, decisions)


def _resume_graph(
    graph: Any, config: dict[str, Any], database: Path, run_id: str
) -> AlignmentState:
    try:
        result = graph.invoke(None, config=config)
    except Exception as exc:
        failed = _state_values(graph, config)
        failed.update(
            status="failed",
            stop_reason="node_error",
            errors=[*failed.get("errors", []), _safe_error(exc)],
        )
        raise AlignmentAgentError(run_id, _safe_error(exc), failed) from exc
    save_review_draft(database, run_id, result["decisions"])
    return result


def purge_alignment_agent_run(database: Path, run_id: str) -> bool:
    """Delete all SQLite checkpoint rows and review draft for one run so it can restart fresh."""
    if not database.is_file():
        return False
    with sqlite3.connect(database) as connection:
        result = connection.execute("DELETE FROM checkpoints WHERE thread_id = ?", (run_id,))
        deleted = result.rowcount
        connection.execute("DELETE FROM writes WHERE thread_id = ?", (run_id,))
        table = connection.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name='alignment_review_drafts'",
        ).fetchone()
        if table:
            connection.execute("DELETE FROM alignment_review_drafts WHERE run_id = ?", (run_id,))
    return deleted > 0


def _config(run_id: str) -> dict[str, Any]:
    return {"configurable": {"thread_id": run_id}}


def _state_values(graph: Any, config: dict[str, Any]) -> AlignmentState:
    snapshot = graph.get_state(config)
    return dict(snapshot.values) if snapshot and snapshot.values else {}


def _with_review_draft(database: Path, run_id: str, state: AlignmentState) -> AlignmentState:
    draft = load_review_draft(database, run_id)
    return {**state, "decisions": draft} if draft is not None else state


def _event(state: AlignmentState, node: str, node_status: str, **updates: Any) -> dict[str, Any]:
    return {
        **updates,
        "events": [*state.get("events", []), {"node": node, "status": node_status}],
    }


def _regional_ids(
    regional_source: dict[str, Any], regional_domain_tree: list[dict[str, Any]]
) -> set[str]:
    identifiers = {
        item["id"]
        for entity in regional_source.get("entities", [])
        for item in [entity, *entity.get("attributes", [])]
    }
    for domain in regional_domain_tree:
        identifiers.add(_alignment_id("regional-domain", domain["name"]))
        identifiers.update(
            _alignment_id("regional-capability", domain["name"], item["name"])
            for item in domain.get("capabilities", [])
        )
    return identifiers


def _proposal_items(proposal: dict[str, Any]) -> list[dict[str, Any]]:
    return [
        *(
            item
            for entity in proposal.get("entities", [])
            for item in [entity, *entity.get("attributes", [])]
        ),
        *(
            item
            for domain in proposal.get("domains", [])
            for item in [domain, *domain.get("capabilities", [])]
        ),
    ]


def _proposal_ids(proposal: dict[str, Any]) -> set[str]:
    return {item["regionalId"] for item in _proposal_items(proposal)}


def _duplicate_proposal_ids(proposal: dict[str, Any]) -> list[str]:
    identifiers = [item["regionalId"] for item in _proposal_items(proposal)]
    return sorted({item for item in identifiers if identifiers.count(item) > 1})


def _safe_error(exc: Exception) -> str:
    return " ".join(str(exc).split())[:1000] or type(exc).__name__


def _alignment_id(kind: str, *parts: str) -> str:
    digest = sha256("\x1f".join((kind, *parts)).encode()).hexdigest()[:20]
    return f"{kind}-{digest}"
