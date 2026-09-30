from __future__ import annotations

import pytest

from canonical_model_generator.acord_alignment import (
    FULL_MATCH,
    MANUAL,
    NOT_MATCHED,
    USE_BASELINE,
    USE_GENERATED,
    approve_acord_alignment,
    attach_generated_gap_proposal,
    default_alignment_decisions,
    delete_alignment_artifact,
    load_alignment_artifacts,
    propose_acord_alignment,
    save_alignment_artifact,
    validate_alignment_decisions,
)


def _regional_source() -> dict:
    return {
        "status": "Approved",
        "entities": [
            {
                "id": "regional-policy",
                "name": "Policy",
                "description": "An insurance policy contract.",
                "apis": ["Quote API"],
                "attributes": [
                    {
                        "id": "regional-policy-number",
                        "name": "policyNumber",
                        "description": "Customer policy number.",
                        "type": "string",
                        "requiredInAllSources": True,
                    },
                    {
                        "id": "regional-premium",
                        "name": "premiumAmount",
                        "description": "Quoted premium.",
                        "type": "decimal",
                        "requiredInAllSources": False,
                    },
                ],
                "endpoints": [
                    {
                        "API": "Quote API",
                        "Endpoint": "GetPolicy",
                        "Method": "GET",
                        "Route": "/policies/{policyId}",
                        "Usage": "Response 200",
                    }
                ],
            }
        ],
    }


def _regional_domains() -> list[dict]:
    return [
        {
            "name": "Policy",
            "capabilities": [
                {
                    "name": "Get a policy",
                    "apis": [
                        {
                            "name": "Quote API",
                            "endpoints": [
                                {
                                    "Summary": "Get a policy",
                                    "Description": "Returns the policy record.",
                                    "Business purpose": "Review policy details.",
                                }
                            ],
                        }
                    ],
                }
            ],
        }
    ]


def _regional_endpoints() -> list[dict]:
    return [
        {
            "API": "Quote API",
            "Endpoint": "GetPolicy",
            "Method": "GET",
            "Route": "/policies/{policyId}",
            "Domain": "Policy",
            "Capability": "Get a policy",
            "Description": "Returns the policy record.",
        }
    ]


def _acord_model() -> dict:
    return {
        "source": {
            "referenceLabel": "ACORD Policy",
            "referenceVersion": "2026.1",
            "sourceFile": "acord.yaml",
        },
        "entities": [
            {
                "id": "acord-policy",
                "name": "Policy",
                "description": "An insurance policy contract.",
                "comments": ["Use approved policy codes."],
                "attributes": [
                    {
                        "id": "acord-policy-number",
                        "name": "policyNumber",
                        "description": "Customer policy number.",
                        "type": "string",
                        "constraints": {"minLength": 5},
                    },
                    {
                        "id": "acord-status",
                        "name": "policyStatus",
                        "description": "Policy lifecycle status.",
                        "type": "string",
                        "constraints": {"enum": ["Active", "Cancelled"]},
                    },
                ],
            }
        ],
        "endpoints": [
            {
                "operationId": "getPolicy",
                "method": "GET",
                "route": "/policies/{policyId}",
                "tags": ["Policy"],
                "summary": "Get a policy",
                "description": "Returns the policy record.",
            }
        ],
    }


def _proposal() -> dict:
    return propose_acord_alignment(
        region="EU",
        regional_source=_regional_source(),
        regional_domain_tree=_regional_domains(),
        regional_endpoints=_regional_endpoints(),
        acord_model=_acord_model(),
        acord_run_id="a" * 32,
    )


def _approve_alignment_tree(decisions: dict) -> None:
    for entity_decision in decisions["entities"].values():
        entity_decision["approved"] = True
        for attribute_decision in entity_decision["attributes"].values():
            attribute_decision["approved"] = True
    for domain_decision in decisions["domains"].values():
        domain_decision["approved"] = True
        for capability_decision in domain_decision["capabilities"].values():
            capability_decision["approved"] = True


def test_proposal_reports_match_coverage_gaps_and_unique_attribute_candidates() -> None:
    proposal = _proposal()

    assert proposal["matchSummary"]["total"] == 5
    assert proposal["matchSummary"]["matchedPercent"] > 0
    entity = proposal["entities"][0]
    assert entity["acordCandidate"]["name"] == "Policy"
    assert entity["status"] != NOT_MATCHED
    assert "premiumAmount" in entity["unmatchedDetails"]["regionalAttributes"]
    candidate_ids = [
        field["acordCandidate"]["id"]
        for field in entity["attributes"]
        if field.get("acordCandidate")
    ]
    assert len(candidate_ids) == len(set(candidate_ids))
    assert proposal["domains"][0]["status"] == FULL_MATCH


