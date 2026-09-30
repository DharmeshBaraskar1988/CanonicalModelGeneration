"""Invoke the Roslyn sidecar and map its observations to DiscoveryModel v1."""

from __future__ import annotations

import json
import subprocess
import tempfile
from collections.abc import Sequence
from pathlib import Path
from typing import Any

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
from canonical_model_generator.discovery_agent.view_model_scope import scope_to_endpoint_view_models


def extract_roslyn(
    project: Path,
    repository: Path,
    region: str,
    system: str,
    hint_types: Sequence[str] = (),
) -> DiscoveryModel:
    """Run Roslyn; `hint_types` are model names from an OpenAPI document to look for in code."""
    sidecar = Path("dotnet/src/CanonicalModel.Discovery/CanonicalModel.Discovery.csproj").resolve()
    with tempfile.TemporaryDirectory(prefix="canonical-roslyn-") as directory:
        raw_path = Path(directory) / "roslyn.json"
        hint_arguments: list[str] = []
        if hint_types:
            hint_path = Path(directory) / "hints.json"
            hint_path.write_text(json.dumps(sorted(set(hint_types))), encoding="utf-8")
            hint_arguments = ["--hint-types", str(hint_path)]
        process = subprocess.run(
            [
                "dotnet",
                "run",
                "--project",
                str(sidecar),
                "--",
                "--project",
                str(project.resolve()),
                "--output",
                str(raw_path),
                *hint_arguments,
            ],
            check=False,
            capture_output=True,
            text=True,
            timeout=120,
        )
        if not raw_path.exists():
            raise RuntimeError(process.stderr.strip() or "Roslyn sidecar produced no output")
        raw = json.loads(raw_path.read_text(encoding="utf-8"))
    return scope_to_endpoint_view_models(roslyn_to_model(raw, repository.resolve(), region, system))


def merge_roslyn_models(models: list[DiscoveryModel]) -> DiscoveryModel:
    """Combine deterministic Roslyn results from every controller-owning project."""
    if not models:
        raise ValueError("At least one Roslyn model is required")
    region, system = models[0].region, models[0].system
    if any((model.region, model.system) != (region, system) for model in models):
        raise ValueError("Roslyn models must describe the same region and system")

    merged = models[0].model_copy(deep=True)
    for model in models[1:]:
        merged.sources.extend(item.model_copy(deep=True) for item in model.sources)
        merged.operations.extend(item.model_copy(deep=True) for item in model.operations)
        merged.entities.extend(item.model_copy(deep=True) for item in model.entities)
        merged.enums.extend(item.model_copy(deep=True) for item in model.enums)
        merged.validations.extend(item.model_copy(deep=True) for item in model.validations)
        merged.relationships.extend(item.model_copy(deep=True) for item in model.relationships)
        merged.evidence.extend(item.model_copy(deep=True) for item in model.evidence)
        merged.lineage.extend(item.model_copy(deep=True) for item in model.lineage)
        merged.diagnostics.extend(item.model_copy(deep=True) for item in model.diagnostics)

    merged.sources = sorted(_unique_by_id(merged.sources), key=lambda item: item.path)
    merged.operations = sorted(
        _unique_by_id(merged.operations), key=lambda item: (item.route, item.method)
    )
    merged.entities = sorted(_unique_by_id(merged.entities), key=lambda item: item.name)
    merged.enums = sorted(_unique_by_id(merged.enums), key=lambda item: item.name)
    merged.validations = sorted(_unique_by_id(merged.validations), key=lambda item: item.id)
    merged.relationships = sorted(_unique_by_id(merged.relationships), key=lambda item: item.id)
    merged.evidence = sorted(_unique_by_id(merged.evidence), key=lambda item: item.id)
    merged.lineage = sorted(_unique_by_id(merged.lineage), key=lambda item: item.id)
    merged.diagnostics = sorted(_unique_by_id(merged.diagnostics), key=lambda item: item.id)
    merged.run = RunMetadata(
        id=stable_id("run", "roslyn-repository", region, system),
        status=RunStatus.FAILED
        if any(item.severity == Severity.ERROR for item in merged.diagnostics)
        else RunStatus.COMPLETE,
        tool_version="0.1.0",
    )
    merged.summary = Summary(
        operation_count=len(merged.operations),
        entity_count=len(merged.entities),
        enum_count=len(merged.enums),
        relationship_count=len(merged.relationships),
        diagnostic_count=len(merged.diagnostics),
    )
    return scope_to_endpoint_view_models(DiscoveryModel.model_validate(merged.model_dump()))


