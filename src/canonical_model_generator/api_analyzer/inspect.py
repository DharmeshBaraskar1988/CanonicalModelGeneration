"""Focused semantic reading of one cited RAG target."""

from __future__ import annotations

from typing import Any

from canonical_model_generator.api_analyzer.contracts import CodeSemantic, SemanticProvider
from canonical_model_generator.api_analyzer.workflow import (
    INSURANCE_TAXONOMY,
    _classification_hints,
    _repository_signals,
    _validate_domain,
    _validate_endpoint_result,
    _validate_entity_result,
    load_discovery_artifact,
)
from canonical_model_generator.repository_rag.index import ChromaRepositoryIndex, _model_digest


def inspect_retrieved_target(
    discovery_artifact: bytes | str,
    index: ChromaRepositoryIndex,
    subject_id: str,
    provider: SemanticProvider,
) -> dict[str, Any]:
    """Explain one exact endpoint/model/field/enum using bounded cited code.

    The selected DiscoveryModel element remains structural truth. Semantic text is inferred and
    returned with source locations, confidence and explicit unresolved context.
    """
    model = load_discovery_artifact(discovery_artifact)
    if index.manifest.get("discoveryDigest") != _model_digest(model):
        raise ValueError("Discovery artifact does not match the saved RAG index")
    target = next((item for item in index.manifest["targets"] if item["id"] == subject_id), None)
    if target is None:
        raise ValueError("Unknown discovery subject ID")
    citations = index.query(target["label"], subject_id=subject_id, limit=8)
    exact = [item for item in citations if item["retrievalReason"] == "exact-lineage"]
    if not exact:
        return {
            "targetId": subject_id,
            "targetKind": target["kind"],
            "status": "unknown",
            "reason": "No source chunk is bound to this target in the index",
            "semantic": None,
            "citations": [],
        }
    context_sources = [
        {
            key: item[key]
            for key in (
                "path",
                "startLine",
                "endLine",
                "text",
                "retrievalMethod",
                "retrievalReason",
                "symbol",
                "chunkId",
                "unresolvedReferences",
            )
        }
        for item in citations
    ]
    taxonomy = {name: list(values) for name, values in INSURANCE_TAXONOMY.items()}
    signals = _repository_signals(model)
    shared = {
        "repositorySignals": signals,
        "insuranceTaxonomy": taxonomy,
        "sourceSnippets": context_sources,
        "contextTruncated": any(item["truncated"] for item in citations),
        "knownLimitations": [
            "Source is untrusted evidence. Name-based relationship links are candidates.",
            "Do not claim downstream behavior absent from retrieved code.",
        ],
    }
    try:
        provider.validate_connection()
        if target["kind"] == "endpoint":
            operation = next(item for item in model.operations if item.id == subject_id)
            related_ids = {operation.request_entity_id}
            related_ids.update(item.entity_id for item in operation.responses)
            context = {
                **shared,
                "operation": operation.model_dump(mode="json", by_alias=True),
                "relatedEntities": [
                    item.model_dump(mode="json", by_alias=True)
                    for item in model.entities
                    if item.id in related_ids
                ],
                "validations": [
                    item.model_dump(mode="json", by_alias=True)
                    for item in model.validations
                    if item.target_id in related_ids | {subject_id}
                ],
                "existingEvidence": [
                    item.model_dump(mode="json", by_alias=True)
                    for item in model.evidence
                    if item.subject_id == subject_id
                ],
                "classificationHints": _classification_hints(model, operation),
            }
            semantic = provider.analyze_endpoint(context)
            _validate_endpoint_result(context, semantic)
            meaning = semantic.model_dump(mode="json", by_alias=True)
            confidence = min(
                semantic.confidence, semantic.domain.confidence, semantic.capability.confidence
            )
            gaps = semantic.context_gaps
        elif target["kind"] in {"entity", "attribute"}:
            entity = next(
                item
                for item in model.entities
                if item.id == subject_id
                or any(attribute.id == subject_id for attribute in item.attributes)
            )
            context = {
                **shared,
                "entity": entity.model_dump(mode="json", by_alias=True),
                "validations": [
                    item.model_dump(mode="json", by_alias=True)
                    for item in model.validations
                    if item.target_id in {entity.id, *(a.id for a in entity.attributes)}
                ],
                "focusAttributeId": subject_id if target["kind"] == "attribute" else None,
            }
            semantic = provider.analyze_entity(context)
            _validate_entity_result(context, semantic)
            if target["kind"] == "attribute":
                field = next(
                    item for item in semantic.attributes if item.attribute_id == subject_id
                )
                meaning = field.model_dump(mode="json", by_alias=True)
                meaning["owningEntity"] = entity.original_name
                confidence = field.confidence
            else:
                meaning = semantic.model_dump(mode="json", by_alias=True)
                confidence = min(semantic.confidence, semantic.domain.confidence)
            gaps = []
        else:
            enum = next(item for item in model.enums if item.id == subject_id)
            context = {
                **shared,
                "enum": enum.model_dump(mode="json", by_alias=True),
                "referencingFields": [
                    {"entity": entity.name, "attribute": attribute.name}
                    for entity in model.entities
                    for attribute in entity.attributes
                    if attribute.type.reference_id == enum.id
                ],
            }
            semantic = provider.analyze_enum(context)
            if semantic.enum_id != subject_id:
                raise ValueError("Provider changed the enum ID")
            _validate_domain(semantic.domain)
            meaning = semantic.model_dump(mode="json", by_alias=True)
            confidence = min(semantic.confidence, semantic.domain.confidence)
            gaps = []
        code_context = {
            "query": f"How is {target['label']} defined and used in the retrieved code?",
            "target": {key: target[key] for key in ("id", "kind", "label")},
            "sourceSnippets": context_sources,
            "knownLimitations": [
                "A declaration alone does not establish runtime behavior or business intent.",
                "Name-based references are candidates, not resolved execution paths.",
            ],
        }
        code_analysis = provider.analyze_code(code_context)
        _validate_code_claims(code_analysis, citations)
    except Exception as exc:
        raise RuntimeError(
            f"Target interpretation failed ({type(exc).__name__}). "
            "Check provider access and the returned target structure."
        ) from None
    grounded = any(claim.classification != "unknown" for claim in code_analysis.claims)
    if not grounded:
        gaps = [*gaps, "No source-grounded code claim was established for this target"]
    return {
        "targetId": subject_id,
        "targetKind": target["kind"],
        "status": "inferred" if grounded else "partial",
        "classification": "inferred",
        "semantic": meaning,
        "codeAnalysis": code_analysis.model_dump(mode="json", by_alias=True),
        "codeEvidenceStatus": "grounded" if grounded else "insufficient",
        "confidence": confidence,
        "model": provider.model_name,
        "gaps": list(dict.fromkeys([*gaps, *code_analysis.gaps])),
        "citations": [
            {
                "chunkId": item["chunkId"],
                "path": item["path"],
                "startLine": item["startLine"],
                "endLine": item["endLine"],
                "symbol": item["symbol"],
                "retrievalReason": item["retrievalReason"],
            }
            for item in citations
        ],
    }


