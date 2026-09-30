"""Deterministic OpenAPI 3 JSON/YAML discovery."""

from __future__ import annotations

import json
from hashlib import sha256
from pathlib import Path, PurePosixPath
from typing import Any

import yaml

from canonical_model_generator.discovery_agent.model import (
    Attribute,
    Diagnostic,
    DiscoveryModel,
    Entity,
    EnumDefinition,
    EnumValue,
    Evidence,
    Lineage,
    Operation,
    Parameter,
    ParameterLocation,
    Relationship,
    RelationshipKind,
    Response,
    RunMetadata,
    RunStatus,
    Severity,
    SourceDescriptor,
    SourceKind,
    Summary,
    TypeKind,
    TypeRef,
    ValidationRule,
    stable_id,
)

HTTP_METHODS = {"get", "post", "put", "patch", "delete", "head", "options", "trace"}
CONSTRAINTS = {
    "minimum",
    "maximum",
    "minLength",
    "maxLength",
    "pattern",
    "minItems",
    "maxItems",
}


def discover_openapi(
    path: Path, region: str, system: str, repository: Path | None = None
) -> DiscoveryModel:
    content = path.read_bytes()
    try:
        document = (
            json.loads(content.decode("utf-8"))
            if path.suffix.lower() == ".json"
            else yaml.safe_load(content)
        )
    except (UnicodeDecodeError, json.JSONDecodeError, yaml.YAMLError) as exc:
        raise ValueError(f"Invalid OpenAPI document: {exc}") from exc
    if not isinstance(document, dict) or not str(document.get("openapi", "")).startswith("3."):
        raise ValueError("Only OpenAPI 3.x documents are supported")
    return _build_model(document, path, content, region, system, repository)


def spec_schema_names(path: Path) -> list[str]:
    """Schema names of an OpenAPI document, used as model-name hints for the code search."""
    try:
        document = (
            json.loads(path.read_text(encoding="utf-8"))
            if path.suffix.lower() == ".json"
            else yaml.safe_load(path.read_bytes())
        )
        schemas = document.get("components", {}).get("schemas", {})
        return sorted(str(name) for name in schemas)
    except (OSError, ValueError, AttributeError, yaml.YAMLError):
        return []


