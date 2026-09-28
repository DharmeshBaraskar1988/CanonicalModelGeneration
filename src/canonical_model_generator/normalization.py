"""Phase 2 deterministic cross-region technical normalization."""

from __future__ import annotations

import re
from typing import Any, Literal

from pydantic import Field, model_validator

from canonical_model_generator.discovery_agent.model import (
    ContractModel,
    DiscoveryModel,
    TypeKind,
    TypeRef,
)


class SourceLocation(ContractModel):
    source: str
    location: str


class NormalizedType(ContractModel):
    data_type: TypeKind
    source_type: str
    referenced_model: str | None = None
    nullable: bool = False
    collection: bool = False
    format: str | None = None


class NormalizedRule(ContractModel):
    rule: str
    arguments: dict[str, Any] = Field(default_factory=dict)
    supported_by: list[SourceLocation] = Field(default_factory=list)


class NormalizedField(ContractModel):
    normalized_name: str
    source_name: str
    type: NormalizedType
    required: bool
    validations: list[NormalizedRule] = Field(default_factory=list)
    supported_by: list[SourceLocation] = Field(default_factory=list)


class NormalizedEntity(ContractModel):
    normalized_name: str
    source_name: str
    inherits_from: str | None = None
    fields: list[NormalizedField] = Field(default_factory=list)
    supported_by: list[SourceLocation] = Field(default_factory=list)


class NormalizedParameter(ContractModel):
    normalized_name: str
    source_name: str
    location: str
    required: bool
    type: NormalizedType


class NormalizedResponse(ContractModel):
    status_code: int
    response_model: str | None = None


class NormalizedOperation(ContractModel):
    normalized_name: str
    source_name: str
    method: str
    normalized_route: str
    source_route: str
    request_model: str | None = None
    parameters: list[NormalizedParameter] = Field(default_factory=list)
    responses: list[NormalizedResponse] = Field(default_factory=list)
    supported_by: list[SourceLocation] = Field(default_factory=list)


class NormalizedEnumValue(ContractModel):
    normalized_name: str
    source_name: str
    value: str | int


class NormalizedEnum(ContractModel):
    normalized_name: str
    source_name: str
    values: list[NormalizedEnumValue] = Field(default_factory=list)
    supported_by: list[SourceLocation] = Field(default_factory=list)


class NormalizedRelationship(ContractModel):
    relationship: str
    source: str
    target: str
    supported_by: list[SourceLocation] = Field(default_factory=list)


class NormalizedDiagnostic(ContractModel):
    severity: str
    code: str
    message: str
    affected_items: list[str] = Field(default_factory=list)
    supported_by: list[SourceLocation] = Field(default_factory=list)


class NormalizedSource(ContractModel):
    region: str
    system: str
    discovery_status: str
    operations: list[NormalizedOperation] = Field(default_factory=list)
    entities: list[NormalizedEntity] = Field(default_factory=list)
    enums: list[NormalizedEnum] = Field(default_factory=list)
    relationships: list[NormalizedRelationship] = Field(default_factory=list)
    diagnostics: list[NormalizedDiagnostic] = Field(default_factory=list)


class NormalizationSummary(ContractModel):
    source_count: int = Field(ge=1)
    operation_count: int = Field(ge=0)
    entity_count: int = Field(ge=0)
    enum_count: int = Field(ge=0)
    relationship_count: int = Field(ge=0)
    diagnostic_count: int = Field(ge=0)


class NormalizedDiscoveryPortfolio(ContractModel):
    contract_version: Literal["1.0"] = "1.0"
    phase: Literal["technical-normalization"] = "technical-normalization"
    rules_applied: list[str]
    sources: list[NormalizedSource]
    summary: NormalizationSummary

    @model_validator(mode="after")
    def validate_summary(self) -> NormalizedDiscoveryPortfolio:
        expected = NormalizationSummary(
            source_count=len(self.sources),
            operation_count=sum(len(source.operations) for source in self.sources),
            entity_count=sum(len(source.entities) for source in self.sources),
            enum_count=sum(len(source.enums) for source in self.sources),
            relationship_count=sum(len(source.relationships) for source in self.sources),
            diagnostic_count=sum(len(source.diagnostics) for source in self.sources),
        )
        if self.summary != expected:
            raise ValueError("normalization summary does not match portfolio contents")
        return self


