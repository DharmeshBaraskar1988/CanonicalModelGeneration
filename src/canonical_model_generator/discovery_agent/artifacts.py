"""Validated deterministic artifact generation from one DiscoveryModel."""

from __future__ import annotations

import json
import os
import tempfile
from http import HTTPStatus
from pathlib import Path
from typing import Any

from canonical_model_generator.discovery_agent.model import DiscoveryModel


def generate_artifacts(model: DiscoveryModel, output: Path) -> dict[str, str]:
    validated = DiscoveryModel.model_validate(model.model_dump())
    payloads: dict[str, Any] = {
        "discovery-model.json": validated.model_dump(mode="json", by_alias=True),
        "api-catalog.json": {
            "operations": _readable_operations(validated),
            "operationCount": validated.summary.operation_count,
        },
        "data-model.json": _readable_data_model(validated),
        "relationship-graph.json": {
            "relationships": _readable_relationships(validated),
            "relationshipCount": validated.summary.relationship_count,
        },
        "validation-enums.json": _readable_validations_and_enums(validated),
        "lineage.json": _readable_lineage(validated),
    }
    for name, payload in payloads.items():
        if name != "discovery-model.json":
            _validate_operator_payload(payload, name)
    _validate_payload_counts(payloads, validated)
    output = output.resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="canonical-artifacts-", dir=output.parent) as temporary:
        temporary_path = Path(temporary)
        for name, payload in payloads.items():
            (temporary_path / name).write_text(
                json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8"
            )
        output.mkdir(parents=True, exist_ok=True)
        for name in sorted(payloads):
            os.replace(temporary_path / name, output / name)
    return {name: str(output / name) for name in sorted(payloads)}


def _readable_relationships(model: DiscoveryModel) -> list[dict[str, Any]]:
    subjects: dict[str, tuple[str, str]] = {}
    for operation in model.operations:
        subjects[operation.id] = (
            operation.name,
            f"{operation.method} {operation.route}",
        )
    for entity in model.entities:
        subjects[entity.id] = (entity.name, "Contract model")
        for attribute in entity.attributes:
            subjects[attribute.id] = (f"{entity.name}.{attribute.name}", "Attribute")
    for enum in model.enums:
        subjects[enum.id] = (enum.name, "Enum")

    evidence_by_id = {item.id: item for item in model.evidence}
    sources_by_id = {item.id: item for item in model.sources}
    lineage_by_subject_source = {(item.subject_id, item.source_id): item for item in model.lineage}

    readable = []
    for relationship in model.relationships:
        source_name, source_type = subjects.get(
            relationship.source_id, ("Unknown source", "Unknown")
        )
        target_name, target_type = subjects.get(
            relationship.target_id, ("Unknown target", "Unknown")
        )
        support = []
        for evidence_id in relationship.evidence_ids:
            evidence = evidence_by_id[evidence_id]
            source = sources_by_id[evidence.source_id]
            lineage = lineage_by_subject_source.get((evidence.subject_id, evidence.source_id))
            location = source.path
            if lineage is not None and lineage.pointer:
                location = f"{lineage.path}{lineage.pointer}"
            elif lineage is not None and lineage.start_line:
                location = f"{lineage.path}:line {lineage.start_line}"
            support.append(
                {
                    "source": source.kind.value,
                    "location": location,
                }
            )

        readable.append(
            {
                "relationship": f"{source_name} {relationship.kind.value.lower()} {target_name}",
                "type": relationship.kind.value,
                "from": {"name": source_name, "type": source_type},
                "to": {"name": target_name, "type": target_type},
                "supportedBy": support,
            }
        )
    return readable


