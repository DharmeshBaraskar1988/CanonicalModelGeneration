"""Read-only regional catalog projections over completed application runs."""

from __future__ import annotations

import json
from typing import Any

from canonical_model_generator.discovery_agent.model import DiscoveryModel


def regional_catalog_rows(
    application_runs: dict[str, dict[str, Any]],
    *,
    region: str,
    application_id: str | None = None,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Build model and endpoint rows without changing any source artifacts."""
    model_rows: list[dict[str, Any]] = []
    endpoint_rows: list[dict[str, Any]] = []

    for run_id, run in sorted(application_runs.items()):
        profile = run.get("profile", {})
        if profile.get("region") != region or (application_id and run_id != application_id):
            continue
        artifact = run.get("discovery_model")
        if not artifact:
            continue
        model = DiscoveryModel.model_validate_json(artifact)
        entity_usage: dict[str, list[tuple[str, str]]] = {item.id: [] for item in model.entities}
        for operation in model.operations:
            if operation.request_entity_id in entity_usage:
                entity_usage[operation.request_entity_id].append((operation.name, "Request"))
            for response in operation.responses:
                if response.entity_id in entity_usage:
                    entity_usage[response.entity_id].append(
                        (operation.name, f"Response {response.status_code}")
                    )

        semantics = _semantic_endpoints(run.get("phase_2_artifacts", {}))
        for operation in model.operations:
            semantic = semantics.get(operation.id, {})
            domain = semantic.get("domain", {})
            capability = semantic.get("capability", {})
            endpoint_rows.append(
                {
                    "Region": model.region,
                    "API": profile.get("application", model.system),
                    "Endpoint": operation.name,
                    "Method": operation.method.upper(),
                    "Route": operation.route,
                    "Domain": domain.get("name", "Awaiting API Analyzer"),
                    "Capability": capability.get("name", "Awaiting API Analyzer"),
                    "Summary": semantic.get("summary", "Awaiting API Analyzer"),
                    "Description": semantic.get("description", "Awaiting API Analyzer"),
                    "Business purpose": semantic.get("businessPurpose", "Awaiting API Analyzer"),
                    "Confidence": semantic.get("confidence"),
                }
            )

        for entity in model.entities:
            usage = sorted(set(entity_usage[entity.id]))
            model_rows.append(
                {
                    "Region": model.region,
                    "API": profile.get("application", model.system),
                    "Model": entity.name,
                    "Fields": len(entity.attributes),
                    "Endpoint mapping": ", ".join(name for name, _ in usage) or "Not linked",
                    "Usage": ", ".join(role for _, role in usage) or "Not linked",
                    "Domain": _entity_domain(run.get("phase_2_artifacts", {}), entity.id),
                }
            )

    model_rows.sort(key=lambda row: (row["API"].lower(), row["Model"].lower()))
    endpoint_rows.sort(key=lambda row: (row["API"].lower(), row["Route"].lower(), row["Method"]))
    return model_rows, endpoint_rows


def regional_model_tree(
    application_runs: dict[str, dict[str, Any]],
    *,
    region: str,
    application_id: str | None = None,
) -> list[dict[str, Any]]:
    """Build a Region -> API -> model -> endpoint/field hierarchy for display."""
    branches: list[dict[str, Any]] = []
    for run_id, run in sorted(application_runs.items()):
        profile = run.get("profile", {})
        if profile.get("region") != region or (application_id and run_id != application_id):
            continue
        artifact = run.get("discovery_model")
        if not artifact:
            continue
        discovery = DiscoveryModel.model_validate_json(artifact)
        semantic_entities = _semantic_entities(run.get("phase_2_artifacts", {}))
        entity_usage: dict[str, list[dict[str, str]]] = {
            entity.id: [] for entity in discovery.entities
        }
        for operation in discovery.operations:
            if operation.request_entity_id in entity_usage:
                entity_usage[operation.request_entity_id].append(
                    {
                        "Endpoint": operation.name,
                        "Method": operation.method.upper(),
                        "Route": operation.route,
                        "Usage": "Request",
                    }
                )
            for response in operation.responses:
                if response.entity_id in entity_usage:
                    entity_usage[response.entity_id].append(
                        {
                            "Endpoint": operation.name,
                            "Method": operation.method.upper(),
                            "Route": operation.route,
                            "Usage": f"Response {response.status_code}",
                        }
                    )

        models = []
        for entity in sorted(discovery.entities, key=lambda item: item.name.casefold()):
            semantic = semantic_entities.get(entity.id, {})
            semantic_attributes = {
                item["attributeId"]: item
                for item in semantic.get("attributes", [])
                if isinstance(item, dict) and item.get("attributeId")
            }
            fields = [
                {
                    "id": attribute.id,
                    "Field": attribute.name,
                    "Type": _display_type(attribute.type),
                    "Required": attribute.required,
                    "Business concept": semantic_attributes.get(attribute.id, {}).get(
                        "businessConcept", "Awaiting API Analyzer"
                    ),
                    "Description": semantic_attributes.get(attribute.id, {}).get(
                        "description", "Awaiting API Analyzer"
                    ),
                    "Confidence": semantic_attributes.get(attribute.id, {}).get("confidence"),
                }
                for attribute in sorted(entity.attributes, key=lambda item: item.name.casefold())
            ]
            models.append(
                {
                    "id": entity.id,
                    "name": entity.name,
                    "domain": semantic.get("domain", {}).get("name", "Awaiting API Analyzer"),
                    "businessConcept": semantic.get("businessConcept", "Awaiting API Analyzer"),
                    "summary": semantic.get("summary", "Awaiting API Analyzer"),
                    "description": semantic.get("description", "Awaiting API Analyzer"),
                    "confidence": semantic.get("confidence"),
                    "fields": fields,
                    "mappings": sorted(
                        entity_usage[entity.id],
                        key=lambda item: (
                            item["Route"].casefold(),
                            item["Method"],
                            item["Usage"],
                        ),
                    ),
                }
            )
        branches.append(
            {
                "runId": run_id,
                "api": profile.get("application", discovery.system),
                "repository": profile.get("repository", "Not recorded"),
                "models": models,
            }
        )
    branches.sort(key=lambda item: (item["api"].casefold(), item["runId"]))
    return branches


def regional_domain_tree(
    application_runs: dict[str, dict[str, Any]],
    *,
    region: str,
    application_id: str | None = None,
) -> list[dict[str, Any]]:
    """Build a Region -> domain -> capability -> API -> endpoint hierarchy."""
    _, endpoint_rows = regional_catalog_rows(
        application_runs, region=region, application_id=application_id
    )
    grouped: dict[str, dict[str, dict[str, list[dict[str, Any]]]]] = {}
    for row in endpoint_rows:
        endpoint = {
            "Endpoint": row["Endpoint"],
            "Method": row["Method"],
            "Route": row["Route"],
            "Summary": row["Summary"],
            "Description": row["Description"],
            "Business purpose": row["Business purpose"],
            "Confidence": row["Confidence"],
        }
        grouped.setdefault(row["Domain"], {}).setdefault(row["Capability"], {}).setdefault(
            row["API"], []
        ).append(endpoint)

    return [
        {
            "name": domain,
            "capabilities": [
                {
                    "name": capability,
                    "apis": [
                        {
                            "name": api,
                            "endpoints": sorted(
                                endpoints,
                                key=lambda item: (
                                    item["Route"].casefold(),
                                    item["Method"],
                                ),
                            ),
                        }
                        for api, endpoints in sorted(
                            apis.items(), key=lambda item: item[0].casefold()
                        )
                    ],
                }
                for capability, apis in sorted(
                    capabilities.items(), key=lambda item: item[0].casefold()
                )
            ],
        }
        for domain, capabilities in sorted(grouped.items(), key=lambda item: item[0].casefold())
    ]


def _display_type(type_ref: Any) -> str:
    name = type_ref.name
    if type_ref.collection:
        name = f"List[{name}]"
    if type_ref.nullable:
        name += "?"
    return name


def _semantic_metadata(artifacts: dict[str, bytes]) -> dict[str, Any]:
    content = artifacts.get("semantic-metadata.json")
    if not content:
        return {}
    try:
        return json.loads(content)
    except (json.JSONDecodeError, TypeError, UnicodeDecodeError):
        return {}


def _semantic_endpoints(artifacts: dict[str, bytes]) -> dict[str, dict[str, Any]]:
    metadata = _semantic_metadata(artifacts)
    return {
        item["operationId"]: item
        for item in metadata.get("endpoints", [])
        if isinstance(item, dict) and item.get("operationId")
    }


def _semantic_entities(artifacts: dict[str, bytes]) -> dict[str, dict[str, Any]]:
    metadata = _semantic_metadata(artifacts)
    return {
        item["entityId"]: item
        for item in metadata.get("entities", [])
        if isinstance(item, dict) and item.get("entityId")
    }


def _entity_domain(artifacts: dict[str, bytes], entity_id: str) -> str:
    semantic = _semantic_entities(artifacts).get(entity_id, {})
    return semantic.get("domain", {}).get("name", "Awaiting API Analyzer")