def test_approval_requires_reasons_and_builds_canonical_model_and_endpoints() -> None:
    proposal = _proposal()
    decisions = default_alignment_decisions(proposal)
    initial_errors = validate_alignment_decisions(proposal, decisions)
    assert initial_errors
    assert any("needs explicit approval" in error for error in initial_errors)
    assert any("Domain Policy needs explicit approval" in error for error in initial_errors)
    assert any(
        "Capability Policy.Get a policy needs explicit approval" in error
        for error in initial_errors
    )

    policy = proposal["entities"][0]
    policy_decision = decisions["entities"][policy["regionalId"]]
    policy_decision["reviewStatus"] = NOT_MATCHED
    policy_decision["reviewDescription"] = "Reviewer-approved policy description."
    policy_number = next(
        field for field in policy["attributes"] if field["regionalName"] == "policyNumber"
    )
    policy_number_decision = policy_decision["attributes"][policy_number["regionalId"]]
    policy_number_decision["reviewStatus"] = "Partial match"
    policy_number_decision["reviewDescription"] = "Reviewed policy identifier."
    policy_number_decision["reason"] = "The field meaning agrees but naming needs review."

    for entity in proposal["entities"]:
        entity_decision = decisions["entities"][entity["regionalId"]]
        if entity["status"] != FULL_MATCH:
            entity_decision["reason"] = "Reviewed regional variance."
        for field in entity["attributes"]:
            field_decision = entity_decision["attributes"][field["regionalId"]]
            if field["status"] != FULL_MATCH:
                field_decision["reason"] = "Approved best available ACORD field."
    for domain in proposal["domains"]:
        domain_decision = decisions["domains"][domain["regionalId"]]
        if domain["status"] != FULL_MATCH:
            domain_decision["reason"] = "Reviewed domain variance."
        for capability in domain["capabilities"]:
            capability_decision = domain_decision["capabilities"][capability["regionalId"]]
            if capability["status"] != FULL_MATCH:
                capability_decision["reason"] = "Reviewed capability variance."

    _approve_alignment_tree(decisions)
    assert validate_alignment_decisions(proposal, decisions) == []
    artifact = approve_acord_alignment(proposal, decisions)

    assert artifact["status"] == "Approved"
    assert artifact["summary"] == {
        "canonicalEntities": 1,
        "canonicalAttributes": 2,
        "canonicalEndpoints": 1,
        "canonicalDomains": 1,
        "canonicalCapabilities": 1,
    }
    canonical_entity = artifact["canonicalModel"]["entities"][0]
    assert canonical_entity["name"] == "Policy"
    assert canonical_entity["description"] == "Reviewer-approved policy description."
    assert canonical_entity["matchStatus"] == NOT_MATCHED
    assert canonical_entity["proposedMatchStatus"] == policy["status"]
    assert canonical_entity["comments"] == ["Use approved policy codes."]
    canonical_policy_number = canonical_entity["attributes"][0]
    assert canonical_policy_number["description"] == "Reviewed policy identifier."
    assert canonical_policy_number["matchStatus"] == "Partial match"
    assert canonical_policy_number["proposedMatchStatus"] == policy_number["status"]
    assert canonical_policy_number["constraints"] == {"minLength": 5}
    entity_mapping = next(
        item for item in artifact["alignmentMappings"] if item["kind"] == "Entity"
    )
    assert entity_mapping["status"] == NOT_MATCHED
    assert entity_mapping["proposedStatus"] == policy["status"]
    assert entity_mapping["description"] == "Reviewer-approved policy description."
    assert artifact["canonicalEndpoints"][0]["entities"] == [
        {"entity": "Policy", "usage": "Response 200"}
    ]


def test_no_candidate_requires_manual_name_and_artifacts_round_trip(tmp_path) -> None:
    proposal = propose_acord_alignment(
        region="EU",
        regional_source=_regional_source(),
        regional_domain_tree=_regional_domains(),
        regional_endpoints=_regional_endpoints(),
        acord_model={"source": {}, "entities": [], "endpoints": []},
        acord_run_id="b" * 32,
    )
    decisions = default_alignment_decisions(proposal)
    assert decisions["entities"]["regional-policy"]["selection"] == MANUAL
    assert any(
        "manual canonical name" in error
        for error in validate_alignment_decisions(proposal, decisions)
    )

    artifact = {"status": "Approved", "region": "EU"}
    save_alignment_artifact(tmp_path, "c" * 32, artifact)
    assert load_alignment_artifacts(tmp_path) == {"c" * 32: artifact}

    assert delete_alignment_artifact(tmp_path, "c" * 32) is True
    assert load_alignment_artifacts(tmp_path) == {}
    assert delete_alignment_artifact(tmp_path, "c" * 32) is False


