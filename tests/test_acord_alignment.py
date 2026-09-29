from __future__ import annotations

from canonical_model_generator.acord_alignment import (
    FULL_MATCH,
    MANUAL,
    NOT_MATCHED,
    approve_acord_alignment,
    default_alignment_decisions,
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
    assert validate_alignment_decisions(proposal, decisions)

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
    assert canonical_entity["comments"] == ["Use approved policy codes."]
    assert canonical_entity["attributes"][0]["constraints"] == {"minLength": 5}
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
