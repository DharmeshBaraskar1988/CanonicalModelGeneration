from __future__ import annotations

import json
from pathlib import Path

from canonical_model_generator.discovery_agent.model import DiscoveryModel
from canonical_model_generator.regional_catalog import (
    regional_catalog_rows,
    regional_domain_tree,
    regional_model_tree,
)


def test_regional_catalog_filters_region_and_maps_semantics() -> None:
    model = DiscoveryModel.model_validate_json(
        Path("tests/fixtures/discovery-model.valid.json").read_bytes()
    )
    eu = model.model_copy(update={"region": "EU", "system": "quote-api"})
    us = model.model_copy(update={"region": "US", "system": "claims-api"})
    operation = eu.operations[0]
    entity = eu.entities[0]
    metadata = {
        "endpoints": [
            {
                "operationId": operation.id,
                "domain": {"name": "Policy"},
                "capability": {"name": "Quote Management"},
                "summary": "Create a quote",
                "description": "Creates an insurance quote.",
                "businessPurpose": "Support quote issuance.",
                "confidence": 0.94,
            }
        ],
        "entities": [
            {
                "entityId": entity.id,
                "domain": {"name": "Policy"},
                "businessConcept": "Quote request",
                "summary": "Quote input",
                "description": "Input used to request a quote.",
                "confidence": 0.92,
                "attributes": [
                    {
                        "attributeId": entity.attributes[0].id,
                        "businessConcept": "Field concept",
                        "description": "Field description.",
                        "confidence": 0.91,
                    }
                ],
            }
        ],
    }
    runs = {
        "eu-quote": {
            "profile": {"region": "EU", "application": "quote-api"},
            "discovery_model": eu.model_dump_json(by_alias=True).encode(),
            "phase_2_artifacts": {"semantic-metadata.json": json.dumps(metadata).encode()},
        },
        "us-claims": {
            "profile": {"region": "US", "application": "claims-api"},
            "discovery_model": us.model_dump_json(by_alias=True).encode(),
            "phase_2_artifacts": {},
        },
    }

    models, endpoints = regional_catalog_rows(runs, region="EU")

    assert {row["API"] for row in models} == {"quote-api"}
    assert {row["API"] for row in endpoints} == {"quote-api"}
    assert endpoints[0]["Domain"] == "Policy"
    assert endpoints[0]["Capability"] == "Quote Management"
    assert endpoints[0]["Description"] == "Creates an insurance quote."
    assert endpoints[0]["Business purpose"] == "Support quote issuance."
    assert endpoints[0]["Confidence"] == 0.94
    assert any(row["Domain"] == "Policy" for row in models)
    tree = regional_model_tree(runs, region="EU")
    enriched_entity = next(branch for branch in tree[0]["models"] if branch["name"] == entity.name)
    assert enriched_entity["description"] == "Input used to request a quote."
    assert enriched_entity["businessConcept"] == "Quote request"
    assert any(field["Description"] == "Field description." for field in enriched_entity["fields"])


def test_regional_catalog_can_focus_on_one_api() -> None:
    model = DiscoveryModel.model_validate_json(
        Path("tests/fixtures/discovery-model.valid.json").read_bytes()
    ).model_copy(update={"region": "EU"})
    runs = {
        run_id: {
            "profile": {"region": "EU", "application": name},
            "discovery_model": model.model_copy(update={"system": name})
            .model_dump_json(by_alias=True)
            .encode(),
            "phase_2_artifacts": {},
        }
        for run_id, name in (("quote", "quote-api"), ("claim", "claim-api"))
    }

    _, endpoints = regional_catalog_rows(runs, region="EU", application_id="claim")

    assert {row["API"] for row in endpoints} == {"claim-api"}
    assert {row["Domain"] for row in endpoints} == {"Awaiting API Analyzer"}


