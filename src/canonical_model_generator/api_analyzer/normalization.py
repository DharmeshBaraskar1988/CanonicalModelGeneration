"""Bounded single-API entity and attribute normalization proposals."""

from __future__ import annotations

import json
from typing import Any, Protocol

from canonical_model_generator.api_analyzer.contracts import NormalizedEntity
from canonical_model_generator.discovery_agent.model import DiscoveryModel


class EntityNormalizationProvider(Protocol):
    def normalize_entity(self, context: dict[str, Any]) -> NormalizedEntity: ...


def normalize_regional_entity(
    discovery_artifact: bytes,
    entity_id: str,
    semantic_metadata: bytes | None,
    provider: EntityNormalizationProvider,
    regional_inventory: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Propose names/descriptions without mutating the Discovery artifact."""
    discovery = DiscoveryModel.model_validate_json(discovery_artifact)
    entity = next((item for item in discovery.entities if item.id == entity_id), None)
    if entity is None:
        raise ValueError(f"Unknown entity ID: {entity_id}")
    semantics = _entity_semantics(semantic_metadata, entity_id)
    context = {
        "region": discovery.region,
        "application": discovery.system,
        "entity": entity.model_dump(mode="json", by_alias=True),
        "apiAnalyzerSemantics": semantics,
        "regionalInventory": regional_inventory,
    }
    result = provider.normalize_entity(context)
    if result.entity_id != entity.id:
        raise ValueError("Normalization must preserve the entity ID")
    expected = {attribute.id: attribute.name for attribute in entity.attributes}
    actual_ids = [attribute.attribute_id for attribute in result.attributes]
    if set(actual_ids) != set(expected) or len(actual_ids) != len(expected):
        raise ValueError("Normalization must preserve every attribute ID exactly once")

    # IDs are the structural identity. Some models restyle source names even when asked to
    # preserve them (for example camelCase -> PascalCase), so restore authoritative names from
    # Discovery rather than rejecting an otherwise structurally valid review proposal.
    preserved = result.model_copy(
        update={
            "original_name": entity.name,
            "attributes": [
                attribute.model_copy(update={"original_name": expected[attribute.attribute_id]})
                for attribute in result.attributes
            ],
        }
    )
    return preserved.model_dump(mode="json", by_alias=True)


def _entity_semantics(content: bytes | None, entity_id: str) -> dict[str, Any] | None:
    if not content:
        return None
    try:
        metadata = json.loads(content)
    except (json.JSONDecodeError, TypeError, UnicodeDecodeError):
        return None
    return next(
        (
            item
            for item in metadata.get("entities", [])
            if isinstance(item, dict) and item.get("entityId") == entity_id
        ),
        None,
    )