def _build_model(
    document: dict[str, Any],
    path: Path,
    content: bytes,
    region: str,
    system: str,
    repository: Path | None,
) -> DiscoveryModel:
    source_path = (
        path.resolve().relative_to(repository.resolve()).as_posix()
        if repository is not None
        else path.as_posix()
    )
    source_id = stable_id("source", "openapi", source_path)
    source = SourceDescriptor(
        id=source_id,
        kind=SourceKind.OPENAPI,
        path=source_path,
        sha256=sha256(content).hexdigest(),
    )
    schemas = document.get("components", {}).get("schemas", {})
    schema_ids = {
        name: stable_id("enum" if "enum" in schema else "entity", name)
        for name, schema in schemas.items()
    }
    evidence: list[Evidence] = []
    lineage: list[Lineage] = []
    relationships: list[Relationship] = []
    validations: list[ValidationRule] = []
    diagnostics: list[Diagnostic] = []
    external_refs = sorted({ref for ref in _iter_refs(document) if not ref.startswith("#")})
    if external_refs:
        names = sorted({_external_reference_name(ref) for ref in external_refs})
        unbundled = [name for name in names if name not in schemas]
        diagnostics.append(
            Diagnostic(
                id=stable_id("diagnostic", "OPENAPI_EXTERNAL_REF", *names),
                severity=Severity.WARNING if unbundled else Severity.INFO,
                code="OPENAPI_EXTERNAL_REF",
                message=(
                    f"{len(external_refs)} external file reference(s) to {len(names)} schema(s); "
                    f"{len(names) - len(unbundled)} resolved by name in components.schemas, "
                    f"{len(unbundled)} kept as opaque named models"
                    + (f": {', '.join(unbundled)}" if unbundled else "")
                ),
            )
        )

    def trace(subject_id: str, pointer: str, value: Any) -> str:
        evidence_id = stable_id("evidence", source_id, subject_id, pointer)
        evidence.append(
            Evidence(
                id=evidence_id, source_id=source_id, subject_id=subject_id, observed_value=value
            )
        )
        lineage.append(
            Lineage(
                id=stable_id("lineage", source_id, subject_id, pointer),
                source_id=source_id,
                subject_id=subject_id,
                path=source_path,
                pointer=pointer,
            )
        )
        return evidence_id

    entities: list[Entity] = []
    enums: list[EnumDefinition] = []
    for name, original_schema in schemas.items():
        pointer = f"#/components/schemas/{_escape(name)}"
        schema = _flatten_schema(original_schema, document, diagnostics, pointer)
        schema_id = schema_ids[name]
        schema_evidence = trace(schema_id, pointer, name)
        if "enum" in schema:
            enums.append(
                EnumDefinition(
                    id=schema_id,
                    name=name,
                    values=[EnumValue(name=str(value), value=value) for value in schema["enum"]],
                    evidence_ids=[schema_evidence],
                )
            )
            continue
        required = set(schema.get("required", []))
        attributes: list[Attribute] = []
        for property_name, property_schema in sorted(schema.get("properties", {}).items()):
            attribute_id = stable_id("attribute", name, property_name)
            property_pointer = f"{pointer}/properties/{_escape(property_name)}"
            property_evidence = trace(attribute_id, property_pointer, property_name)
            resolved = _resolve(property_schema, document)
            reference_name = _reference_name(property_schema)
            if resolved.get("type") == "array":
                reference_name = _reference_name(resolved.get("items", {}))
            reference_id = schema_ids.get(reference_name)
            attributes.append(
                Attribute(
                    id=attribute_id,
                    name=property_name,
                    original_name=property_name,
                    type=_type_ref(resolved, reference_id),
                    required=property_name in required,
                    evidence_ids=[property_evidence],
                )
            )
            relationships.append(
                Relationship(
                    id=stable_id("relationship", "CONTAINS", schema_id, attribute_id),
                    kind=RelationshipKind.CONTAINS,
                    source_id=schema_id,
                    target_id=attribute_id,
                    evidence_ids=[property_evidence],
                )
            )
            for constraint in sorted(CONSTRAINTS & resolved.keys()):
                validations.append(
                    ValidationRule(
                        id=stable_id("validation", attribute_id, constraint),
                        target_id=attribute_id,
                        rule=constraint,
                        arguments={"value": resolved[constraint]},
                        evidence_ids=[property_evidence],
                    )
                )
        entities.append(
            Entity(
                id=schema_id,
                name=name,
                original_name=name,
                attributes=attributes,
                evidence_ids=[schema_evidence],
            )
        )

    operations: list[Operation] = []
    entity_ids = {item.name: item.id for item in entities}
    for route, path_item in sorted(document.get("paths", {}).items()):
        for method, operation_schema in sorted(path_item.items()):
            if method not in HTTP_METHODS:
                continue
            pointer = f"#/paths/{_escape(route)}/{method}"
            operation_id = stable_id("operation", method.upper(), route)
            operation_evidence = trace(
                operation_id, pointer, {"method": method.upper(), "route": route}
            )
            parameters = []
            for parameter in path_item.get("parameters", []) + operation_schema.get(
                "parameters", []
            ):
                parameter = _resolve(parameter, document)
                parameter_id = stable_id(
                    "parameter", operation_id, parameter.get("in", "query"), parameter["name"]
                )
                parameters.append(
                    Parameter(
                        id=parameter_id,
                        name=parameter["name"],
                        location=ParameterLocation(
                            "route"
                            if parameter.get("in") == "path"
                            else parameter.get("in", "query")
                        ),
                        required=parameter.get("required", False),
                        type=_type_ref(_resolve(parameter.get("schema", {}), document), None),
                    )
                )
            request_schema = (
                operation_schema.get("requestBody", {})
                .get("content", {})
                .get("application/json", {})
                .get("schema", {})
            )
            request_name = _reference_name(request_schema)
            request_id = entity_ids.get(request_name)
            if request_schema:
                parameters.append(
                    Parameter(
                        id=stable_id("parameter", operation_id, "body", "body"),
                        name="body",
                        location=ParameterLocation.BODY,
                        required=operation_schema.get("requestBody", {}).get("required", False),
                        type=_type_ref(_resolve(request_schema, document), request_id),
                    )
                )
            responses: list[Response] = []
            for status, response_schema in sorted(operation_schema.get("responses", {}).items()):
                if not str(status).isdigit():
                    continue
                response_schema = _resolve(response_schema, document)
                body_schema = (
                    response_schema.get("content", {}).get("application/json", {}).get("schema", {})
                )
                response_entity = entity_ids.get(_reference_name(body_schema))
                responses.append(
                    Response(
                        id=stable_id("response", operation_id, str(status)),
                        status_code=int(status),
                        entity_id=response_entity,
                        type=(
                            _type_ref(_resolve(body_schema, document), response_entity)
                            if body_schema
                            else None
                        ),
                        description=response_schema.get("description"),
                    )
                )
            operations.append(
                Operation(
                    id=operation_id,
                    name=operation_schema.get("operationId", f"{method}-{route}"),
                    method=method.upper(),
                    route=route,
                    parameters=parameters,
                    request_entity_id=request_id,
                    responses=responses,
                    evidence_ids=[operation_evidence],
                )
            )
            if request_id:
                relationships.append(
                    Relationship(
                        id=stable_id("relationship", "ACCEPTS", operation_id, request_id),
                        kind=RelationshipKind.ACCEPTS,
                        source_id=operation_id,
                        target_id=request_id,
                        evidence_ids=[operation_evidence],
                    )
                )
            for response in responses:
                if response.entity_id:
                    relationships.append(
                        Relationship(
                            id=stable_id(
                                "relationship", "RETURNS", operation_id, response.entity_id
                            ),
                            kind=RelationshipKind.RETURNS,
                            source_id=operation_id,
                            target_id=response.entity_id,
                            evidence_ids=[operation_evidence],
                        )
                    )

    return DiscoveryModel(
        run=RunMetadata(
            id=stable_id("run", "openapi", region, system),
            status=RunStatus.PARTIAL if diagnostics else RunStatus.COMPLETE,
            tool_version="0.1.0",
        ),
        region=region,
        system=system,
        sources=[source],
        operations=operations,
        entities=entities,
        enums=enums,
        validations=validations,
        relationships=relationships,
        evidence=evidence,
        lineage=lineage,
        diagnostics=diagnostics,
        summary=Summary(
            operation_count=len(operations),
            entity_count=len(entities),
            enum_count=len(enums),
            relationship_count=len(relationships),
            diagnostic_count=len(diagnostics),
        ),
    )


