"""Deterministic normalization and reconciliation of discovery evidence."""

from __future__ import annotations

import re

from canonical_model_generator.model import (
    Diagnostic,
    DiscoveryModel,
    RunMetadata,
    RunStatus,
    Severity,
    Summary,
    stable_id,
)
from canonical_model_generator.view_model_scope import scope_to_endpoint_view_models


def normalize_name(value: str) -> str:
    normalized = re.sub(r"[^a-z0-9]", "", value.lower())
    return normalized[:-3] if normalized.endswith("dto") else normalized


def normalize_route(value: str) -> str:
    return re.sub(r"\{([^}:]+):[^}]+\}", r"{\1}", value.rstrip("/").lower()) or "/"


def reconcile(roslyn: DiscoveryModel, openapi: DiscoveryModel) -> DiscoveryModel:
    if (roslyn.region, roslyn.system) != (openapi.region, openapi.system):
        raise ValueError("Discovery sources must describe the same region and system")

    result = roslyn.model_copy(deep=True)
    remap: dict[str, str] = {}
    diagnostics = list(result.diagnostics) + list(openapi.diagnostics)
    entity_by_key = {normalize_name(item.name): item for item in result.entities}
    enum_by_key = {normalize_name(item.name): item for item in result.enums}
    operation_by_key = {
        (item.method, normalize_route(item.route)): item for item in result.operations
    }

    for source_entity in openapi.entities:
        target = entity_by_key.get(normalize_name(source_entity.name))
        if target is None:
            result.entities.append(source_entity.model_copy(deep=True))
            continue
        remap[source_entity.id] = target.id
        target.evidence_ids = sorted(set(target.evidence_ids + source_entity.evidence_ids))
        attributes = {normalize_name(item.name): item for item in target.attributes}
        for source_attribute in source_entity.attributes:
            target_attribute = attributes.get(normalize_name(source_attribute.name))
            if target_attribute is None:
                target.attributes.append(source_attribute.model_copy(deep=True))
                continue
            remap[source_attribute.id] = target_attribute.id
            target_attribute.evidence_ids = sorted(
                set(target_attribute.evidence_ids + source_attribute.evidence_ids)
            )
            if (
                target_attribute.type.kind != source_attribute.type.kind
                or target_attribute.required != source_attribute.required
                or target_attribute.type.collection != source_attribute.type.collection
            ):
                diagnostics.append(
                    Diagnostic(
                        id=stable_id("diagnostic", "RECONCILE_ATTRIBUTE", target_attribute.id),
                        severity=Severity.WARNING,
                        code="RECONCILE_ATTRIBUTE",
                        message=(
                            f"Conflicting type or requiredness evidence for "
                            f"{target.name}.{target_attribute.name}"
                        ),
                        subject_ids=[target_attribute.id],
                        evidence_ids=sorted(
                            set(target_attribute.evidence_ids + source_attribute.evidence_ids)
                        ),
                    )
                )

    for source_enum in openapi.enums:
        target = enum_by_key.get(normalize_name(source_enum.name))
        if target is None:
            result.enums.append(source_enum.model_copy(deep=True))
            continue
        remap[source_enum.id] = target.id
        target.evidence_ids = sorted(set(target.evidence_ids + source_enum.evidence_ids))
        if {str(item.value) for item in target.values} != {
            str(item.value) for item in source_enum.values
        }:
            diagnostics.append(
                Diagnostic(
                    id=stable_id("diagnostic", "RECONCILE_ENUM", target.id),
                    severity=Severity.WARNING,
                    code="RECONCILE_ENUM",
                    message=f"Conflicting enum values for {target.name}",
                    subject_ids=[target.id],
                    evidence_ids=target.evidence_ids,
                )
            )

    for source_operation in openapi.operations:
        key = (source_operation.method, normalize_route(source_operation.route))
        target = operation_by_key.get(key)
        if target is None:
            result.operations.append(source_operation.model_copy(deep=True))
            continue
        remap[source_operation.id] = target.id
        target.evidence_ids = sorted(set(target.evidence_ids + source_operation.evidence_ids))
        target_parameters = {
            (item.location, normalize_name(item.name)): item for item in target.parameters
        }
        for parameter in source_operation.parameters:
            match = target_parameters.get((parameter.location, normalize_name(parameter.name)))
            if match:
                remap[parameter.id] = match.id
        target_responses = {item.status_code: item for item in target.responses}
        for response in source_operation.responses:
            match = target_responses.get(response.status_code)
            if match:
                remap[response.id] = match.id

    result.sources = sorted(result.sources + openapi.sources, key=lambda item: item.id)
    result.evidence = sorted(
        result.evidence
        + [
            item.model_copy(update={"subject_id": remap.get(item.subject_id, item.subject_id)})
            for item in openapi.evidence
        ],
        key=lambda item: item.id,
    )
    result.lineage = sorted(
        result.lineage
        + [
            item.model_copy(update={"subject_id": remap.get(item.subject_id, item.subject_id)})
            for item in openapi.lineage
        ],
        key=lambda item: item.id,
    )
    result.validations = sorted(
        result.validations
        + [
            item.model_copy(update={"target_id": remap.get(item.target_id, item.target_id)})
            for item in openapi.validations
        ],
        key=lambda item: item.id,
    )

    relationships = {}
    for item in result.relationships + openapi.relationships:
        source_id = remap.get(item.source_id, item.source_id)
        target_id = remap.get(item.target_id, item.target_id)
        key = (item.kind, source_id, target_id)
        if key in relationships:
            relationships[key].evidence_ids = sorted(
                set(relationships[key].evidence_ids + item.evidence_ids)
            )
        else:
            relationships[key] = item.model_copy(
                update={
                    "id": stable_id("relationship", item.kind, source_id, target_id),
                    "source_id": source_id,
                    "target_id": target_id,
                }
            )
    result.relationships = sorted(relationships.values(), key=lambda item: item.id)
    result.operations.sort(key=lambda item: (normalize_route(item.route), item.method))
    result.entities.sort(key=lambda item: normalize_name(item.name))
    result.enums.sort(key=lambda item: normalize_name(item.name))
    result.diagnostics = sorted(diagnostics, key=lambda item: item.id)
    result.run = RunMetadata(
        id=stable_id("run", "reconciled", result.region, result.system),
        status=RunStatus.PARTIAL if result.diagnostics else RunStatus.COMPLETE,
        tool_version="0.1.0",
    )
    result.summary = Summary(
        operation_count=len(result.operations),
        entity_count=len(result.entities),
        enum_count=len(result.enums),
        relationship_count=len(result.relationships),
        diagnostic_count=len(result.diagnostics),
    )
    return scope_to_endpoint_view_models(DiscoveryModel.model_validate(result.model_dump()))