def roslyn_to_model(
    raw: dict[str, Any], repository: Path, region: str, system: str
) -> DiscoveryModel:
    sources: list[SourceDescriptor] = []
    source_by_path: dict[str, str] = {}
    for item in raw["sources"]:
        relative = _relative(item["path"], repository)
        source_id = stable_id("source", "roslyn", relative)
        sources.append(
            SourceDescriptor(
                id=source_id, kind=SourceKind.ROSLYN, path=relative, sha256=item["sha256"]
            )
        )
        source_by_path[Path(item["path"]).as_posix().lower()] = source_id

    type_ids = {
        item["fullName"]: stable_id(
            "enum" if item["kind"] == "enum" else "entity", item["fullName"]
        )
        for item in raw["types"]
    }
    evidence: list[Evidence] = []
    lineage: list[Lineage] = []
    entities: list[Entity] = []
    enums: list[EnumDefinition] = []
    validations: list[ValidationRule] = []
    relationships: list[Relationship] = []

    def trace(subject_id: str, location: dict[str, Any], value: Any) -> str:
        source_id = source_by_path[Path(location["path"]).as_posix().lower()]
        evidence_id = stable_id(
            "evidence", source_id, subject_id, json.dumps(value, sort_keys=True)
        )
        evidence.append(
            Evidence(
                id=evidence_id, source_id=source_id, subject_id=subject_id, observed_value=value
            )
        )
        lineage.append(
            Lineage(
                id=stable_id("lineage", source_id, subject_id),
                source_id=source_id,
                subject_id=subject_id,
                path=_relative(location["path"], repository),
                start_line=location["startLine"],
                end_line=location["endLine"],
            )
        )
        return evidence_id

    hinted_types = set(raw.get("hintedTypes", []))
    for item in raw["types"]:
        type_id = type_ids[item["fullName"]]
        type_evidence = trace(type_id, item["location"], item["fullName"])
        type_evidence_ids = [type_evidence]
        if item["fullName"] in hinted_types:
            type_evidence_ids.append(
                trace(type_id, item["location"], {"hint": "openapi-schema", "name": item["name"]})
            )
        if item["kind"] == "enum":
            enums.append(
                EnumDefinition(
                    id=type_id,
                    name=item["name"],
                    values=[EnumValue(name=value, value=value) for value in item["enumValues"]],
                    evidence_ids=[type_evidence],
                )
            )
            continue
        attributes: list[Attribute] = []
        for prop in item["properties"]:
            attribute_id = stable_id("attribute", item["fullName"], prop["name"])
            prop_evidence = trace(attribute_id, prop["location"], prop["name"])
            reference_name = prop["elementType"] if prop["collection"] else prop["type"]
            reference_id = type_ids.get(reference_name)
            attribute = Attribute(
                id=attribute_id,
                name=_camel(prop["name"]),
                original_name=prop["name"],
                type=_type_ref(prop["type"], prop["nullable"], prop["collection"], reference_id),
                required=not prop["nullable"],
                evidence_ids=[prop_evidence],
            )
            attributes.append(attribute)
            relationships.append(
                Relationship(
                    id=stable_id("relationship", "CONTAINS", type_id, attribute_id),
                    kind=RelationshipKind.CONTAINS,
                    source_id=type_id,
                    target_id=attribute_id,
                    evidence_ids=[prop_evidence],
                )
            )
            for rule in prop["attributes"]:
                validations.append(
                    ValidationRule(
                        id=stable_id("validation", attribute_id, rule["name"], *rule["arguments"]),
                        target_id=attribute_id,
                        rule=rule["name"],
                        arguments={"values": rule["arguments"]},
                        evidence_ids=[prop_evidence],
                    )
                )
        base_entity_id = type_ids.get(item["baseType"])
        entities.append(
            Entity(
                id=type_id,
                name=item["name"],
                original_name=item["name"],
                attributes=attributes,
                base_entity_id=base_entity_id,
                evidence_ids=type_evidence_ids,
            )
        )
        if base_entity_id:
            relationships.append(
                Relationship(
                    id=stable_id("relationship", "INHERITS", type_id, base_entity_id),
                    kind=RelationshipKind.INHERITS,
                    source_id=type_id,
                    target_id=base_entity_id,
                    evidence_ids=[type_evidence],
                )
            )

    operations: list[Operation] = []
    entity_ids = {
        item["fullName"]: type_ids[item["fullName"]]
        for item in raw["types"]
        if item["kind"] == "class"
    }
    for item in raw["operations"]:
        operation_id = stable_id("operation", item["method"], item["route"])
        operation_evidence = trace(
            operation_id, item["location"], {"method": item["method"], "route": item["route"]}
        )
        operation_evidence_ids = [operation_evidence]
        if flow := item.get("flow"):
            # Command/handler/mapper/backend trail: kept as evidence, and the models it touches
            # are linked with MAPS_TO (mapper source -> target) and REFERENCES (operation -> model).
            flow_evidence = trace(
                operation_id,
                flow["location"],
                {
                    "flow": flow["kind"],
                    "command": flow["command"],
                    "handler": flow["handler"],
                    "mappings": [
                        {"from": m["from"], "to": m["to"], "via": m["via"]}
                        for m in flow["mappings"]
                    ],
                    "backends": flow["backends"],
                    "related": [{"type": r["type"], "role": r["role"]} for r in flow["related"]],
                },
            )
            operation_evidence_ids.append(flow_evidence)
            for mapping in flow["mappings"]:
                source_entity = entity_ids.get(mapping["from"])
                target_entity = entity_ids.get(mapping["to"])
                if source_entity and target_entity:
                    relationships.append(
                        Relationship(
                            id=stable_id("relationship", "MAPS_TO", source_entity, target_entity),
                            kind=RelationshipKind.MAPS_TO,
                            source_id=source_entity,
                            target_id=target_entity,
                            evidence_ids=[flow_evidence],
                        )
                    )
            contract_entities = {entity_ids.get(item["requestType"])} | {
                entity_ids.get(response["type"]) for response in item["responses"]
            }
            for related in flow["related"]:
                related_entity = entity_ids.get(related["type"])
                if related_entity and related_entity not in contract_entities:
                    relationships.append(
                        Relationship(
                            id=stable_id(
                                "relationship", "REFERENCES", operation_id, related_entity
                            ),
                            kind=RelationshipKind.REFERENCES,
                            source_id=operation_id,
                            target_id=related_entity,
                            evidence_ids=[flow_evidence],
                        )
                    )
        request_id = entity_ids.get(item["requestType"])
        parameters = [
            Parameter(
                id=stable_id("parameter", operation_id, parameter["location"], parameter["name"]),
                name=parameter["name"],
                location=ParameterLocation(parameter["location"]),
                required=parameter["required"],
                type=_type_ref(
                    parameter["type"],
                    not parameter["required"],
                    False,
                    entity_ids.get(parameter["type"]),
                ),
            )
            for parameter in item["parameters"]
        ]
        responses = [
            Response(
                id=stable_id("response", operation_id, str(response["statusCode"])),
                status_code=response["statusCode"],
                entity_id=entity_ids.get(response["type"]),
                type=(
                    _type_ref(
                        response["type"],
                        False,
                        False,
                        entity_ids.get(response["type"]),
                    )
                    if response["type"]
                    else None
                ),
            )
            for response in item["responses"]
        ]
        operations.append(
            Operation(
                id=operation_id,
                name=item["name"],
                method=item["method"],
                route=item["route"],
                parameters=parameters,
                request_entity_id=request_id,
                responses=responses,
                evidence_ids=operation_evidence_ids,
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
                        id=stable_id("relationship", "RETURNS", operation_id, response.entity_id),
                        kind=RelationshipKind.RETURNS,
                        source_id=operation_id,
                        target_id=response.entity_id,
                        evidence_ids=[operation_evidence],
                    )
                )

    diagnostics = [
        Diagnostic(
            id=stable_id("diagnostic", item["code"], item["message"]),
            severity=Severity(item["severity"]),
            code=item["code"],
            message=item["message"],
        )
        for item in raw["diagnostics"]
    ]
    for entity in entities:
        entity.attributes = _unique_by_id(entity.attributes)
    for operation in operations:
        operation.parameters = _unique_by_id(operation.parameters)
        operation.responses = _unique_by_id(operation.responses)

    sources = _unique_by_id(sources)
    operations = _unique_by_id(operations)
    entities = _unique_by_id(entities)
    enums = _unique_by_id(enums)
    validations = _unique_by_id(validations)
    relationships = _unique_by_id(relationships)
    evidence = _unique_by_id(evidence)
    lineage = _unique_by_id(lineage)
    diagnostics = _unique_by_id(diagnostics)

    return DiscoveryModel(
        run=RunMetadata(
            id=stable_id("run", "roslyn", region, system),
            status=RunStatus.FAILED
            if any(item.severity == Severity.ERROR for item in diagnostics)
            else RunStatus.COMPLETE,
            tool_version="0.1.0",
        ),
        region=region,
        system=system,
        sources=sorted(sources, key=lambda item: item.path),
        operations=sorted(operations, key=lambda item: (item.route, item.method)),
        entities=sorted(entities, key=lambda item: item.name),
        enums=sorted(enums, key=lambda item: item.name),
        validations=sorted(validations, key=lambda item: item.id),
        relationships=sorted(relationships, key=lambda item: item.id),
        evidence=sorted(evidence, key=lambda item: item.id),
        lineage=sorted(lineage, key=lambda item: item.id),
        diagnostics=sorted(diagnostics, key=lambda item: item.id),
        summary=Summary(
            operation_count=len(operations),
            entity_count=len(entities),
            enum_count=len(enums),
            relationship_count=len(relationships),
            diagnostic_count=len(diagnostics),
        ),
    )


