import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from canonical_model_generator.discovery_agent.model import (
    DiscoveryModel,
    Lineage,
    RelationshipKind,
    stable_id,
)
from canonical_model_generator.discovery_agent.view_model_scope import (
    scope_to_endpoint_view_models,
)

FIXTURES = Path(__file__).parent / "fixtures"


def test_representative_fixture_validates() -> None:
    model = DiscoveryModel.model_validate_json(
        (FIXTURES / "discovery-model.valid.json").read_text(encoding="utf-8")
    )
    assert model.summary.operation_count == 1


def test_invalid_reference_has_useful_error() -> None:
    with pytest.raises(ValidationError, match="invalid operation entity reference"):
        DiscoveryModel.model_validate_json(
            (FIXTURES / "discovery-model.invalid.json").read_text(encoding="utf-8")
        )


def test_stable_ids_are_deterministic_and_path_normalized() -> None:
    assert stable_id("entity", "src\\Quote.cs", "Quote") == stable_id(
        "entity", "src/Quote.cs", "Quote"
    )


def test_schema_is_exportable() -> None:
    schema = DiscoveryModel.model_json_schema(by_alias=True)
    assert schema["properties"]["contractVersion"]["const"] == "1.0"
    assert json.dumps(schema, sort_keys=True)


def test_phase_one_keeps_endpoint_request_response_and_view_models() -> None:
    model = DiscoveryModel.model_validate_json(
        (FIXTURES / "discovery-model.valid.json").read_text(encoding="utf-8")
    )
    request, response = model.entities
    request.name = request.original_name = "CreateProfileRequest"
    response.name = response.original_name = "ProfileViewModel"
    model.lineage.extend(
        [
            Lineage(
                id="lineage-create-profile-request",
                source_id="source-code",
                subject_id=request.id,
                path="Contracts/CreateProfileRequest.cs",
                start_line=1,
                end_line=10,
            ),
            Lineage(
                id="lineage-response-view-model",
                source_id="source-code",
                subject_id=response.id,
                path="ViewModels/ProfileViewModel.cs",
                start_line=1,
                end_line=10,
            ),
        ]
    )

    scoped = scope_to_endpoint_view_models(model)

    assert [item.name for item in scoped.entities] == [
        "CreateProfileRequest",
        "ProfileViewModel",
    ]
    assert scoped.operations[0].request_entity_id == request.id
    assert scoped.operations[0].responses[0].entity_id == response.id
    assert [item.kind for item in scoped.relationships] == [
        RelationshipKind.ACCEPTS,
        RelationshipKind.RETURNS,
    ]


def test_phase_one_excludes_generated_view_models() -> None:
    model = DiscoveryModel.model_validate_json(
        (FIXTURES / "discovery-model.valid.json").read_text(encoding="utf-8")
    )
    response = model.entities[1]
    response.name = response.original_name = "GeneratedViewModel"
    model.lineage.append(
        Lineage(
            id="lineage-generated-view-model",
            source_id="source-code",
            subject_id=response.id,
            path="obj/GeneratedViewModel.g.cs",
            start_line=1,
            end_line=10,
        )
    )

    scoped = scope_to_endpoint_view_models(model)

    assert scoped.entities == []
    assert scoped.relationships == []


def test_phase_one_excludes_dtos_and_base_contract_types() -> None:
    model = DiscoveryModel.model_validate_json(
        (FIXTURES / "discovery-model.valid.json").read_text(encoding="utf-8")
    )
    request, response = model.entities
    request.name = request.original_name = "CustomerDto"
    response.name = response.original_name = "BaseResponse"
    model.lineage.extend(
        [
            Lineage(
                id="lineage-request-dto",
                source_id="source-code",
                subject_id=request.id,
                path="Dtos/CustomerDto.cs",
                start_line=1,
                end_line=10,
            ),
            Lineage(
                id="lineage-base-response",
                source_id="source-code",
                subject_id=response.id,
                path="Messaging/BaseResponse.cs",
                start_line=1,
                end_line=10,
            ),
        ]
    )

    scoped = scope_to_endpoint_view_models(model)

    assert scoped.entities == []
    assert scoped.operations[0].request_entity_id is None
    assert scoped.operations[0].responses[0].entity_id is None
    assert scoped.relationships == []