NORMALIZATION_RULES = [
    "Identifiers are represented as deterministic snake_case comparison names.",
    "Original source names are preserved beside normalized names.",
    "Routes use lowercase static segments, snake_case parameters, and no route constraints.",
    "Types use the DiscoveryModel v1 source-neutral technical type vocabulary.",
    "Requiredness, nullability, collections, formats, validations, and lineage are preserved.",
    "No semantic matching, classification, or canonical-model proposal is performed.",
]


def normalize_discoveries(
    discoveries: list[DiscoveryModel],
) -> NormalizedDiscoveryPortfolio:
    if not discoveries:
        raise ValueError("Phase 2 requires at least one accepted DiscoveryModel")
    validated = [DiscoveryModel.model_validate(item.model_dump()) for item in discoveries]
    sources = sorted(
        (_normalize_source(model) for model in validated),
        key=lambda source: (source.region.lower(), source.system.lower()),
    )
    return NormalizedDiscoveryPortfolio(
        rules_applied=NORMALIZATION_RULES,
        sources=sources,
        summary=NormalizationSummary(
            source_count=len(sources),
            operation_count=sum(len(source.operations) for source in sources),
            entity_count=sum(len(source.entities) for source in sources),
            enum_count=sum(len(source.enums) for source in sources),
            relationship_count=sum(len(source.relationships) for source in sources),
            diagnostic_count=sum(len(source.diagnostics) for source in sources),
        ),
    )


def normalize_identifier(value: str) -> str:
    separated = re.sub(r"([A-Z]+)([A-Z][a-z])", r"\1_\2", value)
    separated = re.sub(r"([a-z0-9])([A-Z])", r"\1_\2", separated)
    words = re.findall(r"[A-Za-z0-9]+", separated)
    return "_".join(word.lower() for word in words) or "unnamed"


def normalize_route(value: str) -> str:
    route = value.strip() or "/"

    def normalize_parameter(match: re.Match[str]) -> str:
        parameter = match.group(1).split(":", 1)[0]
        return "{" + normalize_identifier(parameter) + "}"

    route = re.sub(r"\{([^}]+)\}", normalize_parameter, route)
    segments = [
        segment if segment.startswith("{") else segment.lower()
        for segment in route.strip("/").split("/")
        if segment
    ]
    return "/" + "/".join(segments) if segments else "/"