def _readable_data_model(model: DiscoveryModel) -> dict[str, Any]:
    type_names = {entity.id: entity.name for entity in model.entities}
    type_names.update({enum.id: enum.name for enum in model.enums})
    entities = []

    for entity in model.entities:
        fields = []
        for attribute in entity.attributes:
            fields.append(
                {
                    "name": attribute.name,
                    "originalName": attribute.original_name,
                    "type": type_names.get(attribute.type.reference_id, attribute.type.name),
                    "required": attribute.required,
                    "nullable": attribute.type.nullable,
                    "collection": attribute.type.collection,
                    "format": attribute.type.format,
                    "supportedBy": _supporting_sources(model, attribute.evidence_ids),
                }
            )
        entities.append(
            {
                "name": entity.name,
                "originalName": entity.original_name,
                "inheritsFrom": type_names.get(entity.base_entity_id),
                "fields": fields,
                "supportedBy": _supporting_sources(model, entity.evidence_ids),
            }
        )

    enums = [
        {
            "name": enum.name,
            "values": [{"name": value.name, "value": value.value} for value in enum.values],
            "supportedBy": _supporting_sources(model, enum.evidence_ids),
        }
        for enum in model.enums
    ]
    return {
        "entities": entities,
        "enums": enums,
        "entityCount": len(entities),
        "enumCount": len(enums),
    }


def _readable_validations_and_enums(model: DiscoveryModel) -> dict[str, Any]:
    subjects = _subject_names(model)
    validations = []
    for validation in model.validations:
        subject = subjects.get(
            validation.target_id,
            {"name": "Unknown target", "type": "Unknown"},
        )
        validations.append(
            {
                "target": subject["name"],
                "targetType": subject["type"],
                "rule": validation.rule,
                "arguments": validation.arguments,
                "supportedBy": _supporting_sources(model, validation.evidence_ids),
            }
        )

    enums = [
        {
            "name": enum.name,
            "values": [{"name": value.name, "value": value.value} for value in enum.values],
            "supportedBy": _supporting_sources(model, enum.evidence_ids),
        }
        for enum in model.enums
    ]
    return {"validations": validations, "enums": enums}


def _readable_lineage(model: DiscoveryModel) -> dict[str, Any]:
    subjects = _subject_names(model)
    sources = {source.id: source for source in model.sources}
    lineage_by_subject_source = {(item.subject_id, item.source_id): item for item in model.lineage}

    evidence = []
    for item in model.evidence:
        subject = subjects.get(item.subject_id, {"name": "Unknown", "type": "Unknown"})
        source = sources.get(item.source_id)
        lineage = lineage_by_subject_source.get((item.subject_id, item.source_id))
        evidence.append(
            {
                "subject": subject["name"],
                "subjectType": subject["type"],
                "observedValue": item.observed_value,
                "source": source.kind.value if source is not None else "unknown",
                "location": _lineage_location(lineage, source.path if source else "Unknown"),
            }
        )

    lineage_items = []
    for item in model.lineage:
        subject = subjects.get(item.subject_id, {"name": "Unknown", "type": "Unknown"})
        source = sources.get(item.source_id)
        lineage_items.append(
            {
                "subject": subject["name"],
                "subjectType": subject["type"],
                "source": source.kind.value if source is not None else "unknown",
                "location": _lineage_location(item, source.path if source else "Unknown"),
            }
        )

    diagnostics = []
    for diagnostic in model.diagnostics:
        diagnostics.append(
            {
                "severity": diagnostic.severity.value,
                "code": diagnostic.code,
                "message": diagnostic.message,
                "affectedItems": [
                    subjects.get(subject_id, {"name": "Unknown"})["name"]
                    for subject_id in diagnostic.subject_ids
                ],
                "supportedBy": _supporting_sources(model, diagnostic.evidence_ids),
            }
        )

    return {
        "evidence": evidence,
        "lineage": lineage_items,
        "diagnostics": diagnostics,
        "evidenceCount": len(evidence),
        "lineageCount": len(lineage_items),
        "diagnosticCount": len(diagnostics),
    }


