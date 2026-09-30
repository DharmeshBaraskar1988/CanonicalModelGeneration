"""Deterministic normalization and reconciliation of discovery evidence."""

from __future__ import annotations

import re

from canonical_model_generator.discovery_agent.model import (
    Diagnostic,
    DiscoveryModel,
    Entity,
    RunMetadata,
    RunStatus,
    Severity,
    Summary,
    stable_id,
)
from canonical_model_generator.discovery_agent.view_model_scope import scope_to_endpoint_view_models


def normalize_name(value: str) -> str:
    normalized = re.sub(r"[^a-z0-9]", "", value.lower())
    return normalized[:-3] if normalized.endswith("dto") else normalized


def normalize_route(value: str) -> str:
    return re.sub(r"\{([^}:]+):[^}]+\}", r"{\1}", value.rstrip("/").lower()) or "/"


def _route_segments(route: str) -> list[str]:
    return [
        "{}" if segment.startswith("{") else segment
        for segment in normalize_route(route).strip("/").split("/")
        if segment
    ]


def _is_route_suffix(spec_route: str, code_route: str) -> bool:
    """OpenAPI paths are usually relative to a server/base path the code route includes."""
    spec, code = _route_segments(spec_route), _route_segments(code_route)
    return bool(spec) and len(spec) <= len(code) and code[len(code) - len(spec) :] == spec


def _attribute_overlap(left: Entity, right: Entity) -> float:
    names_left = {normalize_name(item.name) for item in left.attributes}
    names_right = {normalize_name(item.name) for item in right.attributes}
    union = names_left | names_right
    return len(names_left & names_right) / len(union) if union else 0.0