def _normalize_source(model: DiscoveryModel) -> NormalizedSource:
    type_names = {entity.id: entity.name for entity in model.entities}
    type_names.update({enum.id: enum.name for enum in model.enums})
    validation_by_target: dict[str, list[NormalizedRule]] = {}
    for validation in model.validations:
        validation_by_target.setdefault(validation.target_id, []).append(
            NormalizedRule(
                rule=validation.rule,
                arguments=validation.arguments,
                supported_by=_supporting_sources(model, validation.evidence_ids),
            )
        )

    entities = []
    for entity in model.entities:
        fields = [
            NormalizedField(
                normalized_name=normalize_identifier(attribute.name),
                source_name=attribute.original_name,
                type=_normalized_type(attribute.type, type_names),
                required=attribute.required,
                validations=sorted(
                    validation_by_target.get(attribute.id, []),
                    key=lambda rule: (rule.rule, str(rule.arguments)),
                ),
                supported_by=_supporting_sources(model, attribute.evidence_ids),
            )
            for attribute in entity.attributes
        ]
        entities.append(
            NormalizedEntity(
                normalized_name=normalize_identifier(entity.name),
                source_name=entity.original_name,
                inherits_from=type_names.get(entity.base_entity_id),
                fields=sorted(fields, key=lambda field: (field.normalized_name, field.source_name)),
                supported_by=_supporting_sources(model, entity.evidence_ids),
            )
        )

    operations = []
    for operation in model.operations:
        parameters = [
            NormalizedParameter(
                normalized_name=normalize_identifier(parameter.name),
                source_name=parameter.name,
                location=parameter.location.value,
                required=parameter.required,
                type=_normalized_type(parameter.type, type_names),
            )
            for parameter in operation.parameters
        ]
        responses = [
            NormalizedResponse(
                status_code=response.status_code,
                response_model=type_names.get(response.entity_id),
            )
            for response in operation.responses
        ]
        operations.append(
            NormalizedOperation(
                normalized_name=normalize_identifier(operation.name),
                source_name=operation.name,
                method=operation.method.upper(),
                normalized_route=normalize_route(operation.route),
                source_route=operation.route,
                request_model=type_names.get(operation.request_entity_id),
                parameters=sorted(
                    parameters,
                    key=lambda parameter: (
                        parameter.location,
                        parameter.normalized_name,
                    ),
                ),
                responses=sorted(responses, key=lambda response: response.status_code),
                supported_by=_supporting_sources(model, operation.evidence_ids),
            )
        )

    enums = [
        NormalizedEnum(
            normalized_name=normalize_identifier(enum.name),
            source_name=enum.name,
            values=[
                NormalizedEnumValue(
                    normalized_name=normalize_identifier(value.name),
                    source_name=value.name,
                    value=value.value,
                )
                for value in enum.values
            ],
            supported_by=_supporting_sources(model, enum.evidence_ids),
        )
        for enum in model.enums
    ]
    subjects = _subject_names(model)
    relationships = [
        NormalizedRelationship(
            relationship=relationship.kind.value,
            source=subjects.get(relationship.source_id, "Unknown source"),
            target=subjects.get(relationship.target_id, "Unknown target"),
            supported_by=_supporting_sources(model, relationship.evidence_ids),
        )
        for relationship in model.relationships
    ]
    diagnostics = [
        NormalizedDiagnostic(
            severity=diagnostic.severity.value,
            code=diagnostic.code,
            message=diagnostic.message,
            affected_items=[
                subjects.get(subject_id, "Unknown item") for subject_id in diagnostic.subject_ids
            ],
            supported_by=_supporting_sources(model, diagnostic.evidence_ids),
        )
        for diagnostic in model.diagnostics
    ]
    return NormalizedSource(
        region=model.region,
        system=model.system,
        discovery_status=model.run.status.value,
        operations=sorted(
            operations,
            key=lambda operation: (operation.normalized_route, operation.method),
        ),
        entities=sorted(
            entities,
            key=lambda entity: (entity.normalized_name, entity.source_name),
        ),
        enums=sorted(enums, key=lambda enum: (enum.normalized_name, enum.source_name)),
        relationships=sorted(
            relationships,
            key=lambda relationship: (
                relationship.relationship,
                relationship.source,
                relationship.target,
            ),
        ),
        diagnostics=sorted(
            diagnostics,
            key=lambda diagnostic: (diagnostic.severity, diagnostic.code, diagnostic.message),
        ),
    )


def _normalized_type(type_ref: TypeRef, type_names: dict[str, str]) -> NormalizedType:
    return NormalizedType(
        data_type=type_ref.kind,
        source_type=type_ref.name,
        referenced_model=type_names.get(type_ref.reference_id),
        nullable=type_ref.nullable,
        collection=type_ref.collection,
        format=type_ref.format,
    )


def _subject_names(model: DiscoveryModel) -> dict[str, str]:
    subjects = {
        operation.id: f"{operation.name} ({operation.method} {operation.route})"
        for operation in model.operations
    }
    for entity in model.entities:
        subjects[entity.id] = entity.name
        subjects.update(
            {attribute.id: f"{entity.name}.{attribute.name}" for attribute in entity.attributes}
        )
    subjects.update({enum.id: enum.name for enum in model.enums})
    return subjects


def _supporting_sources(
    model: DiscoveryModel,
    evidence_ids: list[str],
) -> list[SourceLocation]:
    evidence_by_id = {evidence.id: evidence for evidence in model.evidence}
    source_by_id = {source.id: source for source in model.sources}
    lineage_by_subject_source = {
        (lineage.subject_id, lineage.source_id): lineage for lineage in model.lineage
    }
    locations = []
    seen: set[tuple[str, str]] = set()
    for evidence_id in evidence_ids:
        evidence = evidence_by_id.get(evidence_id)
        if evidence is None:
            continue
        source = source_by_id.get(evidence.source_id)
        if source is None:
            continue
        lineage = lineage_by_subject_source.get((evidence.subject_id, evidence.source_id))
        location = source.path
        if lineage is not None and lineage.pointer:
            location = f"{lineage.path}{lineage.pointer}"
        elif lineage is not None and lineage.start_line:
            location = f"{lineage.path}:line {lineage.start_line}"
        key = (source.kind.value, location)
        if key in seen:
            continue
        seen.add(key)
        locations.append(SourceLocation(source=source.kind.value, location=location))
    return locations
