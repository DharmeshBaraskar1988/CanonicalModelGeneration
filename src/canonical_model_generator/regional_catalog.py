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

    for run_id, run in _selected_application_runs(application_runs, region, application_id):
        profile = run.get("profile", {})
        artifact = run.get("discovery_model")
        if not artifact:
            continue
        model = DiscoveryModel.model_validate_json(artifact)
        entity_usage: dict[str, list[tuple[str, str, str]]] = {
            item.id: [] for item in model.entities
        }
        for operation in model.operations:
            if operation.request_entity_id in entity_usage:
                entity_usage[operation.request_entity_id].append(
                    (operation.id, operation.name, "Request")
                )
            for response in operation.responses:
                if response.entity_id in entity_usage:
                    entity_usage[response.entity_id].append(
                        (operation.id, operation.name, f"Response {response.status_code}")
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
            entity_domain, _ = _entity_domain(
                run.get("phase_2_artifacts", {}), entity.id, usage, semantics
            )
            model_rows.append(
                {
                    "Region": model.region,
                    "API": profile.get("application", model.system),
                    "Model": entity.name,
                    "Fields": len(entity.attributes),
                    "Endpoint mapping": ", ".join(name for _, name, _ in usage) or "Not linked",
                    "Usage": ", ".join(role for _, _, role in usage) or "Not linked",
                    "Domain": entity_domain,
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
    for run_id, run in _selected_application_runs(application_runs, region, application_id):
        profile = run.get("profile", {})
        artifact = run.get("discovery_model")
        if not artifact:
            continue
        discovery = DiscoveryModel.model_validate_json(artifact)
        semantic_entities = _semantic_entities(run.get("phase_2_artifacts", {}))
        semantic_endpoints = _semantic_endpoints(run.get("phase_2_artifacts", {}))
        entity_usage: dict[str, list[dict[str, str]]] = {
            entity.id: [] for entity in discovery.entities
        }
        for operation in discovery.operations:
            if operation.request_entity_id in entity_usage:
                entity_usage[operation.request_entity_id].append(
                    {
                        "OperationId": operation.id,
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
                            "OperationId": operation.id,
                            "Endpoint": operation.name,
                            "Method": operation.method.upper(),
                            "Route": operation.route,
                            "Usage": f"Response {response.status_code}",
                        }
                    )

        models = []
        for entity in sorted(discovery.entities, key=lambda item: item.name.casefold()):
            semantic = semantic_entities.get(entity.id, {})
            usage = entity_usage[entity.id]
            entity_domain, domain_source = _entity_domain(
                run.get("phase_2_artifacts", {}),
                entity.id,
                [(item["OperationId"], item["Endpoint"], item["Usage"]) for item in usage],
                semantic_endpoints,
            )
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
                    "domain": entity_domain,
                    "domainSource": domain_source,
                    "businessConcept": semantic.get("businessConcept", "Awaiting API Analyzer"),
                    "summary": semantic.get("summary", "Awaiting API Analyzer"),
                    "description": semantic.get("description", "Awaiting API Analyzer"),
                    "confidence": semantic.get("confidence"),
                    "fields": fields,
                    "mappings": sorted(
                        [
                            {key: value for key, value in item.items() if key != "OperationId"}
                            for item in usage
                        ],
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


def _selected_application_runs(
    application_runs: dict[str, dict[str, Any]],
    region: str,
    application_id: str | None,
) -> list[tuple[str, dict[str, Any]]]:
    eligible = [
        (run_id, run)
        for run_id, run in application_runs.items()
        if run.get("profile", {}).get("region") == region
        and (application_id is None or run_id == application_id)
    ]
    if application_id is not None:
        return sorted(eligible)

    selected: dict[tuple[str, str, str], tuple[str, dict[str, Any]]] = {}
    for run_id, run in eligible:
        profile = run.get("profile", {})
        identity = (
            region,
            str(profile.get("application", "")).casefold(),
            str(profile.get("repository", "")).casefold(),
        )
        current = selected.get(identity)
        if current is None or _run_quality(run_id, run) > _run_quality(*current):
            selected[identity] = (run_id, run)
    return sorted(selected.values())


def _run_quality(run_id: str, run: dict[str, Any]) -> tuple[int, int, int, str]:
    metadata = _semantic_metadata(run.get("phase_2_artifacts", {}))
    try:
        entity_count = len(
            DiscoveryModel.model_validate_json(run.get("discovery_model", b"{}")).entities
        )
    except (TypeError, ValueError):
        entity_count = 0
    return (
        len(metadata.get("entities", [])),
        len(metadata.get("endpoints", [])),
        entity_count,
        run_id,
    )


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


def _entity_domain(
    artifacts: dict[str, bytes],
    entity_id: str,
    usage: list[tuple[str, str, str]],
    endpoint_semantics: dict[str, dict[str, Any]],
) -> tuple[str, str]:
    semantic = _semantic_entities(artifacts).get(entity_id, {})
    semantic_domain = semantic.get("domain", {}).get("name")
    if semantic_domain:
        return semantic_domain, "Entity analysis"
    linked_domains = sorted(
        {
            endpoint_semantics.get(operation_id, {}).get("domain", {}).get("name")
            for operation_id, _, _ in usage
        }
        - {None}
    )
    if len(linked_domains) == 1:
        return linked_domains[0], "Analyzed endpoint mapping"
    if len(linked_domains) > 1:
        return "Multiple analyzed domains", "Analyzed endpoint mappings"
    return "Awaiting API Analyzer", "Entity analysis pending"
