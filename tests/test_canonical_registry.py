from __future__ import annotations

import json

import yaml

from canonical_model_generator.canonical_registry import (
    KEEP_ORIGINAL,
    REJECT,
    default_final_review,
    load_canonical_versions,
    submit_canonical_version,
)


def _artifact() -> dict:
    return {
        "status": "Approved",
        "region": "EU",
        "canonicalModel": {
            "entities": [
                {
                    "id": "entity-policy",
                    "name": "StandardPolicy",
                    "description": "Approved policy description.",
                    "attributes": [
                        {
                            "id": "attribute-number",
                            "name": "standardPolicyNumber",
                            "description": "Existing policy number description.",
                            "type": "string",
                            "required": True,
                            "constraints": {"minLength": 5, "maxLength": 20},
                        },
                        {
                            "id": "attribute-internal",
                            "name": "internalOnly",
                            "description": "Internal field.",
                            "type": "string",
                            "required": False,
                            "constraints": {},
                        },
                    ],
                }
            ]
        },
        "canonicalEndpoints": [
            {
                "api": "Policy API",
                "operation": "GetPolicy",
                "method": "GET",
                "route": "/policies/{policyId}",
                "domain": "StandardPolicyDomain",
                "capability": "ReadPolicy",
                "description": "Returns an existing policy.",
                "entities": [{"entity": "StandardPolicy", "usage": "Response 200"}],
            }
        ],
        "alignmentMappings": [
            {
                "kind": "Entity",
                "regional": "Policy",
                "canonical": "StandardPolicy",
            },
            {
                "kind": "Attribute",
                "regional": "Policy.policyNumber",
                "canonical": "StandardPolicy.standardPolicyNumber",
            },
            {
                "kind": "Attribute",
                "regional": "Policy.internalOnly",
                "canonical": "StandardPolicy.internalOnly",
            },
            {
                "kind": "Domain",
                "regional": "Policy",
                "canonical": "StandardPolicyDomain",
            },
            {
                "kind": "Capability",
                "regional": "Policy.Get policy",
                "canonical": "StandardPolicyDomain.ReadPolicy",
            },
        ],
    }


def test_final_review_versions_model_and_renders_openapi_json_and_yaml(tmp_path) -> None:
    artifact = _artifact()
    review = default_final_review(artifact)
    review["entities"]["entity-policy"] = KEEP_ORIGINAL
    review["attributes"]["attribute-number"] = KEEP_ORIGINAL
    review["attributes"]["attribute-internal"] = REJECT
    review["domains"]["StandardPolicyDomain"] = KEEP_ORIGINAL
    review["capabilities"]["StandardPolicyDomain.ReadPolicy"] = KEEP_ORIGINAL
    database = tmp_path / "canonical.sqlite3"

    first = submit_canonical_version(
        database, alignment_id="alignment-one", artifact=artifact, review=review
    )
    second = submit_canonical_version(
        database, alignment_id="alignment-one", artifact=artifact, review=review
    )
    third = submit_canonical_version(
        database,
        alignment_id="alignment-two",
        artifact=artifact,
        review=default_final_review(artifact),
    )

    assert first["version"] == 1
    assert second["version"] == 2
    assert third["version"] == 3
    versions = load_canonical_versions(database)
    assert [item["version"] for item in versions] == [3, 2, 1]
    assert [item["alignmentId"] for item in versions] == [
        "alignment-two",
        "alignment-one",
        "alignment-one",
    ]
    assert third["artifact"]["canonicalModel"]["entities"][0]["name"] == "StandardPolicy"
    final_entity = first["artifact"]["canonicalModel"]["entities"][0]
    assert final_entity["name"] == "Policy"
    assert [item["name"] for item in final_entity["attributes"]] == ["policyNumber"]
    openapi_json = json.loads(first["openapiJson"])
    openapi_yaml = yaml.safe_load(first["openapiYaml"])
    for document in (openapi_json, openapi_yaml):
        assert document["openapi"] == "3.0.3"
        schema = document["components"]["schemas"]["Policy"]
        field = schema["properties"]["policyNumber"]
        assert field["description"] == "Existing policy number description."
        assert field["minLength"] == 5
        assert field["maxLength"] == 20
        operation = document["paths"]["/policies/{policyId}"]["get"]
        assert operation["x-domain"] == "Policy"
        assert operation["x-capability"] == "Get policy"
        assert operation["parameters"] == [
            {
                "name": "policyId",
                "in": "path",
                "required": True,
                "schema": {"type": "string"},
            }
        ]
        assert operation["responses"]["200"]["content"]["application/json"]["schema"] == {
            "$ref": "#/components/schemas/Policy"
        }


def test_final_review_rejects_inventory_changes(tmp_path) -> None:
    artifact = _artifact()
    review = default_final_review(artifact)
    del review["entities"]["entity-policy"]

    try:
        submit_canonical_version(
            tmp_path / "canonical.sqlite3",
            alignment_id="alignment-one",
            artifact=artifact,
            review=review,
        )
    except ValueError as exc:
        assert "inventory" in str(exc)
    else:
        raise AssertionError("Expected mismatched review inventory to fail")