def _resolve(schema: dict[str, Any], document: dict[str, Any]) -> dict[str, Any]:
    reference = schema.get("$ref")
    if not reference:
        return schema
    if not reference.startswith("#/"):
        # File references such as `.\\Model_v3.yaml`: use the same-named component schema when
        # the document bundles it; otherwise keep an opaque model so parsing can continue.
        name = _external_reference_name(reference)
        bundled = document.get("components", {}).get("schemas", {}).get(name)
        return bundled if isinstance(bundled, dict) else {"type": "object", "x-external-ref": name}
    current: Any = document
    for token in reference[2:].split("/"):
        current = current[token.replace("~1", "/").replace("~0", "~")]
    return current


def _flatten_schema(
    schema: dict[str, Any],
    document: dict[str, Any],
    diagnostics: list[Diagnostic],
    pointer: str,
) -> dict[str, Any]:
    schema = _resolve(schema, document)
    if "oneOf" in schema or "anyOf" in schema:
        diagnostics.append(
            Diagnostic(
                id=stable_id("diagnostic", "OPENAPI_COMPOSITION", pointer),
                severity=Severity.WARNING,
                code="OPENAPI_COMPOSITION",
                message=f"Unsupported oneOf/anyOf at {pointer}",
            )
        )
    if "allOf" not in schema:
        return schema
    merged: dict[str, Any] = {"type": "object", "properties": {}, "required": []}
    for part in schema["allOf"]:
        resolved = _flatten_schema(part, document, diagnostics, pointer)
        merged["properties"].update(resolved.get("properties", {}))
        merged["required"].extend(resolved.get("required", []))
    merged["properties"].update(schema.get("properties", {}))
    merged["required"] = sorted(set(merged["required"] + schema.get("required", [])))
    return merged


def _reference_name(schema: dict[str, Any]) -> str | None:
    reference = schema.get("$ref")
    if not isinstance(reference, str):
        return None
    if not reference.startswith("#"):
        return _external_reference_name(reference)
    return reference.rsplit("/", 1)[-1]


def _external_reference_name(reference: str) -> str:
    return PurePosixPath(reference.replace("\\", "/")).stem


def _iter_refs(node: Any):
    if isinstance(node, dict):
        reference = node.get("$ref")
        if isinstance(reference, str):
            yield reference
        for value in node.values():
            yield from _iter_refs(value)
    elif isinstance(node, list):
        for value in node:
            yield from _iter_refs(value)


def _type_ref(schema: dict[str, Any], reference_id: str | None) -> TypeRef:
    schema_type = schema.get("type", "object" if reference_id else "unknown")
    collection = schema_type == "array"
    value_schema = schema.get("items", {}) if collection else schema
    value_type = value_schema.get("type", "object" if reference_id else "unknown")
    kind = {
        "string": TypeKind.STRING,
        "integer": TypeKind.INTEGER,
        "number": TypeKind.NUMBER,
        "boolean": TypeKind.BOOLEAN,
        "object": TypeKind.OBJECT,
    }.get(value_type, TypeKind.UNKNOWN)
    if value_schema.get("format") == "uuid":
        kind = TypeKind.UUID
    elif value_schema.get("format") == "date-time":
        kind = TypeKind.DATE_TIME
    if reference_id and reference_id.startswith("enum-"):
        kind = TypeKind.ENUM
    return TypeRef(
        kind=kind,
        name=_reference_name(value_schema) or value_type,
        nullable=schema.get("nullable", False),
        collection=collection,
        reference_id=reference_id,
        format=value_schema.get("format"),
    )


def _escape(value: str) -> str:
    return value.replace("~", "~0").replace("/", "~1")