def _remap_type_reference(type_ref, remap: dict[str, str]):
    if type_ref is None or type_ref.reference_id is None:
        return type_ref
    return type_ref.model_copy(
        update={"reference_id": remap.get(type_ref.reference_id, type_ref.reference_id)}
    )


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

    # Pair operations first (exact route, else the spec path as a suffix of the code route), then
    # use each pair to find the request/response model the spec and the code both mean, even when
    # their names differ, and to see through `data` response envelopes.
    matched: dict[str, object] = {}
    claimed: set[str] = set()
    for source_operation in sorted(
        openapi.operations,
        key=lambda item: (-len(_route_segments(item.route)), item.route, item.method),
    ):
        exact = operation_by_key.get(
            (source_operation.method, normalize_route(source_operation.route))
        )
        candidates = (
            [exact]
            if exact is not None
            else [
                item
                for item in result.operations
                if item.method == source_operation.method
                and item.id not in claimed
                and _is_route_suffix(source_operation.route, item.route)
            ]
        )
        if len(candidates) == 1:
            matched[source_operation.id] = candidates[0]
            claimed.add(candidates[0].id)
            if exact is None:
                diagnostics.append(
                    Diagnostic(
                        id=stable_id("diagnostic", "RECONCILE_ROUTE_PREFIX", source_operation.id),
                        severity=Severity.INFO,
                        code="RECONCILE_ROUTE_PREFIX",
                        message=(
                            f"OpenAPI {source_operation.method} {source_operation.route} matched "
                            f"code route {candidates[0].route} "
                            "(spec path is relative to a base path)"
                        ),
                        subject_ids=[candidates[0].id],
                    )
                )
        elif len(candidates) > 1:
            diagnostics.append(
                Diagnostic(
                    id=stable_id("diagnostic", "RECONCILE_ROUTE_AMBIGUOUS", source_operation.id),
                    severity=Severity.WARNING,
                    code="RECONCILE_ROUTE_AMBIGUOUS",
                    message=(
                        f"OpenAPI {source_operation.method} {source_operation.route} matches "
                        f"{len(candidates)} code routes; not merged"
                    ),
                )
            )

    spec_entities = {item.id: item for item in openapi.entities}
    code_entities = {item.id: item for item in result.entities}
    pair_override: dict[str, Entity] = {}
    envelope_inner: dict[str, str] = {}
    pending_pairs: list[tuple[str | None, str | None]] = []
    for source_operation in openapi.operations:
        code_operation = matched.get(source_operation.id)
        if code_operation is None:
            continue
        pending_pairs.append((source_operation.request_entity_id, code_operation.request_entity_id))
        code_responses = {item.status_code: item for item in code_operation.responses}
        for response in source_operation.responses:
            counterpart = code_responses.get(response.status_code)
            if counterpart is not None:
                pending_pairs.append((response.entity_id, counterpart.entity_id))
    seen_pairs: set[tuple[str, str]] = set()
    while pending_pairs:
        spec_id, code_id = pending_pairs.pop(0)
        spec_entity, code_entity = spec_entities.get(spec_id), code_entities.get(code_id)
        if spec_entity is None or code_entity is None or (spec_id, code_id) in seen_pairs:
            continue
        seen_pairs.add((spec_id, code_id))
        if normalize_name(spec_entity.name) == normalize_name(code_entity.name):
            continue
        inner = next(
            (
                spec_entities[attribute.type.reference_id]
                for attribute in spec_entity.attributes
                if normalize_name(attribute.name) == "data"
                and attribute.type.reference_id in spec_entities
            ),
            None,
        )
        best = max(
            [item for item in (spec_entity, inner) if item is not None],
            key=lambda item: _attribute_overlap(item, code_entity),
        )
        if _attribute_overlap(best, code_entity) < 0.5:
            continue
        pair_override[best.id] = code_entity
        if best is not spec_entity:
            envelope_inner[spec_entity.id] = best.id
        code_attributes = {normalize_name(item.name): item for item in code_entity.attributes}
        for attribute in best.attributes:
            counterpart_attribute = code_attributes.get(normalize_name(attribute.name))
            if counterpart_attribute is not None:
                pending_pairs.append(
                    (attribute.type.reference_id, counterpart_attribute.type.reference_id)
                )

    for source_entity in openapi.entities:
        target = pair_override.get(source_entity.id) or entity_by_key.get(
            normalize_name(source_entity.name)
        )
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
        target = matched.get(source_operation.id)
        if target is None:
            result.operations.append(source_operation.model_copy(deep=True))
            diagnostics.append(
                Diagnostic(
                    id=stable_id("diagnostic", "RECONCILE_SPEC_ONLY", source_operation.id),
                    severity=Severity.WARNING,
                    code="RECONCILE_SPEC_ONLY",
                    message=(
                        f"OpenAPI operation {source_operation.method} {source_operation.route} "
                        f"({source_operation.name}) was not found in code; search the repository "
                        f"for that route suffix and operation name"
                    ),
                    subject_ids=[source_operation.id],
                )
            )
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
            else:
                retained = parameter.model_copy(deep=True)
                retained.type = _remap_type_reference(retained.type, remap)
                target.parameters.append(retained)
                remap[parameter.id] = retained.id
        target.parameters.sort(key=lambda item: (item.location.value, item.name, item.id))
        source_request_id = remap.get(
            source_operation.request_entity_id, source_operation.request_entity_id
        )
        if target.request_entity_id is None and source_request_id:
            target.request_entity_id = source_request_id
        elif (
            target.request_entity_id
            and source_request_id
            and target.request_entity_id != source_request_id
        ):
            diagnostics.append(
                Diagnostic(
                    id=stable_id("diagnostic", "RECONCILE_REQUEST", target.id),
                    severity=Severity.WARNING,
                    code="RECONCILE_REQUEST",
                    message=f"Conflicting request contract evidence for {target.name}",
                    subject_ids=[target.id, target.request_entity_id, source_request_id],
                    evidence_ids=target.evidence_ids,
                )
            )
        target_responses = {item.status_code: item for item in target.responses}
        for response in source_operation.responses:
            match = target_responses.get(response.status_code)
            if match:
                remap[response.id] = match.id
                source_entity_id = remap.get(response.entity_id, response.entity_id)
                inner_id = envelope_inner.get(response.entity_id)
                if inner_id and remap.get(inner_id) == match.entity_id:
                    diagnostics.append(
                        Diagnostic(
                            id=stable_id("diagnostic", "RECONCILE_ENVELOPE", match.id),
                            severity=Severity.INFO,
                            code="RECONCILE_ENVELOPE",
                            message=(
                                f"OpenAPI wraps the {target.name} HTTP {response.status_code} "
                                f"payload in an envelope model; the code returns it directly"
                            ),
                            subject_ids=[target.id, match.entity_id],
                        )
                    )
                elif match.entity_id is None and source_entity_id:
                    match.entity_id = source_entity_id
                elif match.entity_id and source_entity_id and match.entity_id != source_entity_id:
                    diagnostics.append(
                        Diagnostic(
                            id=stable_id("diagnostic", "RECONCILE_RESPONSE", match.id),
                            severity=Severity.WARNING,
                            code="RECONCILE_RESPONSE",
                            message=(
                                f"Conflicting response contract evidence for "
                                f"{target.name} HTTP {response.status_code}"
                            ),
                            subject_ids=[target.id, match.entity_id, source_entity_id],
                            evidence_ids=target.evidence_ids,
                        )
                    )
                if match.type is None:
                    match.type = _remap_type_reference(response.type, remap)
                if not match.description and response.description:
                    match.description = response.description
            else:
                retained = response.model_copy(deep=True)
                retained.entity_id = remap.get(retained.entity_id, retained.entity_id)
                retained.type = _remap_type_reference(retained.type, remap)
                target.responses.append(retained)
                remap[response.id] = retained.id
        target.responses.sort(key=lambda item: item.status_code)

    # Spec-only entities/operations were copied before every merge was known; point their
    # references at the merged code entities.
    for entity in result.entities:
        entity.base_entity_id = remap.get(entity.base_entity_id, entity.base_entity_id)
        for attribute in entity.attributes:
            attribute.type = _remap_type_reference(attribute.type, remap)
    for operation in result.operations:
        operation.request_entity_id = remap.get(
            operation.request_entity_id, operation.request_entity_id
        )
        for parameter in operation.parameters:
            parameter.type = _remap_type_reference(parameter.type, remap)
        for response in operation.responses:
            response.entity_id = remap.get(response.entity_id, response.entity_id)
            response.type = _remap_type_reference(response.type, remap)

    if openapi.operations:
        for code_operation in result.operations:
            if code_operation.id not in claimed and code_operation.id in {
                item.id for item in roslyn.operations
            }:
                diagnostics.append(
                    Diagnostic(
                        id=stable_id("diagnostic", "RECONCILE_CODE_ONLY", code_operation.id),
                        severity=Severity.INFO,
                        code="RECONCILE_CODE_ONLY",
                        message=(
                            f"Code operation {code_operation.method} {code_operation.route} "
                            f"is not described by the OpenAPI document"
                        ),
                        subject_ids=[code_operation.id],
                    )
                )

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