def _type_ref(name: str, nullable: bool, collection: bool, reference_id: str | None) -> TypeRef:
    lowered = name.lower()
    if reference_id:
        kind = TypeKind.OBJECT if reference_id.startswith("entity-") else TypeKind.ENUM
    elif "guid" in lowered:
        kind = TypeKind.UUID
    elif "datetime" in lowered:
        kind = TypeKind.DATE_TIME
    elif lowered in {"int", "long", "short", "system.int32", "system.int64"}:
        kind = TypeKind.INTEGER
    elif lowered in {"decimal", "double", "float", "system.decimal"}:
        kind = TypeKind.NUMBER
    elif lowered in {"bool", "system.boolean"}:
        kind = TypeKind.BOOLEAN
    elif lowered in {"string", "system.string"}:
        kind = TypeKind.STRING
    else:
        kind = TypeKind.UNKNOWN
    return TypeRef(
        kind=kind,
        name=name,
        nullable=nullable,
        collection=collection,
        reference_id=reference_id,
    )


def _relative(path: str, repository: Path) -> str:
    return Path(path).resolve().relative_to(repository).as_posix()


def _camel(value: str) -> str:
    return value[:1].lower() + value[1:]


def _unique_by_id(items: list[Any]) -> list[Any]:
    """Keep the first deterministic observation for each stable model ID."""
    return list({item.id: item for item in reversed(items)}.values())[::-1]
