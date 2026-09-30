"""Versioned final canonical-model review and OpenAPI publication."""

from __future__ import annotations

import json
import re
import sqlite3
from copy import deepcopy
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import yaml

USE_CANONICAL = "Use canonical"
KEEP_ORIGINAL = "Keep regional original"
REJECT = "Reject"
REVIEW_ACTIONS = (USE_CANONICAL, KEEP_ORIGINAL, REJECT)


def default_final_review(artifact: dict[str, Any]) -> dict[str, dict[str, str]]:
    """Return explicit defaults for every reviewable canonical item."""
    review: dict[str, dict[str, str]] = {
        "entities": {},
        "attributes": {},
        "domains": {},
        "capabilities": {},
    }
    mappings = _mapping_index(artifact)
    for entity in artifact["canonicalModel"]["entities"]:
        review["entities"][entity["id"]] = USE_CANONICAL
        for attribute in entity["attributes"]:
            review["attributes"][attribute["id"]] = USE_CANONICAL
    for mapping in artifact.get("alignmentMappings", []):
        kind = mapping.get("kind")
        if kind == "Domain":
            review["domains"][str(mapping["canonical"])] = USE_CANONICAL
        elif kind == "Capability":
            review["capabilities"][str(mapping["canonical"])] = USE_CANONICAL
    # Ensure malformed/legacy mappings cannot silently change the review inventory.
    if not mappings:
        review["domains"] = {}
        review["capabilities"] = {}
    return review


def submit_canonical_version(
    database: Path,
    *,
    alignment_id: str,
    artifact: dict[str, Any],
    review: dict[str, dict[str, str]],
) -> dict[str, Any]:
    """Append one immutable reviewed model version and its OpenAPI representations."""
    _validate_review(artifact, review)
    final_artifact = _apply_review(artifact, review)
    openapi = render_canonical_openapi(final_artifact)
    created_at = datetime.now(UTC).isoformat()
    database.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(database) as connection:
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS canonical_model_versions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                version_number INTEGER NOT NULL UNIQUE,
                created_at TEXT NOT NULL,
                region TEXT NOT NULL,
                alignment_id TEXT NOT NULL,
                artifact_json TEXT NOT NULL,
                openapi_json TEXT NOT NULL,
                openapi_yaml TEXT NOT NULL
            )
            """
        )
        version = connection.execute(
            "SELECT COALESCE(MAX(version_number), 0) + 1 FROM canonical_model_versions"
        ).fetchone()[0]
        final_artifact["canonicalVersion"] = version
        final_artifact["submittedAt"] = created_at
        openapi["info"]["version"] = str(version)
        openapi_json = json.dumps(openapi, indent=2, sort_keys=True) + "\n"
        openapi_yaml = yaml.safe_dump(openapi, sort_keys=False, allow_unicode=True)
        connection.execute(
            """
            INSERT INTO canonical_model_versions
                (version_number, created_at, region, alignment_id,
                 artifact_json, openapi_json, openapi_yaml)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                version,
                created_at,
                final_artifact["region"],
                alignment_id,
                json.dumps(final_artifact, sort_keys=True),
                openapi_json,
                openapi_yaml,
            ),
        )
    return {
        "version": version,
        "createdAt": created_at,
        "alignmentId": alignment_id,
        "artifact": final_artifact,
        "openapiJson": openapi_json.encode(),
        "openapiYaml": openapi_yaml.encode(),
    }


def load_canonical_versions(database: Path) -> list[dict[str, Any]]:
    """Load submitted versions newest first."""
    if not database.is_file():
        return []
    with sqlite3.connect(database) as connection:
        rows = connection.execute(
            """
            SELECT version_number, created_at, alignment_id,
                   artifact_json, openapi_json, openapi_yaml
            FROM canonical_model_versions ORDER BY version_number DESC
            """
        ).fetchall()
    return [
        {
            "version": row[0],
            "createdAt": row[1],
            "alignmentId": row[2],
            "artifact": json.loads(row[3]),
            "openapiJson": row[4].encode(),
            "openapiYaml": row[5].encode(),
        }
        for row in rows
    ]


