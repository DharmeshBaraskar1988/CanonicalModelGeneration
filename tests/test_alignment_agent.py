from __future__ import annotations

from copy import deepcopy

import pytest

from canonical_model_generator.acord_alignment import propose_acord_alignment
from canonical_model_generator.alignment_agent import (
    AlignmentAgentError,
    load_alignment_agent_state,
    persist_alignment_decisions,
    resume_alignment_agent,
    run_alignment_agent,
)


def _inputs() -> dict:
    return {
        "region": "EU",
        "regional_source": {
            "status": "Approved",
            "entities": [
                {
                    "id": "regional-policy",
                    "name": "Policy",
                    "description": "Regional policy.",
                    "attributes": [
                        {
                            "id": "regional-policy-number",
                            "name": "policyNumber",
                            "description": "Policy identifier.",
                            "type": "string",
                        }
                    ],
                }
            ],
        },
        "regional_domain_tree": [
            {
                "name": "Policy",
                "capabilities": [{"name": "Get policy", "apis": []}],
            }
        ],
        "regional_endpoints": [],
        "acord_model": {
            "source": {"referenceLabel": "ACORD", "referenceVersion": "1"},
            "entities": [
                {
                    "id": "acord-policy",
                    "name": "Policy",
                    "description": "Standard policy.",
                    "attributes": [
                        {
                            "id": "acord-policy-number",
                            "name": "policyNumber",
                            "description": "Standard policy identifier.",
                            "type": "string",
                        }
                    ],
                }
            ],
            "endpoints": [
                {
                    "operationId": "getPolicy",
                    "method": "GET",
                    "route": "/policies/{id}",
                    "tags": ["Policy"],
                    "summary": "Get policy",
                }
            ],
        },
        "acord_run_id": "a" * 32,
    }


def test_alignment_agent_checkpoints_proposal_and_review_draft(tmp_path) -> None:
    database = tmp_path / "alignment-agent.sqlite3"
    state = run_alignment_agent(database, run_id="alignment-1", **_inputs())

    assert state["status"] == "awaiting_review"
    assert state["stop_reason"] == "review_required"
    assert [event["node"] for event in state["events"]] == [
        "validate_inputs",
        "propose_alignment",
        "validate_proposal",
        "prepare_review",
    ]
    assert state["proposal"]["entities"][0]["acordCandidate"]["name"] == "Policy"
    assert database.is_file()

    decisions = deepcopy(state["decisions"])
    decisions["entities"]["regional-policy"]["reason"] = "Durable reviewer note."
    persist_alignment_decisions(database, "alignment-1", decisions)
    restored = load_alignment_agent_state(database, "alignment-1")
    assert restored is not None
    assert (
        restored["decisions"]["entities"]["regional-policy"]["reason"] == "Durable reviewer note."
    )


def test_alignment_agent_retries_transient_proposal_failure(tmp_path) -> None:
    attempts = 0

    def flaky_builder(**kwargs):
        nonlocal attempts
        attempts += 1
        if attempts < 3:
            raise RuntimeError("temporary matcher failure")
        return propose_acord_alignment(**kwargs)

    state = run_alignment_agent(
        tmp_path / "alignment-agent.sqlite3",
        run_id="alignment-retry",
        proposal_builder=flaky_builder,
        **_inputs(),
    )

    assert state["status"] == "awaiting_review"
    assert attempts == 3


def test_alignment_agent_resumes_failed_node_without_replaying_validation(tmp_path) -> None:
    database = tmp_path / "alignment-agent.sqlite3"

    def unavailable_builder(**_kwargs):
        raise RuntimeError("matcher unavailable")

    with pytest.raises(AlignmentAgentError) as failure:
        run_alignment_agent(
            database,
            run_id="alignment-resume",
            proposal_builder=unavailable_builder,
            max_node_attempts=2,
            **_inputs(),
        )
    assert failure.value.state["status"] == "failed"
    assert [item["node"] for item in failure.value.state["events"]] == ["validate_inputs"]

    resumed = resume_alignment_agent(database, "alignment-resume")
    assert resumed["status"] == "awaiting_review"
    assert [item["node"] for item in resumed["events"]].count("validate_inputs") == 1


def test_alignment_agent_rejects_reusing_run_id_for_changed_evidence(tmp_path) -> None:
    database = tmp_path / "alignment-agent.sqlite3"
    run_alignment_agent(database, run_id="alignment-stable", **_inputs())
    changed = _inputs()
    changed["region"] = "US"

    with pytest.raises(ValueError, match="different input evidence"):
        run_alignment_agent(database, run_id="alignment-stable", **changed)