def test_alignment_delete_rejects_unexpected_files(tmp_path) -> None:
    alignment_id = "e" * 32
    save_alignment_artifact(tmp_path, alignment_id, {"status": "Approved"})
    (tmp_path / alignment_id / "keep.txt").write_text("preserve", encoding="utf-8")

    with pytest.raises(OSError, match="unexpected files"):
        delete_alignment_artifact(tmp_path, alignment_id)

    assert (tmp_path / alignment_id / "canonical-alignment.json").is_file()
    assert (tmp_path / alignment_id / "keep.txt").is_file()


def test_later_region_uses_canonical_baseline_then_acord_and_reviews_generated_gap() -> None:
    baseline = {
        "region": "EU",
        "regions": ["EU"],
        "canonicalModel": {
            "entities": [
                {
                    "id": "canonical-policy",
                    "name": "Policy",
                    "description": "Approved EU policy.",
                    "attributes": [
                        {
                            "id": "canonical-policy-number",
                            "name": "policyNumber",
                            "description": "Approved policy number.",
                            "type": "string",
                            "constraints": {"minLength": 5},
                            "required": True,
                        }
                    ],
                    "sourceApis": ["EU Policy API"],
                }
            ]
        },
        "canonicalEndpoints": [
            {
                "api": "EU Policy API",
                "operation": "GetPolicy",
                "method": "GET",
                "route": "/eu/policies/{policyId}",
                "domain": "Policy",
                "capability": "Get a policy",
                "entities": [{"entity": "Policy", "usage": "Response 200"}],
                "description": "Returns an EU policy.",
            }
        ],
        "alignmentMappings": [],
    }
    proposal = propose_acord_alignment(
        region="US",
        regional_source=_regional_source(),
        regional_domain_tree=_regional_domains(),
        regional_endpoints=_regional_endpoints(),
        acord_model=_acord_model(),
        acord_run_id="d" * 32,
        canonical_baseline=baseline,
        baseline_version=4,
    )

    policy = proposal["entities"][0]
    assert policy["baselineCandidate"]["name"] == "Policy"
    assert policy["candidateSource"] == "Canonical baseline"
    policy_number = next(
        item for item in policy["attributes"] if item["regionalName"] == "policyNumber"
    )
    premium = next(item for item in policy["attributes"] if item["regionalName"] == "premiumAmount")
    assert policy_number["baselineCandidate"]["name"] == "policyNumber"
    assert premium["status"] == NOT_MATCHED

    proposal = attach_generated_gap_proposal(
        proposal,
        premium["regionalId"],
        {
            "name": "premiumAmount",
            "description": "Approved monetary premium for the policy.",
            "type": "decimal",
            "constraints": {"minimum": 0},
            "rationale": "No baseline or ACORD field represented this regional value.",
        },
    )
    decisions = default_alignment_decisions(proposal)
    assert decisions["entities"]["regional-policy"]["selection"] == USE_BASELINE
    premium_decision = decisions["entities"]["regional-policy"]["attributes"]["regional-premium"]
    assert premium_decision["selection"] == USE_GENERATED

    for entity in proposal["entities"]:
        entity_decision = decisions["entities"][entity["regionalId"]]
        if entity["status"] != FULL_MATCH:
            entity_decision["reason"] = "Reviewed against the approved baseline."
        for field in entity["attributes"]:
            field_decision = entity_decision["attributes"][field["regionalId"]]
            if field["status"] != FULL_MATCH:
                field_decision["reason"] = "Reviewer approved this regional gap."
    for domain in proposal["domains"]:
        domain_decision = decisions["domains"][domain["regionalId"]]
        if domain["status"] != FULL_MATCH:
            domain_decision["reason"] = "Reviewed domain variance."
        for capability in domain["capabilities"]:
            capability_decision = domain_decision["capabilities"][capability["regionalId"]]
            if capability["status"] != FULL_MATCH:
                capability_decision["reason"] = "Reviewed capability variance."

    _approve_alignment_tree(decisions)
    assert validate_alignment_decisions(proposal, decisions) == []
    artifact = approve_acord_alignment(proposal, decisions)
    assert artifact["regions"] == ["EU", "US"]
    assert artifact["baselineCanonicalVersion"] == 4
    assert artifact["summary"]["canonicalEntities"] == 1
    fields = artifact["canonicalModel"]["entities"][0]["attributes"]
    assert [item["name"] for item in fields] == ["policyNumber", "premiumAmount"]
    generated = next(item for item in fields if item["name"] == "premiumAmount")
    assert generated["description"] == "Approved monetary premium for the policy."
    assert generated["constraints"] == {"minimum": 0}
    assert artifact["summary"]["canonicalEndpoints"] == 2