def render_canonical_openapi(artifact: dict[str, Any]) -> dict[str, Any]:
    """Render standard OpenAPI structure from one submitted canonical snapshot."""
    entities = artifact["canonicalModel"]["entities"]
    schemas = {entity["name"]: _entity_schema(entity) for entity in entities}
    paths: dict[str, Any] = {}
    for endpoint in artifact.get("canonicalEndpoints", []):
        operation: dict[str, Any] = {
            "operationId": endpoint["operation"],
            "summary": endpoint.get("description") or endpoint["operation"],
            "description": endpoint.get("description") or endpoint["operation"],
            "tags": [endpoint["domain"]] if endpoint.get("domain") else [],
            "x-domain": endpoint.get("domain"),
            "x-capability": endpoint.get("capability"),
            "responses": {},
        }
        path_parameters = re.findall(r"\{([^{}]+)\}", endpoint["route"])
        if path_parameters:
            operation["parameters"] = [
                {
                    "name": name,
                    "in": "path",
                    "required": True,
                    "schema": {"type": "string"},
                }
                for name in path_parameters
            ]
        for usage in endpoint.get("entities", []):
            entity_name = usage["entity"]
            if entity_name not in schemas:
                continue
            usage_text = str(usage.get("usage", ""))
            schema = {"$ref": f"#/components/schemas/{entity_name}"}
            if usage_text.casefold().startswith("request"):
                operation["requestBody"] = {
                    "required": True,
                    "content": {"application/json": {"schema": schema}},
                }
            else:
                status = next((part for part in usage_text.split() if part.isdigit()), "200")
                operation["responses"][status] = {
                    "description": endpoint.get("description") or "Response",
                    "content": {"application/json": {"schema": schema}},
                }
        if not operation["responses"]:
            operation["responses"]["200"] = {"description": "Successful response"}
        paths.setdefault(endpoint["route"], {})[endpoint["method"].lower()] = operation
    regions = artifact.get("regions") or [artifact["region"]]
    region_label = " + ".join(str(region) for region in regions)
    return {
        "openapi": "3.0.3",
        "info": {
            "title": f"{region_label} approved canonical API",
            "version": str(artifact.get("canonicalVersion", "draft")),
            "description": "Generated from a reviewed, versioned canonical model.",
        },
        "servers": [{"url": "/"}],
        "paths": paths,
        "components": {"schemas": schemas},
    }


def _validate_review(artifact: dict[str, Any], review: dict[str, dict[str, str]]) -> None:
    expected = default_final_review(artifact)
    for section, items in expected.items():
        supplied = review.get(section, {})
        if set(supplied) != set(items):
            raise ValueError(f"Final review {section} inventory does not match the approved model")
        invalid = {value for value in supplied.values() if value not in REVIEW_ACTIONS}
        if invalid:
            raise ValueError(f"Unsupported final review action: {sorted(invalid)[0]}")


