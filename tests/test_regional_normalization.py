from __future__ import annotations

from pathlib import Path

import pytest

from canonical_model_generator.api_analyzer.contracts import (
    NormalizedAttribute,
    NormalizedEntity,
)
from canonical_model_generator.api_analyzer.normalization import normalize_regional_entity
from canonical_model_generator.discovery_agent.model import DiscoveryModel


class FakeNormalizationProvider:
    def __init__(self, result: NormalizedEntity) -> None:
        self.result = result
        self.context = None

    def normalize_entity(self, context):
        self.context = context
        return self.result


def _model_and_result() -> tuple[DiscoveryModel, NormalizedEntity]:
    model = DiscoveryModel.model_validate_json(
        Path("tests/fixtures/discovery-model.valid.json").read_bytes()
    )
    entity = model.entities[0]
    result = NormalizedEntity(
        entity_id=entity.id,
        original_name=entity.name,
        normalized_name="NormalizedQuoteRequest",
        normalized_description="Normalized regional quote request.",
        attributes=[
            NormalizedAttribute(
                attribute_id=attribute.id,
                original_name=attribute.name,
                normalized_name=f"normalized{attribute.name[:1].upper()}{attribute.name[1:]}",
                normalized_description=f"Normalized description for {attribute.name}.",
                confidence=0.9,
            )
            for attribute in entity.attributes
        ],
        confidence=0.91,
    )
    return model, result


def test_normalize_regional_entity_preserves_structure_and_returns_proposal() -> None:
    model, result = _model_and_result()
    provider = FakeNormalizationProvider(result)

    proposal = normalize_regional_entity(
        model.model_dump_json(by_alias=True).encode(),
        model.entities[0].id,
        None,
        provider,
    )

    assert proposal["normalizedName"] == "NormalizedQuoteRequest"
    assert len(proposal["attributes"]) == len(model.entities[0].attributes)
    assert provider.context["region"] == model.region
    assert provider.context["entity"]["id"] == model.entities[0].id


def test_normalize_regional_entity_rejects_changed_attribute_identity() -> None:
    model, result = _model_and_result()
    changed = result.model_copy(
        update={
            "attributes": [
                result.attributes[0].model_copy(update={"attribute_id": "changed"}),
                *result.attributes[1:],
            ]
        }
    )

    with pytest.raises(ValueError, match="preserve every attribute"):
        normalize_regional_entity(
            model.model_dump_json(by_alias=True).encode(),
            model.entities[0].id,
            None,
            FakeNormalizationProvider(changed),
        )