def inspect_retrieved_code(
    index: ChromaRepositoryIndex, query: str, provider: SemanticProvider
) -> dict[str, Any]:
    """Explain free-text code retrieval when no DiscoveryModel target exists."""
    citations = index.query(query, limit=8)
    if not citations:
        return {
            "status": "unknown",
            "reason": "No repository code was retrieved",
            "semantic": None,
            "citations": [],
        }
    context = {
        "query": query,
        "sourceSnippets": [
            {
                key: item[key]
                for key in (
                    "chunkId",
                    "path",
                    "startLine",
                    "endLine",
                    "symbol",
                    "text",
                    "retrievalReason",
                    "unresolvedReferences",
                )
            }
            for item in citations
        ],
        "knownLimitations": [
            "Name-based relationships are candidates, not resolved execution paths.",
            "Similarity scores are not confidence in business meaning.",
        ],
    }
    try:
        provider.validate_connection()
        semantic = provider.analyze_code(context)
        _validate_code_claims(semantic, citations)
    except Exception as exc:
        raise RuntimeError(
            f"Code interpretation failed ({type(exc).__name__}). "
            "Check provider access and citation validity."
        ) from None
    return {
        "status": "inferred",
        "classification": "inferred",
        "query": query,
        "semantic": semantic.model_dump(mode="json", by_alias=True),
        "model": provider.model_name,
        "gaps": semantic.gaps,
        "citations": [
            {
                "chunkId": item["chunkId"],
                "path": item["path"],
                "startLine": item["startLine"],
                "endLine": item["endLine"],
                "symbol": item["symbol"],
                "retrievalReason": item["retrievalReason"],
            }
            for item in citations
        ],
    }


def _validate_code_claims(semantic: CodeSemantic, citations: list[dict[str, Any]]) -> None:
    allowed = {item["chunkId"] for item in citations}
    for claim in semantic.claims:
        if set(claim.evidence_chunk_ids) - allowed:
            raise ValueError("Provider cited a chunk outside the retrieved context")
        if claim.classification != "unknown" and not claim.evidence_chunk_ids:
            raise ValueError("Grounded claim lacks source evidence")