def _readable_operations(model: DiscoveryModel) -> list[dict[str, Any]]:
    entity_names = {entity.id: entity.name for entity in model.entities}
    readable = []

    for operation in model.operations:
        parameters = []
        for parameter in operation.parameters:
            parameter_type = entity_names.get(
                parameter.type.reference_id,
                parameter.type.name,
            )
            parameters.append(
                {
                    "name": parameter.name,
                    "location": parameter.location.value,
                    "required": parameter.required,
                    "type": parameter_type,
                    "collection": parameter.type.collection,
                    "nullable": parameter.type.nullable,
                }
            )

        responses = []
        for response in operation.responses:
            try:
                status_name = HTTPStatus(response.status_code).phrase
            except ValueError:
                status_name = "Custom status"
            responses.append(
                {
                    "statusCode": response.status_code,
                    "statusName": status_name,
                    "responseModel": entity_names.get(
                        response.entity_id,
                        "No response model identified",
                    ),
                    "responseModelTree": _response_model_tree(
                        model,
                        response.entity_id,
                    ),
                }
            )

        readable.append(
            {
                "operation": operation.name,
                "method": operation.method,
                "route": operation.route,
                "requestModel": entity_names.get(
                    operation.request_entity_id,
                    "No request model identified",
                ),
                "requestModelTree": _model_tree(
                    model,
                    operation.request_entity_id,
                    root_role="Request model",
                ),
                "parameters": parameters,
                "responses": responses,
                "supportedBy": _supporting_sources(model, operation.evidence_ids),
            }
        )

    return readable


def _response_model_tree(
    model: DiscoveryModel,
    root_entity_id: str | None,
) -> dict[str, Any] | None:
    return _model_tree(model, root_entity_id, root_role="Response model")


def _model_tree(
    model: DiscoveryModel,
    root_entity_id: str | None,
    *,
    root_role: str,
) -> dict[str, Any] | None:
    entities_by_id = {entity.id: entity for entity in model.entities}
    root = entities_by_id.get(root_entity_id)
    if root is None:
        return None

    type_names = {entity.id: entity.name for entity in model.entities}
    type_names.update({enum.id: enum.name for enum in model.enums})
    model_details = []
    relations = []
    pending = [root.id]
    visited: set[str] = set()

    while pending:
        entity_id = pending.pop(0)
        if entity_id in visited:
            continue
        entity = entities_by_id.get(entity_id)
        if entity is None:
            continue
        visited.add(entity_id)

        fields = []
        for attribute in entity.attributes:
            field_type = type_names.get(attribute.type.reference_id, attribute.type.name)
            fields.append(
                {
                    "name": attribute.name,
                    "type": field_type,
                    "required": attribute.required,
                    "collection": attribute.type.collection,
                    "nullable": attribute.type.nullable,
                }
            )
            related = entities_by_id.get(attribute.type.reference_id)
            if related is not None:
                relation = "contains many" if attribute.type.collection else "contains"
                relations.append(
                    {
                        "from": entity.name,
                        "relationship": relation,
                        "viaField": attribute.name,
                        "to": related.name,
                    }
                )
                if related.id not in visited and related.id not in pending:
                    pending.append(related.id)

        base = entities_by_id.get(entity.base_entity_id)
        if base is not None:
            relations.append(
                {
                    "from": entity.name,
                    "relationship": "inherits from",
                    "to": base.name,
                }
            )
            if base.id not in visited and base.id not in pending:
                pending.append(base.id)

        model_details.append(
            {
                "name": entity.name,
                "role": root_role if entity.id == root.id else "Related model",
                "inheritsFrom": base.name if base is not None else None,
                "fields": fields,
                "supportedBy": _supporting_sources(model, entity.evidence_ids),
            }
        )

    return {
        "rootModel": root.name,
        "models": model_details,
        "relations": relations,
    }


def _subject_names(model: DiscoveryModel) -> dict[str, dict[str, str]]:
    subjects: dict[str, dict[str, str]] = {}
    for operation in model.operations:
        operation_name = f"{operation.name} ({operation.method} {operation.route})"
        subjects[operation.id] = {"name": operation_name, "type": "Operation"}
        for parameter in operation.parameters:
            subjects[parameter.id] = {
                "name": f"{operation.name}.{parameter.name}",
                "type": "Parameter",
            }
        for response in operation.responses:
            try:
                status_name = HTTPStatus(response.status_code).phrase
            except ValueError:
                status_name = "Custom status"
            subjects[response.id] = {
                "name": f"{operation.name} response {response.status_code} {status_name}",
                "type": "Response",
            }
    for entity in model.entities:
        subjects[entity.id] = {"name": entity.name, "type": "Contract model"}
        for attribute in entity.attributes:
            subjects[attribute.id] = {
                "name": f"{entity.name}.{attribute.name}",
                "type": "Attribute",
            }
    for enum in model.enums:
        subjects[enum.id] = {"name": enum.name, "type": "Enum"}
    return subjects


