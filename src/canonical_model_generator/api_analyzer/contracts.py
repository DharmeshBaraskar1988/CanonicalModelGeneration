"""Stable provider-neutral contracts used by the API Analyzer workflow."""

from __future__ import annotations

from typing import Any, Literal, Protocol

from pydantic import Field

from canonical_model_generator.discovery_agent.model import ContractModel


class DomainSemantic(ContractModel):
    name: str = Field(min_length=1, max_length=160)
    confidence: float = Field(ge=0, le=1)
    suggested_name: str | None = Field(default=None, max_length=160)


class CapabilitySemantic(ContractModel):
    name: str = Field(min_length=1, max_length=160)
    confidence: float = Field(ge=0, le=1)
    suggested_name: str | None = Field(default=None, max_length=160)


class ResponseSemantic(ContractModel):
    status_code: int = Field(ge=100, le=599)
    description: str = Field(min_length=1, max_length=1000)


class EndpointSemantic(ContractModel):
    operation_id: str
    domain: DomainSemantic
    capability: CapabilitySemantic
    summary: str = Field(min_length=1, max_length=160)
    description: str = Field(min_length=1, max_length=4000)
    business_purpose: str = Field(min_length=1, max_length=2000)
    request_description: str = Field(min_length=1, max_length=2000)
    responses: list[ResponseSemantic] = Field(default_factory=list)
    tags: list[str] = Field(default_factory=list)
    confidence: float = Field(ge=0, le=1)
    requested_symbols: list[str] = Field(default_factory=list, max_length=8)
    context_gaps: list[str] = Field(default_factory=list, max_length=8)


class AttributeSemantic(ContractModel):
    attribute_id: str
    summary: str = Field(min_length=1, max_length=240)
    description: str = Field(min_length=1, max_length=2000)
    business_concept: str = Field(min_length=1, max_length=240)
    business_meaning: str = Field(min_length=1, max_length=2000)
    confidence: float = Field(ge=0, le=1)


class EntitySemantic(ContractModel):
    entity_id: str
    domain: DomainSemantic
    business_concept: str = Field(min_length=1, max_length=240)
    summary: str = Field(min_length=1, max_length=240)
    description: str = Field(min_length=1, max_length=3000)
    attributes: list[AttributeSemantic] = Field(default_factory=list)
    confidence: float = Field(ge=0, le=1)


class NormalizedAttribute(ContractModel):
    attribute_id: str
    original_name: str = Field(min_length=1, max_length=240)
    normalized_name: str = Field(min_length=1, max_length=240)
    normalized_description: str = Field(min_length=1, max_length=2000)
    confidence: float = Field(ge=0, le=1)


class NormalizedEntity(ContractModel):
    entity_id: str
    original_name: str = Field(min_length=1, max_length=240)
    normalized_name: str = Field(min_length=1, max_length=240)
    normalized_description: str = Field(min_length=1, max_length=3000)
    attributes: list[NormalizedAttribute] = Field(default_factory=list)
    confidence: float = Field(ge=0, le=1)


class EnumSemantic(ContractModel):
    enum_id: str
    domain: DomainSemantic
    business_concept: str = Field(min_length=1, max_length=240)
    summary: str = Field(min_length=1, max_length=240)
    description: str = Field(min_length=1, max_length=2000)
    confidence: float = Field(ge=0, le=1)


class CodeClaim(ContractModel):
    text: str = Field(min_length=1, max_length=1000)
    classification: Literal["observed", "inferred", "unknown"]
    confidence: float = Field(ge=0, le=1)
    evidence_chunk_ids: list[str] = Field(default_factory=list, max_length=8)


class CodeSemantic(ContractModel):
    summary: str = Field(min_length=1, max_length=400)
    role: str = Field(min_length=1, max_length=400)
    claims: list[CodeClaim] = Field(default_factory=list, max_length=12)
    gaps: list[str] = Field(default_factory=list, max_length=8)


class SemanticProvider(Protocol):
    """Port implemented by semantic-analysis providers."""

    @property
    def model_name(self) -> str: ...

    def validate_connection(self) -> None: ...

    def analyze_endpoint(self, context: dict[str, Any]) -> EndpointSemantic: ...

    def analyze_entity(self, context: dict[str, Any]) -> EntitySemantic: ...

    def analyze_enum(self, context: dict[str, Any]) -> EnumSemantic: ...

    def analyze_code(self, context: dict[str, Any]) -> CodeSemantic: ...
