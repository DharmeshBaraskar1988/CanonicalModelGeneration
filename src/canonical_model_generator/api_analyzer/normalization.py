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
    }
    result = provider.normalize_entity(context)
    if result.entity_id != entity.id or result.original_name != entity.name:
        raise ValueError("Normalization must preserve the entity ID and original name")
    expected = {attribute.id: attribute.name for attribute in entity.attributes}
    actual = {attribute.attribute_id: attribute.original_name for attribute in result.attributes}
    if actual != expected or len(result.attributes) != len(expected):
        raise ValueError("Normalization must preserve every attribute ID and original name")
    return result.model_dump(mode="json", by_alias=True)


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