def _lineage_location(lineage: Any | None, fallback: str) -> str:
    if lineage is None:
        return fallback
    if lineage.pointer:
        return f"{lineage.path}{lineage.pointer}"
    if lineage.start_line:
        if lineage.end_line and lineage.end_line != lineage.start_line:
            return f"{lineage.path}:lines {lineage.start_line}-{lineage.end_line}"
        return f"{lineage.path}:line {lineage.start_line}"
    return lineage.path


def _supporting_sources(
    model: DiscoveryModel,
    evidence_ids: list[str],
) -> list[dict[str, str]]:
    evidence_by_id = {item.id: item for item in model.evidence}
    sources_by_id = {item.id: item for item in model.sources}
    lineage_by_subject_source = {(item.subject_id, item.source_id): item for item in model.lineage}
    supported_by = []
    seen: set[tuple[str, str]] = set()

    for evidence_id in evidence_ids:
        evidence = evidence_by_id.get(evidence_id)
        if evidence is None:
            continue
        source = sources_by_id.get(evidence.source_id)
        lineage = lineage_by_subject_source.get((evidence.subject_id, evidence.source_id))
        source_name = source.kind.value if source is not None else "unknown"
        location = source.path if source is not None else evidence.source_id
        if lineage is not None and lineage.pointer:
            location = f"{lineage.path}{lineage.pointer}"
        elif lineage is not None and lineage.start_line:
            location = f"{lineage.path}:line {lineage.start_line}"

        key = (source_name, location)
        if key in seen:
            continue
        seen.add(key)
        supported_by.append({"source": source_name, "location": location})

    return supported_by


def _validate_payload_counts(payloads: dict[str, Any], model: DiscoveryModel) -> None:
    if payloads["api-catalog.json"]["operationCount"] != len(model.operations):
        raise ValueError("API catalog operation count mismatch")
    if payloads["data-model.json"]["entityCount"] != len(model.entities):
        raise ValueError("Data model entity count mismatch")
    if payloads["relationship-graph.json"]["relationshipCount"] != len(model.relationships):
        raise ValueError("Relationship graph count mismatch")
    subjects = {item.subject_id for item in model.lineage}
    explained = {subject for item in model.diagnostics for subject in item.subject_ids}
    required = {item.id for item in model.operations + model.entities}
    required.update(attribute.id for entity in model.entities for attribute in entity.attributes)
    missing = required - subjects - explained
    if missing:
        raise ValueError(f"Missing lineage or diagnostic for: {', '.join(sorted(missing))}")


def _validate_operator_payload(payload: Any, artifact_name: str) -> None:
    internal_prefixes = {
        "attribute",
        "diagnostic",
        "entity",
        "enum",
        "evidence",
        "lineage",
        "operation",
        "parameter",
        "relationship",
        "response",
        "source",
        "validation",
    }

    def visit(value: Any) -> None:
        if isinstance(value, dict):
            for key, nested in value.items():
                if key == "id" or key.endswith("Id") or key.endswith("Ids"):
                    raise ValueError(
                        f"Operator artifact {artifact_name} exposes internal key {key}"
                    )
                visit(nested)
        elif isinstance(value, list):
            for nested in value:
                visit(nested)
        elif isinstance(value, str):
            prefix, separator, suffix = value.partition("-")
            if (
                separator
                and prefix in internal_prefixes
                and len(suffix) == 20
                and all(character in "0123456789abcdef" for character in suffix)
            ):
                raise ValueError(f"Operator artifact {artifact_name} exposes internal identifier")

    visit(payload)
