"""Restrict Phase 1 entities to endpoint-reachable, user-authored models."""

from __future__ import annotations

from pathlib import PurePosixPath

from canonical_model_generator.discovery_agent.model import (
    DiscoveryModel,
    Relationship,
    RelationshipKind,
    SourceKind,
    Summary,
    stable_id,
)

GENERATED_PATH_PARTS = {"bin", "obj"}
GENERATED_SUFFIXES = (".g.cs", ".generated.cs", ".designer.cs")


def scope_to_endpoint_contract_models(model: DiscoveryModel) -> DiscoveryModel:
    """Keep user-authored types used by endpoints or their reachable model graph."""
    result = model.model_copy(deep=True)
    candidates = {
        entity.id: entity for entity in result.entities if _has_contract_source(result, entity.id)
    }
    retained_ids = {
        entity_id
        for operation in result.operations
        for entity_id in [
            operation.request_entity_id,
            *(response.entity_id for response in operation.responses),
            *(parameter.type.reference_id for parameter in operation.parameters),
        ]
        if entity_id in candidates
    }

    # Models an endpoint returns/accepts per the relationships (e.g. an OpenAPI response envelope
    # that the code returns without its wrapper).
    operation_ids = {operation.id for operation in result.operations}
    for relationship in result.relationships:
        if (
            relationship.kind in {RelationshipKind.ACCEPTS, RelationshipKind.RETURNS}
            and relationship.source_id in operation_ids
            and relationship.target_id in candidates
        ):
            retained_ids.add(relationship.target_id)

    # Models named by the OpenAPI document that exist in code (evidence marker from Roslyn hints).
    retained_ids.update(
        item.subject_id
        for item in result.evidence
        if isinstance(item.observed_value, dict)
        and item.observed_value.get("hint") == "openapi-schema"
        and item.subject_id in candidates
    )

    # Models the endpoint's handler flow touches (mapper endpoints, handler/mapper/client models).
    flow_edges: dict[str, set[str]] = {}
    for relationship in result.relationships:
        if (
            relationship.kind == RelationshipKind.REFERENCES
            and relationship.source_id in operation_ids
        ):
            if relationship.target_id in candidates:
                retained_ids.add(relationship.target_id)
        elif relationship.kind == RelationshipKind.MAPS_TO:
            flow_edges.setdefault(relationship.source_id, set()).add(relationship.target_id)
            flow_edges.setdefault(relationship.target_id, set()).add(relationship.source_id)

    pending = list(retained_ids)
    while pending:
        entity_id = pending.pop()
        entity = candidates[entity_id]
        referenced = {
            entity.base_entity_id,
            *(attribute.type.reference_id for attribute in entity.attributes),
            *flow_edges.get(entity_id, ()),
        }
        for reference_id in referenced:
            if reference_id in candidates and reference_id not in retained_ids:
                retained_ids.add(reference_id)
                pending.append(reference_id)

    result.entities = sorted(
        [entity for entity in result.entities if entity.id in retained_ids],
        key=lambda item: item.name,
    )
    retained_enum_ids = {
        attribute.type.reference_id
        for entity in result.entities
        for attribute in entity.attributes
        if attribute.type.reference_id is not None
        and attribute.type.reference_id.startswith("enum-")
    }
    result.enums = sorted(
        [enum for enum in result.enums if enum.id in retained_enum_ids],
        key=lambda item: item.name,
    )
    retained_type_ids = retained_ids | retained_enum_ids

    for operation in result.operations:
        if operation.request_entity_id not in retained_ids:
            operation.request_entity_id = None
        for response in operation.responses:
            if response.entity_id not in retained_ids:
                response.entity_id = None
        for parameter in operation.parameters:
            if parameter.type.reference_id not in retained_type_ids:
                parameter.type.reference_id = None
    for entity in result.entities:
        if entity.base_entity_id not in retained_ids:
            entity.base_entity_id = None
        for attribute in entity.attributes:
            if attribute.type.reference_id not in retained_type_ids:
                attribute.type.reference_id = None

    subject_ids = {item.id for item in result.operations + result.entities + result.enums}
    subject_ids.update(
        parameter.id for operation in result.operations for parameter in operation.parameters
    )
    subject_ids.update(
        response.id for operation in result.operations for response in operation.responses
    )
    subject_ids.update(
        attribute.id for entity in result.entities for attribute in entity.attributes
    )

    result.evidence = [item for item in result.evidence if item.subject_id in subject_ids]
    evidence_ids = {item.id for item in result.evidence}
    result.lineage = [item for item in result.lineage if item.subject_id in subject_ids]
    result.validations = [
        item.model_copy(
            update={"evidence_ids": [value for value in item.evidence_ids if value in evidence_ids]}
        )
        for item in result.validations
        if item.target_id in subject_ids
    ]
    result.relationships = [
        item.model_copy(
            update={"evidence_ids": [value for value in item.evidence_ids if value in evidence_ids]}
        )
        for item in result.relationships
        if item.source_id in subject_ids and item.target_id in subject_ids
    ]
    relationship_keys = {
        (item.kind, item.source_id, item.target_id) for item in result.relationships
    }
    for entity in result.entities:
        for attribute in entity.attributes:
            target_id = attribute.type.reference_id
            key = (RelationshipKind.CONTAINS, entity.id, target_id)
            if target_id not in retained_ids or key in relationship_keys:
                continue
            result.relationships.append(
                Relationship(
                    id=stable_id("relationship", "CONTAINS", entity.id, target_id),
                    kind=RelationshipKind.CONTAINS,
                    source_id=entity.id,
                    target_id=target_id,
                    evidence_ids=[
                        value for value in attribute.evidence_ids if value in evidence_ids
                    ],
                )
            )
            relationship_keys.add(key)
    result.relationships.sort(key=lambda item: item.id)
    for operation in result.operations:
        operation.evidence_ids = [
            value for value in operation.evidence_ids if value in evidence_ids
        ]
    for entity in result.entities:
        entity.evidence_ids = [value for value in entity.evidence_ids if value in evidence_ids]
        for attribute in entity.attributes:
            attribute.evidence_ids = [
                value for value in attribute.evidence_ids if value in evidence_ids
            ]
    for enum in result.enums:
        enum.evidence_ids = [value for value in enum.evidence_ids if value in evidence_ids]
    result.diagnostics = [
        item.model_copy(
            update={
                "subject_ids": [value for value in item.subject_ids if value in subject_ids],
                "evidence_ids": [value for value in item.evidence_ids if value in evidence_ids],
            }
        )
        for item in result.diagnostics
    ]

    used_source_ids = {item.source_id for item in result.evidence + result.lineage}
    result.sources = [item for item in result.sources if item.id in used_source_ids]
    result.run.id = stable_id("run", "endpoint-contract-model-scope", model.run.id)
    result.summary = Summary(
        operation_count=len(result.operations),
        entity_count=len(result.entities),
        enum_count=len(result.enums),
        relationship_count=len(result.relationships),
        diagnostic_count=len(result.diagnostics),
    )
    return DiscoveryModel.model_validate(result.model_dump())


def scope_to_endpoint_view_models(model: DiscoveryModel) -> DiscoveryModel:
    """Backward-compatible name for the endpoint contract-model boundary."""
    return scope_to_endpoint_contract_models(model)


def _has_contract_source(model: DiscoveryModel, subject_id: str) -> bool:
    """User-authored Roslyn source, or an OpenAPI schema (reachable ones are kept by callers)."""
    sources = {item.id: item for item in model.sources}
    for lineage in model.lineage:
        source = sources.get(lineage.source_id)
        if lineage.subject_id != subject_id or source is None:
            continue
        if source.kind == SourceKind.OPENAPI:
            return True
        if source.kind != SourceKind.ROSLYN:
            continue
        path = PurePosixPath(lineage.path.replace("\\", "/"))
        lowered_parts = {part.lower() for part in path.parts}
        lowered_name = path.name.lower()
        if not lowered_parts.intersection(GENERATED_PATH_PARTS) and not lowered_name.endswith(
            GENERATED_SUFFIXES
        ):
            return True
    return False
