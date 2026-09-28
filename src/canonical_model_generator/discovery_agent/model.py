"""Versioned, source-neutral DiscoveryModel v1 contract."""

from __future__ import annotations

from enum import StrEnum
from hashlib import sha256
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


def stable_id(kind: str, *coordinates: str) -> str:
    """Return a deterministic ID from normalized semantic coordinates."""
    normalized = "\x1f".join(value.strip().replace("\\", "/") for value in coordinates)
    return f"{kind}-{sha256(f'{kind}\x1e{normalized}'.encode()).hexdigest()[:20]}"


def _camel(value: str) -> str:
    head, *tail = value.split("_")
    return head + "".join(part.title() for part in tail)


class ContractModel(BaseModel):
    model_config = ConfigDict(alias_generator=_camel, populate_by_name=True, extra="forbid")


class SourceKind(StrEnum):
    ROSLYN = "roslyn"
    OPENAPI = "openapi"


class RunStatus(StrEnum):
    COMPLETE = "complete"
    PARTIAL = "partial"
    FAILED = "failed"


class Severity(StrEnum):
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"


class TypeKind(StrEnum):
    STRING = "string"
    INTEGER = "integer"
    NUMBER = "number"
    BOOLEAN = "boolean"
    UUID = "uuid"
    DATE_TIME = "date-time"
    OBJECT = "object"
    ENUM = "enum"
    UNKNOWN = "unknown"


class ParameterLocation(StrEnum):
    ROUTE = "route"
    QUERY = "query"
    HEADER = "header"
    BODY = "body"


class RelationshipKind(StrEnum):
    ACCEPTS = "ACCEPTS"
    RETURNS = "RETURNS"
    CONTAINS = "CONTAINS"
    INHERITS = "INHERITS"
    CALLS = "CALLS"


class RunMetadata(ContractModel):
    id: str
    status: RunStatus
    tool_version: str


class SourceDescriptor(ContractModel):
    id: str
    kind: SourceKind
    path: str
    sha256: str = Field(pattern=r"^[0-9a-f]{64}$")


class TypeRef(ContractModel):
    kind: TypeKind
    name: str
    nullable: bool = False
    collection: bool = False
    reference_id: str | None = None
    format: str | None = None


class Parameter(ContractModel):
    id: str
    name: str
    location: ParameterLocation
    required: bool
    type: TypeRef


class Response(ContractModel):
    id: str
    status_code: int = Field(ge=100, le=599)
    entity_id: str | None = None
    type: TypeRef | None = None
    description: str | None = Field(default=None, max_length=2000)


class Operation(ContractModel):
    id: str
    name: str
    method: str
    route: str
    parameters: list[Parameter] = Field(default_factory=list)
    request_entity_id: str | None = None
    responses: list[Response] = Field(default_factory=list)
    evidence_ids: list[str] = Field(default_factory=list)


class Attribute(ContractModel):
    id: str
    name: str
    original_name: str
    type: TypeRef
    required: bool
    evidence_ids: list[str] = Field(default_factory=list)


class Entity(ContractModel):
    id: str
    name: str
    original_name: str
    attributes: list[Attribute] = Field(default_factory=list)
    base_entity_id: str | None = None
    evidence_ids: list[str] = Field(default_factory=list)


class EnumValue(ContractModel):
    name: str
    value: str | int


class EnumDefinition(ContractModel):
    id: str
    name: str
    values: list[EnumValue]
    evidence_ids: list[str] = Field(default_factory=list)


class ValidationRule(ContractModel):
    id: str
    target_id: str
    rule: str
    arguments: dict[str, Any] = Field(default_factory=dict)
    evidence_ids: list[str] = Field(default_factory=list)


class Relationship(ContractModel):
    id: str
    kind: RelationshipKind
    source_id: str
    target_id: str
    evidence_ids: list[str] = Field(default_factory=list)


class Evidence(ContractModel):
    id: str
    source_id: str
    subject_id: str
    observed_value: Any


class Lineage(ContractModel):
    id: str
    source_id: str
    subject_id: str
    path: str
    start_line: int | None = Field(default=None, ge=1)
    end_line: int | None = Field(default=None, ge=1)
    pointer: str | None = None

    @model_validator(mode="after")
    def validate_location(self) -> Lineage:
        if self.pointer is None and self.start_line is None:
            raise ValueError("lineage requires source lines or a document pointer")
        if self.start_line and self.end_line and self.end_line < self.start_line:
            raise ValueError("lineage endLine must not precede startLine")
        return self