def _apply_review(artifact: dict[str, Any], review: dict[str, dict[str, str]]) -> dict[str, Any]:
    result = deepcopy(artifact)
    mappings = _mapping_index(artifact)
    entity_renames: dict[str, str | None] = {}
    kept_entities = []
    for entity in result["canonicalModel"]["entities"]:
        action = review["entities"][entity["id"]]
        mapping = mappings.get(("Entity", entity["name"]), {})
        original_name = str(mapping.get("regional") or entity["name"])
        final_name = (
            None
            if action == REJECT
            else original_name
            if action == KEEP_ORIGINAL
            else entity["name"]
        )
        entity_renames[entity["name"]] = final_name
        if final_name is None:
            continue
        entity["name"] = final_name
        entity["finalReviewAction"] = action
        kept_attributes = []
        for attribute in entity["attributes"]:
            attribute_action = review["attributes"][attribute["id"]]
            attribute_mapping = mappings.get(
                ("Attribute", f"{mapping.get('canonical', final_name)}.{attribute['name']}"), {}
            )
            if attribute_action == REJECT:
                continue
            if attribute_action == KEEP_ORIGINAL:
                regional = str(attribute_mapping.get("regional") or attribute["name"])
                attribute["name"] = regional.rsplit(".", 1)[-1]
            attribute["finalReviewAction"] = attribute_action
            kept_attributes.append(attribute)
        entity["attributes"] = kept_attributes
        kept_entities.append(entity)
    result["canonicalModel"]["entities"] = kept_entities

    domain_renames: dict[str, str | None] = {}
    capability_renames: dict[str, str | None] = {}
    for mapping in result.get("alignmentMappings", []):
        kind = mapping.get("kind")
        canonical = str(mapping.get("canonical", ""))
        if kind == "Domain":
            action = review["domains"][canonical]
            domain_renames[canonical] = (
                None
                if action == REJECT
                else str(mapping["regional"])
                if action == KEEP_ORIGINAL
                else canonical
            )
        elif kind == "Capability":
            action = review["capabilities"][canonical]
            capability_renames[canonical] = (
                None
                if action == REJECT
                else str(mapping["regional"]).rsplit(".", 1)[-1]
                if action == KEEP_ORIGINAL
                else canonical.rsplit(".", 1)[-1]
            )

    endpoints = []
    for endpoint in result.get("canonicalEndpoints", []):
        domain = domain_renames.get(endpoint.get("domain"), endpoint.get("domain"))
        capability_key = f"{endpoint.get('domain')}.{endpoint.get('capability')}"
        capability = capability_renames.get(capability_key, endpoint.get("capability"))
        if domain is None or capability is None:
            continue
        endpoint["domain"] = domain
        endpoint["capability"] = capability
        endpoint["entities"] = [
            {**item, "entity": entity_renames[item["entity"]]}
            for item in endpoint.get("entities", [])
            if entity_renames.get(item["entity"]) is not None
        ]
        endpoints.append(endpoint)
    result["canonicalEndpoints"] = endpoints
    result["finalReview"] = deepcopy(review)
    result["summary"] = {
        "canonicalEntities": len(kept_entities),
        "canonicalAttributes": sum(len(item["attributes"]) for item in kept_entities),
        "canonicalEndpoints": len(endpoints),
        "canonicalDomains": len({item["domain"] for item in endpoints}),
        "canonicalCapabilities": len({(item["domain"], item["capability"]) for item in endpoints}),
    }
    return result


def _mapping_index(artifact: dict[str, Any]) -> dict[tuple[str, str], dict[str, Any]]:
    return {
        (str(item.get("kind")), str(item.get("canonical"))): item
        for item in artifact.get("alignmentMappings", [])
    }


def _entity_schema(entity: dict[str, Any]) -> dict[str, Any]:
    properties: dict[str, Any] = {}
    required = []
    for attribute in entity["attributes"]:
        schema = _type_schema(str(attribute.get("type", "string")))
        schema.update(deepcopy(attribute.get("constraints", {})))
        if attribute.get("description"):
            schema["description"] = attribute["description"]
        properties[attribute["name"]] = schema
        if attribute.get("required"):
            required.append(attribute["name"])
    schema: dict[str, Any] = {
        "type": "object",
        "description": entity.get("description") or entity["name"],
        "properties": properties,
    }
    if required:
        schema["required"] = required
    return schema


def _type_schema(value: str) -> dict[str, Any]:
    normalized = value.casefold().replace("?", "")
    if normalized in {"integer", "int", "int32", "int64", "long"}:
        return {"type": "integer"}
    if normalized in {"number", "decimal", "float", "double"}:
        return {"type": "number"}
    if normalized in {"boolean", "bool"}:
        return {"type": "boolean"}
    if normalized.startswith(("array", "list")):
        return {"type": "array", "items": {"type": "object"}}
    return {"type": "string"}
