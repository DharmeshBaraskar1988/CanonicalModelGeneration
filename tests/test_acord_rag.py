from __future__ import annotations

import json
from pathlib import Path

import yaml

from canonical_model_generator.acord_rag import (
    ACORD_ARTIFACTS,
    AcordDocumentIndex,
    build_acord_chunks,
    generate_acord_artifacts,
    parse_acord_document,
)
from canonical_model_generator.acord_rag.history import load_acord_records, save_acord_record
from canonical_model_generator.repository_rag.embeddings import EmbeddingConfig


def _document() -> bytes:
    return yaml.safe_dump(
        {
            "openapi": "3.0.3",
            "info": {
                "title": "ACORD policy reference",
                "version": "2026.1",
                "description": "Approved policy contract reference.",
                "x-comment": "Use the published code lists.",
            },
            "paths": {
                "/policies/{policyId}": {
                    "parameters": [
                        {
                            "name": "policyId",
                            "in": "path",
                            "required": True,
                            "description": "Stable policy identifier.",
                            "schema": {"type": "string", "pattern": "^[A-Z0-9]+$"},
                        }
                    ],
                    "get": {
                        "operationId": "getPolicy",
                        "summary": "Get a policy",
                        "description": "Returns the complete policy record.",
                        "x-comment": "Includes the insured mailing address.",
                        "responses": {
                            "200": {
                                "description": "Policy found.",
                                "content": {
                                    "application/json": {
                                        "schema": {"$ref": "#/components/schemas/Policy"}
                                    }
                                },
                            }
                        },
                    },
                }
            },
            "components": {
                "schemas": {
                    "Policy": {
                        "type": "object",
                        "description": "An insurance policy.",
                        "$comment": "Reference object, not a regional canonical entity.",
                        "required": ["policyNumber", "insured"],
                        "properties": {
                            "policyNumber": {
                                "type": "string",
                                "description": "Policy number shown to customers.",
                                "minLength": 5,
                                "maxLength": 20,
                            },
                            "insured": {
                                "type": "object",
                                "description": "The named insured.",
                                "properties": {
                                    "name": {
                                        "type": "string",
                                        "description": "Full legal name.",
                                    },
                                    "address": {
                                        "type": "object",
                                        "description": "Mailing address.",
                                        "properties": {
                                            "postalCode": {
                                                "type": "string",
                                                "description": "Postal code.",
                                                "pattern": "^[0-9]{5}$",
                                            }
                                        },
                                    },
                                },
                            },
                        },
                    }
                }
            },
        },
        sort_keys=False,
    ).encode()


class FakeEmbedder:
    config = EmbeddingConfig()

    def embed(self, texts: list[str]) -> list[list[float]]:
        return [
            [
                float("policy" in text.casefold()),
                float("address" in text.casefold()),
                1.0,
            ]
            for text in texts
        ]


def test_acord_ingestion_extracts_nested_models_semantics_constraints_and_artifacts():
    model = parse_acord_document(
        _document(),
        "acord-policy.yaml",
        reference_label="ACORD policy",
        reference_version="2026.1",
    )

    assert model["summary"] == {
        "endpointCount": 1,
        "entityCount": 3,
        "attributeCount": 5,
        "enumCount": 0,
        "relationshipCount": 8,
        "validationCount": 5,
        "diagnosticCount": 0,
    }
    assert [item["name"] for item in model["entities"]] == [
        "Policy",
        "Policy.insured",
        "Policy.insured.address",
    ]
    policy = next(item for item in model["entities"] if item["name"] == "Policy")
    assert policy["description"] == "An insurance policy."
    assert policy["comments"] == ["Reference object, not a regional canonical entity."]
    number = next(item for item in policy["attributes"] if item["name"] == "policyNumber")
    assert number["constraints"] == {"required": True, "minLength": 5, "maxLength": 20}
    endpoint = model["endpoints"][0]
    assert endpoint["summary"] == "Get a policy"
    assert endpoint["comments"] == ["Includes the insured mailing address."]
    assert endpoint["parameters"][0]["constraints"] == {
        "required": True,
        "pattern": "^[A-Z0-9]+$",
    }

    artifacts = generate_acord_artifacts(model)
    assert set(artifacts) == set(ACORD_ARTIFACTS)
    catalog = json.loads(artifacts["API Catalog"])
    assert (
        catalog["operations"][0]["responses"][0]["bodies"][0]["modelTree"]["rootModel"] == "Policy"
    )
    assert len(catalog["operations"][0]["responses"][0]["bodies"][0]["modelTree"]["models"]) == 3
    data_model = json.loads(artifacts["Data Model"])
    assert data_model["entities"][0]["fields"][0]["description"]

    chunks = build_acord_chunks(model)
    endpoint_chunk = next(item for item in chunks if item["kind"] == "endpoint")
    policy_chunk = next(
        item for item in chunks if item["kind"] == "entity" and "Entity Policy\n" in item["text"]
    )
    assert "Returns the complete policy record" in endpoint_chunk["text"]
    assert "Response 200: Policy found" in endpoint_chunk["text"]
    assert "Policy number shown to customers" in policy_chunk["text"]
    assert '"maxLength":20' in policy_chunk["text"]


def test_acord_rag_is_persistent_and_retrieves_meaningful_chunks(tmp_path: Path):
    content = _document()
    model = parse_acord_document(
        content,
        "acord-policy.yaml",
        reference_label="ACORD policy",
        reference_version="2026.1",
    )
    artifacts = generate_acord_artifacts(model)
    chunks = build_acord_chunks(model)
    run_id = "a" * 32
    run_path = save_acord_record(
        tmp_path,
        run_id,
        model=model,
        artifacts=artifacts,
        source_content=content,
    )
    index = AcordDocumentIndex(run_path / "index", FakeEmbedder())
    stats = index.ingest(model, chunks)
    results = index.query("insured address")
    index.close()

    assert stats["endpointChunks"] == 1
    assert stats["entityChunks"] == 3
    assert results
    assert "address" in results[0]["text"].casefold()
    loaded = load_acord_records(tmp_path)
    assert loaded[run_id]["profile"]["referenceVersion"] == "2026.1"
    assert loaded[run_id]["manifest"]["stats"] == stats


def test_acord_ingestion_rejects_non_openapi_documents():
    try:
        parse_acord_document(
            b'{"type":"object"}',
            "schema.json",
            reference_label="ACORD",
            reference_version="1",
        )
    except ValueError as exc:
        assert "OpenAPI 3.x" in str(exc)
    else:
        raise AssertionError("Expected a validation error")