class Diagnostic(ContractModel):
    id: str
    severity: Severity
    code: str
    message: str
    subject_ids: list[str] = Field(default_factory=list)
    evidence_ids: list[str] = Field(default_factory=list)


class Summary(ContractModel):
    operation_count: int = Field(ge=0)
    entity_count: int = Field(ge=0)
    enum_count: int = Field(ge=0)
    relationship_count: int = Field(ge=0)
    diagnostic_count: int = Field(ge=0)


class DiscoveryModel(ContractModel):
    contract_version: Literal["1.0"] = "1.0"
    run: RunMetadata
    region: str = Field(min_length=1)
    system: str = Field(min_length=1)
    sources: list[SourceDescriptor]
    operations: list[Operation] = Field(default_factory=list)
    entities: list[Entity] = Field(default_factory=list)
    enums: list[EnumDefinition] = Field(default_factory=list)
    validations: list[ValidationRule] = Field(default_factory=list)
    relationships: list[Relationship] = Field(default_factory=list)
    evidence: list[Evidence] = Field(default_factory=list)
    lineage: list[Lineage] = Field(default_factory=list)
    diagnostics: list[Diagnostic] = Field(default_factory=list)
    summary: Summary

    @model_validator(mode="after")
    def validate_graph(self) -> DiscoveryModel:
        source_ids = {item.id for item in self.sources}
        evidence_ids = {item.id for item in self.evidence}
        subject_ids = {item.id for item in self.operations + self.entities + self.enums}
        subject_ids.update(
            parameter.id for operation in self.operations for parameter in operation.parameters
        )
        subject_ids.update(
            response.id for operation in self.operations for response in operation.responses
        )
        subject_ids.update(
            attribute.id for entity in self.entities for attribute in entity.attributes
        )
        all_ids = source_ids | evidence_ids | subject_ids
        all_ids.update(
            item.id
            for item in self.validations + self.relationships + self.lineage + self.diagnostics
        )
        if len(all_ids) != sum(
            len(group)
            for group in (
                self.sources,
                self.operations,
                self.entities,
                self.enums,
                self.validations,
                self.relationships,
                self.evidence,
                self.lineage,
                self.diagnostics,
            )
        ) + sum(len(item.parameters) + len(item.responses) for item in self.operations) + sum(
            len(item.attributes) for item in self.entities
        ):
            raise ValueError("all model IDs must be globally unique")

        entity_ids = {item.id for item in self.entities}
        for operation in self.operations:
            refs = [operation.request_entity_id] + [item.entity_id for item in operation.responses]
            self._require(refs, entity_ids, "operation entity")
            self._require(operation.evidence_ids, evidence_ids, "operation evidence")
        for entity in self.entities:
            self._require([entity.base_entity_id], entity_ids, "base entity")
            self._require(entity.evidence_ids, evidence_ids, "entity evidence")
            for attribute in entity.attributes:
                if attribute.type.reference_id:
                    self._require(
                        [attribute.type.reference_id],
                        entity_ids | {e.id for e in self.enums},
                        "type",
                    )
                self._require(attribute.evidence_ids, evidence_ids, "attribute evidence")
        for item in self.evidence:
            self._require([item.source_id], source_ids, "evidence source")
            self._require([item.subject_id], subject_ids, "evidence subject")
        for item in self.lineage:
            self._require([item.source_id], source_ids, "lineage source")
            self._require([item.subject_id], subject_ids, "lineage subject")
        for item in self.relationships:
            self._require([item.source_id, item.target_id], subject_ids, "relationship endpoint")
            self._require(item.evidence_ids, evidence_ids, "relationship evidence")
        self._require(
            [item.target_id for item in self.validations], subject_ids, "validation target"
        )
        if self.summary != Summary(
            operation_count=len(self.operations),
            entity_count=len(self.entities),
            enum_count=len(self.enums),
            relationship_count=len(self.relationships),
            diagnostic_count=len(self.diagnostics),
        ):
            raise ValueError("summary counts do not match model contents")
        return self

    @staticmethod
    def _require(values: list[str | None], allowed: set[str], label: str) -> None:
        missing = sorted({value for value in values if value is not None and value not in allowed})
        if missing:
            raise ValueError(f"invalid {label} reference(s): {', '.join(missing)}")