def test_regional_model_tree_contains_api_models_fields_and_endpoint_mappings() -> None:
    model = DiscoveryModel.model_validate_json(
        Path("tests/fixtures/discovery-model.valid.json").read_bytes()
    ).model_copy(update={"region": "EU", "system": "quote-api"})
    runs = {
        "quote": {
            "profile": {
                "region": "EU",
                "application": "quote-api",
                "repository": "quote.zip",
            },
            "discovery_model": model.model_dump_json(by_alias=True).encode(),
            "phase_2_artifacts": {},
        }
    }

    tree = regional_model_tree(runs, region="EU")

    assert tree[0]["api"] == "quote-api"
    assert tree[0]["repository"] == "quote.zip"
    assert tree[0]["models"]
    assert tree[0]["models"][0]["fields"]
    assert any(branch["mappings"] for branch in tree[0]["models"])


def test_regional_domain_tree_groups_domain_capability_api_and_endpoints() -> None:
    model = DiscoveryModel.model_validate_json(
        Path("tests/fixtures/discovery-model.valid.json").read_bytes()
    ).model_copy(update={"region": "EU", "system": "quote-api"})
    operation = model.operations[0]
    metadata = {
        "endpoints": [
            {
                "operationId": operation.id,
                "domain": {"name": "Policy"},
                "capability": {"name": "Quote Management"},
                "confidence": 0.93,
            }
        ]
    }
    runs = {
        "quote": {
            "profile": {"region": "EU", "application": "quote-api"},
            "discovery_model": model.model_dump_json(by_alias=True).encode(),
            "phase_2_artifacts": {"semantic-metadata.json": json.dumps(metadata).encode()},
        }
    }

    tree = regional_domain_tree(runs, region="EU")

    policy = next(branch for branch in tree if branch["name"] == "Policy")
    capability = policy["capabilities"][0]
    assert capability["name"] == "Quote Management"
    assert capability["apis"][0]["name"] == "quote-api"
    assert capability["apis"][0]["endpoints"][0]["Endpoint"] == operation.name


def test_model_domain_falls_back_to_its_analyzed_endpoint_in_partial_run() -> None:
    model = DiscoveryModel.model_validate_json(
        Path("tests/fixtures/discovery-model.valid.json").read_bytes()
    ).model_copy(update={"region": "EU", "system": "quote-api"})
    operation = model.operations[0]
    metadata = {
        "endpoints": [
            {
                "operationId": operation.id,
                "domain": {"name": "Policy"},
                "capability": {"name": "Quote Management"},
            }
        ],
        "entities": [],
    }
    runs = {
        "partial": {
            "profile": {"region": "EU", "application": "quote-api"},
            "discovery_model": model.model_dump_json(by_alias=True).encode(),
            "phase_2_artifacts": {"semantic-metadata.json": json.dumps(metadata).encode()},
        }
    }

    rows, _ = regional_catalog_rows(runs, region="EU")
    request = next(row for row in rows if row["Model"] == model.entities[0].name)
    assert request["Domain"] == "Policy"
    tree = regional_model_tree(runs, region="EU")
    request_branch = next(
        item for item in tree[0]["models"] if item["name"] == model.entities[0].name
    )
    assert request_branch["domain"] == "Policy"
    assert request_branch["domainSource"] == "Analyzed endpoint mapping"


def test_all_api_view_hides_superseded_duplicate_application_run() -> None:
    model = DiscoveryModel.model_validate_json(
        Path("tests/fixtures/discovery-model.valid.json").read_bytes()
    ).model_copy(update={"region": "EU", "system": "insurance"})
    empty = model.model_copy(deep=True)
    empty.entities = []
    empty.enums = []
    empty.relationships = []
    empty.validations = []
    empty.evidence = []
    empty.lineage = []
    for operation in empty.operations:
        operation.request_entity_id = None
        for response in operation.responses:
            response.entity_id = None
    empty.summary.entity_count = 0
    profile = {
        "region": "EU",
        "application": "Insurance",
        "repository": "InsurancePortal.zip",
    }
    runs = {
        "old": {
            "profile": profile,
            "discovery_model": empty.model_dump_json(by_alias=True).encode(),
            "phase_2_artifacts": {},
        },
        "new": {
            "profile": profile,
            "discovery_model": model.model_dump_json(by_alias=True).encode(),
            "phase_2_artifacts": {},
        },
    }

    tree = regional_model_tree(runs, region="EU")

    assert len(tree) == 1
    assert tree[0]["runId"] == "new"
    assert len(tree[0]["models"]) == len(model.entities)
