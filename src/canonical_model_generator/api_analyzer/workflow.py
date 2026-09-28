"""Evidence-grounded Phase 2 semantic OpenAPI generation."""

from __future__ import annotations

import json
import re
from collections.abc import Callable, Mapping
from hashlib import sha256
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any, TypedDict

import yaml
from langgraph.graph import END, START, StateGraph

from canonical_model_generator.api_analyzer.contracts import (
    AttributeSemantic as _AttributeSemantic,
)
from canonical_model_generator.api_analyzer.contracts import (
    CapabilitySemantic as _CapabilitySemantic,
)
from canonical_model_generator.api_analyzer.contracts import (
    DomainSemantic,
    EndpointSemantic,
    EntitySemantic,
    EnumSemantic,
    SemanticProvider,
)
from canonical_model_generator.api_analyzer.contracts import (
    ResponseSemantic as _ResponseSemantic,
)
from canonical_model_generator.api_analyzer.er_diagram import render_er_mermaid, render_er_svg
from canonical_model_generator.api_analyzer.providers.openai import (
    OpenAISemanticProvider as _OpenAISemanticProvider,
)
from canonical_model_generator.api_analyzer.tools.repository_search import ChromaRepositoryIndex
from canonical_model_generator.discovery_agent.model import DiscoveryModel, TypeKind, TypeRef
from canonical_model_generator.discovery_agent.openapi import discover_openapi
from canonical_model_generator.repository_rag.chunking import redact
from canonical_model_generator.repository_rag.embeddings import Embedder

# Compatibility exports for existing callers; new code should import from ``api_analyzer``.
AttributeSemantic = _AttributeSemantic
CapabilitySemantic = _CapabilitySemantic
ResponseSemantic = _ResponseSemantic
OpenAISemanticProvider = _OpenAISemanticProvider

MAX_CONTEXT_CHARACTERS = 24_000
MAX_FOLLOW_UP_CHARACTERS = 12_000
MAX_VECTOR_CONTEXT_CHARACTERS = 12_000
AUTO_ACCEPT_THRESHOLD = 0.90
REVIEW_THRESHOLD = 0.70

INSURANCE_TAXONOMY: dict[str, tuple[str, ...]] = {
    "Policy": (
        "Quote Management",
        "Policy Issuance",
        "Policy Inquiry",
        "Policy Change",
        "Renewal",
        "Cancellation",
    ),
    "Claims": (
        "FNOL",
        "Claim Registration",
        "Claim Assessment",
        "Settlement",
        "Claim Inquiry",
    ),
    "Billing": ("Invoice Management", "Billing Inquiry", "Collections"),
    "Party / Customer": ("Customer Management", "Party Inquiry", "Contact Management"),
    "Product": ("Product Definition", "Product Inquiry", "Coverage Management"),
    "Underwriting": ("Risk Assessment", "Eligibility", "Referral Management"),
    "Rating": ("Rate Calculation", "Premium Calculation", "Rate Management"),
    "Distribution": ("Agent Management", "Broker Management", "Channel Management"),
    "Documents": ("Document Generation", "Document Retrieval", "Correspondence Management"),
    "Payments": ("Payment Collection", "Refunds", "Payment Inquiry"),
    "Reference Data": ("Reference Data Inquiry", "Code List Management"),
    "UNCLASSIFIED": ("UNCLASSIFIED",),
}

DOMAIN_DESCRIPTIONS = {
    "Policy": "Insurance policy lifecycle, quotation, issuance, servicing, and renewal APIs.",
    "Claims": "Insurance loss reporting, claim handling, assessment, and settlement APIs.",
    "Billing": "Premium billing, invoicing, collections, and account inquiry APIs.",
    "Party / Customer": "Customer, organization, contact, and party information APIs.",
    "Product": "Insurance product, coverage, and product configuration APIs.",
    "Underwriting": "Risk assessment, eligibility, referral, and underwriting decision APIs.",
    "Rating": "Rate selection, premium calculation, and rating configuration APIs.",
    "Distribution": "Agent, broker, producer, and distribution channel APIs.",
    "Documents": "Insurance document generation, storage, retrieval, and correspondence APIs.",
    "Payments": "Payment collection, refund, and payment inquiry APIs.",
    "Reference Data": "Shared code lists and reference-data lookup APIs.",
    "UNCLASSIFIED": "APIs that cannot be assigned safely to the controlled insurance taxonomy.",
}


class Phase2State(TypedDict, total=False):
    has_repository: bool
    persistent_index: bool
    discovery_model: DiscoveryModel
    repository_root: str
    vector_store_path: str
    retrieval_stats: dict[str, Any]
    endpoint_contexts: list[dict[str, Any]]
    entity_contexts: list[dict[str, Any]]
    enum_contexts: list[dict[str, Any]]
    provider_ready: bool
    endpoint_semantics: list[EndpointSemantic]
    entity_semantics: list[EntitySemantic]
    enum_semantics: list[EnumSemantic]
    investigations: list[dict[str, Any]]
    errors: list[str]
    artifacts: dict[str, bytes]


type DiscoveryArtifact = bytes | bytearray | str | Path | Mapping[str, Any]


def load_discovery_artifact(artifact: DiscoveryArtifact) -> DiscoveryModel:
    """Validate the serialized Phase 1 artifact used at the agent boundary."""
    if isinstance(artifact, Path):
        return DiscoveryModel.model_validate_json(artifact.read_bytes())
    if isinstance(artifact, (bytes, bytearray, str)):
        return DiscoveryModel.model_validate_json(artifact)
    if isinstance(artifact, Mapping):
        return DiscoveryModel.model_validate(dict(artifact))
    raise TypeError("API Analyzer input must be a serialized Discovery Agent artifact")


def run_semantic_openapi_agent(
    discovery_artifact: DiscoveryArtifact,
    repository_root: Path | None,
    provider: SemanticProvider,
    progress: Callable[[str], None] | None = None,
    *,
    rag_store_path: Path | None = None,
    embedder: Embedder | None = None,
) -> dict[str, bytes]:
    """Run Phase 2 from a validated serialized Phase 1 artifact."""
    discovery_model = load_discovery_artifact(discovery_artifact)
    if repository_root is None or rag_store_path is None:
        raise ValueError(
            "API Analyzer requires the source repository and its saved RAG index; "
            "RAG is mandatory for every analysis run."
        )
    if not (rag_store_path / "rag-manifest.json").is_file():
        raise ValueError("API Analyzer requires a saved RAG artifact with rag-manifest.json")
    saved_index = ChromaRepositoryIndex(rag_store_path, embedder)
    try:
        saved_index.validate_snapshot(repository_root, discovery_model)
    finally:
        saved_index.close()
    with TemporaryDirectory(prefix="canonical-chroma-"):
        graph = _build_graph(provider, progress, embedder)
        result = graph.invoke(
            {
                "discovery_model": discovery_model,
                "repository_root": str(repository_root.resolve()),
                "vector_store_path": str(rag_store_path),
                "has_repository": True,
                "persistent_index": True,
                "errors": [],
            }
        )
        return result["artifacts"]


def run_api_analyzer_agent(
    discovery_artifact: DiscoveryArtifact,
    repository_root: Path | None,
    provider: SemanticProvider,
    progress: Callable[[str], None] | None = None,
    *,
    rag_store_path: Path | None = None,
    embedder: Embedder | None = None,
) -> dict[str, bytes]:
    """Run the API Analyzer using only the Discovery Agent artifact handoff."""
    return run_semantic_openapi_agent(
        discovery_artifact,
        repository_root,
        provider,
        progress,
        rag_store_path=rag_store_path,
        embedder=embedder,
    )


def _build_graph(
    provider: SemanticProvider,
    progress: Callable[[str], None] | None = None,
    embedder: Embedder | None = None,
) -> Any:
    graph = StateGraph(Phase2State)

    def notify(message: str) -> None:
        if progress is not None:
            progress(message)

    def build_contexts(state: Phase2State) -> dict[str, Any]:
        model = state["discovery_model"]
        root = Path(state["repository_root"])
        result = {
            "endpoint_contexts": [
                _endpoint_context(model, item.id, root) for item in model.operations
            ],
            "entity_contexts": [_entity_context(model, item.id, root) for item in model.entities],
            "enum_contexts": [_enum_context(model, item.id, root) for item in model.enums],
        }
        notify(
            "Built evidence contexts for "
            f"{len(result['endpoint_contexts'])} endpoints, "
            f"{len(result['entity_contexts'])} entities, and "
            f"{len(result['enum_contexts'])} enums."
        )
        return result

    def validate_provider(state: Phase2State) -> dict[str, Any]:
        notify(f"Validating OpenAI credentials and access to {provider.model_name}...")
        try:
            validator = getattr(provider, "validate_connection", None)
            if validator is not None:
                validator()
        except Exception as exc:
            message = _provider_error_message(exc, provider.model_name)
            notify(message)
            return {
                "provider_ready": False,
                "errors": [*state.get("errors", []), message],
            }
        notify("OpenAI connection validated. Starting semantic analysis.")
        return {"provider_ready": True}

    def provider_route(state: Phase2State) -> str:
        return "ingest" if state.get("provider_ready") else "render"

    def ingest_repository(state: Phase2State) -> dict[str, Any]:
        if not state.get("has_repository", True):
            return {"retrieval_stats": {"provider": "none", "status": "specification-only"}}
        notify("Ingesting the redacted repository into the local Chroma vector index...")
        index: ChromaRepositoryIndex | None = None
        try:
            index = ChromaRepositoryIndex(Path(state["vector_store_path"]), embedder)
            stats = dict(index.ingest(Path(state["repository_root"]), state["discovery_model"]))
            endpoint_contexts = [
                _add_vector_context(index, context, _endpoint_vector_query(context))
                for context in state["endpoint_contexts"]
            ]
            entity_contexts = [
                _add_vector_context(index, context, _entity_vector_query(context))
                for context in state["entity_contexts"]
            ]
            enum_contexts = [
                _add_vector_context(index, context, _enum_vector_query(context))
                for context in state["enum_contexts"]
            ]
        except Exception as exc:
            message = f"Chroma repository retrieval failed: {_safe_error_text(exc)}"
            notify(message)
            return {
                "retrieval_stats": {"provider": "chroma", "status": "failed"},
                "errors": [*state.get("errors", []), message],
            }
        finally:
            if index is not None:
                index.close()
        stats["targetsRetrieved"] = sum(
            bool(item.get("vectorRetrievedCount"))
            for item in [*endpoint_contexts, *entity_contexts, *enum_contexts]
        )
        stats["storage"] = (
            "persistent-local" if state.get("persistent_index") else "ephemeral-local"
        )
        notify(
            f"Chroma indexed {stats['chunksIndexed']} chunks from {stats['filesIndexed']} files "
            f"and retrieved context for {stats['targetsRetrieved']} targets."
        )
        return {
            "endpoint_contexts": endpoint_contexts,
            "entity_contexts": entity_contexts,
            "enum_contexts": enum_contexts,
            "retrieval_stats": stats,
        }

    def analyze_endpoints(state: Phase2State) -> dict[str, Any]:
        results: list[EndpointSemantic] = []
        investigations: list[dict[str, Any]] = []
        errors = list(state.get("errors", []))
        total = len(state["endpoint_contexts"])
        for index, context in enumerate(state["endpoint_contexts"], 1):
            name = context["operation"]["name"]
            notify(f"Analyzing endpoint {index}/{total}: {name}")
            try:
                result, investigation = _analyze_endpoint_with_follow_up(
                    provider,
                    context,
                    Path(state["repository_root"]),
                    Path(state["vector_store_path"]),
                    embedder,
                    allow_retrieval=state.get("has_repository", True),
                )
                results.append(result)
                investigations.append(investigation)
                if investigation["retrievedFragmentCount"]:
                    notify(
                        f"Retrieved {investigation['retrievedFragmentCount']} additional source "
                        f"fragment(s) for {name}; confidence is now "
                        f"{investigation['finalConfidence']:.2f}."
                    )
            except Exception as exc:  # provider errors must become visible partial output
                errors.append(f"Endpoint {name}: {_safe_error_text(exc)}")
        return {
            "endpoint_semantics": results,
            "investigations": investigations,
            "errors": errors,
        }

    def analyze_entities(state: Phase2State) -> dict[str, Any]:
        results: list[EntitySemantic] = []
        errors = list(state.get("errors", []))
        total = len(state["entity_contexts"])
        for index, context in enumerate(state["entity_contexts"], 1):
            name = context["entity"]["name"]
            notify(f"Analyzing entity {index}/{total}: {name}")
            try:
                result = provider.analyze_entity(context)
                _validate_entity_result(context, result)
                results.append(result)
            except Exception as exc:  # provider errors must become visible partial output
                errors.append(f"Entity {name}: {_safe_error_text(exc)}")
        return {"entity_semantics": results, "errors": errors}

    def analyze_enums(state: Phase2State) -> dict[str, Any]:
        results: list[EnumSemantic] = []
        errors = list(state.get("errors", []))
        total = len(state["enum_contexts"])
        for index, context in enumerate(state["enum_contexts"], 1):
            name = context["enum"]["name"]
            notify(f"Analyzing enum {index}/{total}: {name}")
            try:
                result = provider.analyze_enum(context)
                if result.enum_id != context["enum"]["id"]:
                    raise ValueError("the result changed the enum ID")
                _validate_domain(result.domain)
                results.append(result)
            except Exception as exc:  # provider errors must become visible partial output
                errors.append(f"Enum {name}: {_safe_error_text(exc)}")
        return {"enum_semantics": results, "errors": errors}

    def render(state: Phase2State) -> dict[str, Any]:
        notify("Rendering and validating the enriched OpenAPI and analysis artifacts.")
        return {
            "artifacts": _render_artifacts(
                state["discovery_model"],
                Path(state["repository_root"]),
                provider.model_name,
                state.get("endpoint_contexts", []),
                state.get("entity_contexts", []),
                state.get("enum_contexts", []),
                state.get("endpoint_semantics", []),
                state.get("entity_semantics", []),
                state.get("enum_semantics", []),
                state.get("investigations", []),
                state.get("retrieval_stats", {}),
                state.get("provider_ready", False),
                state.get("errors", []),
            )
        }

    graph.add_node("build_contexts", build_contexts)
    graph.add_node("validate_provider", validate_provider)
    graph.add_node("ingest_repository", ingest_repository)
    graph.add_node("analyze_endpoints", analyze_endpoints)
    graph.add_node("analyze_entities", analyze_entities)
    graph.add_node("analyze_enums", analyze_enums)
    graph.add_node("render_and_validate", render)
    graph.add_edge(START, "build_contexts")
    graph.add_edge("build_contexts", "validate_provider")
    graph.add_conditional_edges(
        "validate_provider",
        provider_route,
        {"ingest": "ingest_repository", "render": "render_and_validate"},
    )
    graph.add_edge("ingest_repository", "analyze_endpoints")
    graph.add_edge("analyze_endpoints", "analyze_entities")
    graph.add_edge("analyze_entities", "analyze_enums")
    graph.add_edge("analyze_enums", "render_and_validate")
    graph.add_edge("render_and_validate", END)
    return graph.compile()


def _provider_error_message(exc: Exception, model_name: str) -> str:
    error_name = type(exc).__name__
    if error_name == "AuthenticationError":
        return (
            "OpenAI authentication failed (401 invalid_api_key). Replace OPENAI_API_KEY in .env "
            "with an active API key, restart Streamlit, and run the agent again."
        )
    if error_name == "PermissionDeniedError":
        return "OpenAI access was denied. Check the API project's permissions and model access."
    if error_name == "NotFoundError":
        return f"OpenAI model {model_name!r} is unavailable to this API project."
    if error_name == "BadRequestError":
        return f"OpenAI rejected the provider configuration: {_safe_error_text(exc)}"
    return f"OpenAI provider validation failed ({error_name}): {_safe_error_text(exc)}"


def _safe_error_text(exc: Exception) -> str:
    value = str(exc)
    value = re.sub(r"sk-[A-Za-z0-9_-]+", "[REDACTED]", value)
    return value[:1000]


def _validate_entity_result(context: dict[str, Any], result: EntitySemantic) -> None:
    if result.entity_id != context["entity"]["id"]:
        raise ValueError("the result changed the entity ID")
    expected = {item["id"] for item in context["entity"]["attributes"]}
    actual = {item.attribute_id for item in result.attributes}
    if actual != expected or len(actual) != len(result.attributes):
        raise ValueError("the result must contain every supplied attribute exactly once")
    _validate_domain(result.domain)


def _validate_endpoint_result(context: dict[str, Any], result: EndpointSemantic) -> None:
    if result.operation_id != context["operation"]["id"]:
        raise ValueError("the result changed the operation ID")
    _validate_domain(result.domain)
    if result.capability.name == "UNCLASSIFIED" and not result.capability.suggested_name:
        raise ValueError("UNCLASSIFIED capability requires a suggested capability")
    result.tags = [result.domain.name]
    expected_responses = {item["statusCode"] for item in context["operation"]["responses"]}
    actual_responses = {item.status_code for item in result.responses}
    if actual_responses != expected_responses or len(actual_responses) != len(result.responses):
        raise ValueError("the result must describe every discovered response exactly once")


def _validate_domain(domain: DomainSemantic) -> None:
    if domain.name == "UNCLASSIFIED" and not domain.suggested_name:
        raise ValueError("UNCLASSIFIED requires a suggested domain")


def _endpoint_vector_query(context: dict[str, Any]) -> str:
    operation = context["operation"]
    entity_names = [item["name"] for item in context.get("relatedEntities", [])]
    hints = context.get("classificationHints", {})
    return " ".join(
        [
            "endpoint domain capability business purpose implementation authorization",
            operation["name"],
            operation["method"],
            operation["route"],
            hints.get("controllerDomainCandidate", ""),
            hints.get("actionCapabilityCandidate", ""),
            *entity_names,
        ]
    )


def _entity_vector_query(context: dict[str, Any]) -> str:
    entity = context["entity"]
    return " ".join(
        [
            "model DTO business meaning validation mapping request response",
            entity["name"],
            *(item["name"] for item in entity.get("attributes", [])),
        ]
    )


def _enum_vector_query(context: dict[str, Any]) -> str:
    enum = context["enum"]
    return " ".join(
        [
            "enum business meaning state status values",
            enum["name"],
            *(item["name"] for item in enum.get("values", [])),
            *(
                f"{item['entity']} {item['attribute']}"
                for item in context.get("referencingFields", [])
            ),
        ]
    )


def _add_vector_context(
    index: ChromaRepositoryIndex,
    context: dict[str, Any],
    query: str,
) -> dict[str, Any]:
    existing = {
        (item["path"], item["startLine"], item["endLine"])
        for item in context.get("sourceSnippets", [])
    }
    retrieved: list[dict[str, Any]] = []
    used = 0
    target = context.get("operation") or context.get("entity") or context.get("enum") or {}
    for item in index.query(query[:2000], limit=4, subject_id=target.get("id")):
        key = (item["path"], item["startLine"], item["endLine"])
        if key in existing:
            continue
        remaining = MAX_VECTOR_CONTEXT_CHARACTERS - used
        if remaining <= 0:
            break
        if len(item["text"]) > remaining:
            item = {**item, "text": item["text"][:remaining] + "\n[retrieval truncated]"}
        retrieved.append(item)
        used += len(item["text"])
    return {
        **context,
        "sourceSnippets": [*context.get("sourceSnippets", []), *retrieved],
        "vectorQuery": query,
        "vectorRetrievedCount": len(retrieved),
    }


def _analyze_endpoint_with_follow_up(
    provider: SemanticProvider,
    context: dict[str, Any],
    root: Path,
    vector_store_path: Path,
    embedder: Embedder | None = None,
    *,
    allow_retrieval: bool = True,
) -> tuple[EndpointSemantic, dict[str, Any]]:
    result = provider.analyze_endpoint(context)
    _validate_endpoint_result(context, result)
    initial_confidence = _endpoint_minimum_confidence(result)
    requested = _safe_symbol_names(result.requested_symbols)
    if initial_confidence < REVIEW_THRESHOLD and not requested:
        requested = _candidate_symbols_from_context(context)

    retrieved: list[dict[str, Any]] = []
    if requested and initial_confidence < AUTO_ACCEPT_THRESHOLD and allow_retrieval:
        existing_paths = {item["path"] for item in context.get("sourceSnippets", [])}
        existing_spans = {
            (item["path"], item["startLine"], item["endLine"])
            for item in context.get("sourceSnippets", [])
        }
        vector_index = ChromaRepositoryIndex(vector_store_path, embedder)
        try:
            retrieved = vector_index.query(
                " ".join(
                    [
                        "implementation call path service handler repository authorization",
                        context["operation"]["name"],
                        *requested,
                    ]
                ),
                limit=20,
            )
        finally:
            vector_index.close()
        retrieved = [
            item
            for item in retrieved
            if (item["path"], item["startLine"], item["endLine"]) not in existing_spans
        ]
        if not retrieved:
            retrieved = _retrieve_symbol_context(root, requested, existing_paths)
        if retrieved:
            context["sourceSnippets"] = [*context.get("sourceSnippets", []), *retrieved]
            context["investigationRound"] = 2
            context["retrievedSymbols"] = requested
            result = provider.analyze_endpoint(context)
            _validate_endpoint_result(context, result)

    final_confidence = _endpoint_minimum_confidence(result)
    return result, {
        "targetId": result.operation_id,
        "initialConfidence": initial_confidence,
        "finalConfidence": final_confidence,
        "requestedSymbols": requested,
        "retrievedFragmentCount": len(retrieved),
        "status": (
            "auto_accept_candidate"
            if final_confidence >= AUTO_ACCEPT_THRESHOLD
            else "review"
            if final_confidence >= REVIEW_THRESHOLD
            else "needs_more_context"
        ),
    }


def _endpoint_minimum_confidence(item: EndpointSemantic) -> float:
    return min(item.confidence, item.domain.confidence, item.capability.confidence)


def _safe_symbol_names(values: list[str]) -> list[str]:
    result: list[str] = []
    for value in values:
        value = value.strip()
        if re.fullmatch(r"[A-Za-z_][A-Za-z0-9_.]{0,159}", value) and value not in result:
            result.append(value)
    return result[:8]


def _candidate_symbols_from_context(context: dict[str, Any]) -> list[str]:
    candidates: list[str] = []
    pattern = re.compile(r"\b([A-Z][A-Za-z0-9_]*(?:Service|Repository|Handler|Client|Mediator))\b")
    for snippet in context.get("sourceSnippets", []):
        for candidate in pattern.findall(snippet.get("text", "")):
            if candidate not in candidates:
                candidates.append(candidate)
    return candidates[:8]


def _retrieve_symbol_context(
    root: Path,
    symbols: list[str],
    existing_paths: set[str],
) -> list[dict[str, Any]]:
    root = root.resolve()
    requested = {item.rsplit(".", 1)[-1] for item in symbols}
    snippets: list[dict[str, Any]] = []
    used = 0
    for path in sorted(root.rglob("*.cs")):
        relative = path.relative_to(root).as_posix()
        if relative in existing_paths or any(part in {"bin", "obj", ".git"} for part in path.parts):
            continue
        if path.stat().st_size > 1_000_000:
            continue
        lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
        matches = [
            number
            for number, line in enumerate(lines, 1)
            if any(re.search(rf"\b{re.escape(symbol)}\b", line) for symbol in requested)
        ]
        if not matches:
            continue
        first = max(1, matches[0] - 8)
        last = min(len(lines), matches[0] + 36)
        text = "\n".join(f"{number:>5}: {lines[number - 1]}" for number in range(first, last + 1))
        text = _redact_likely_secrets(text)
        remaining = MAX_FOLLOW_UP_CHARACTERS - used
        if remaining <= 0:
            break
        if len(text) > remaining:
            text = text[:remaining] + "\n[follow-up context truncated]"
        snippets.append(
            {
                "path": relative,
                "startLine": first,
                "endLine": last,
                "text": text,
                "retrievalMethod": "bounded-symbol-match",
            }
        )
        used += len(text)
    return snippets


def _endpoint_context(model: DiscoveryModel, operation_id: str, root: Path) -> dict[str, Any]:
    operation = next(item for item in model.operations if item.id == operation_id)
    entity_ids = {operation.request_entity_id} if operation.request_entity_id else set()
    entity_ids.update(item.entity_id for item in operation.responses if item.entity_id)
    related_entities = [item for item in model.entities if item.id in entity_ids]
    subject_ids = {operation.id}
    subject_ids.update(item.id for item in operation.parameters)
    for entity in related_entities:
        subject_ids.add(entity.id)
        subject_ids.update(item.id for item in entity.attributes)
    snippets, truncated = _source_snippets(model, subject_ids, root, operation_window=True)
    evidence = [
        item.model_dump(mode="json", by_alias=True)
        for item in model.evidence
        if item.subject_id == operation.id
    ]
    return {
        "operation": operation.model_dump(mode="json", by_alias=True),
        "relatedEntities": [
            item.model_dump(mode="json", by_alias=True) for item in related_entities
        ],
        "validations": [
            item.model_dump(mode="json", by_alias=True)
            for item in model.validations
            if item.target_id in subject_ids
        ],
        "existingEvidence": evidence,
        "repositorySignals": _repository_signals(model),
        "classificationHints": _classification_hints(model, operation),
        "insuranceTaxonomy": {key: list(value) for key, value in INSURANCE_TAXONOMY.items()},
        "sourceSnippets": snippets,
        "contextTruncated": truncated,
        "knownLimitations": [
            "Phase 1 does not yet provide a semantic service call graph.",
            "Descriptions must not claim downstream behavior not visible in these snippets.",
        ],
    }


def _classification_hints(model: DiscoveryModel, operation: Any) -> dict[str, str]:
    controller = ""
    for lineage in model.lineage:
        if lineage.subject_id != operation.id:
            continue
        stem = Path(lineage.path).stem
        if stem.lower().endswith("controller"):
            controller = stem[: -len("Controller")]
            break
    if not controller:
        parts = [item for item in operation.route.strip("/").split("/") if item]
        controller = parts[0] if parts else ""
    domain = _humanize_identifier(controller)
    if domain.lower() in {"manage", "management"}:
        domain = "Management"
    action = _humanize_identifier(re.sub(r"Async$", "", operation.name))
    return {
        "controller": f"{controller}Controller" if controller else "",
        "controllerDomainCandidate": domain,
        "actionCapabilityCandidate": action,
        "policy": (
            "Prefer an insurance taxonomy match when supported; otherwise use the controller "
            "domain candidate and action capability candidate instead of UNCLASSIFIED."
        ),
    }


def _humanize_identifier(value: str) -> str:
    value = value.replace("_", " ").replace("-", " ")
    value = re.sub(r"(?<=[a-z0-9])(?=[A-Z])", " ", value)
    return " ".join(value.split()).title()


def _entity_context(model: DiscoveryModel, entity_id: str, root: Path) -> dict[str, Any]:
    entity = next(item for item in model.entities if item.id == entity_id)
    subject_ids = {entity.id, *(item.id for item in entity.attributes)}
    snippets, truncated = _source_snippets(model, subject_ids, root)
    return {
        "entity": entity.model_dump(mode="json", by_alias=True),
        "validations": [
            item.model_dump(mode="json", by_alias=True)
            for item in model.validations
            if item.target_id in subject_ids
        ],
        "repositorySignals": _repository_signals(model),
        "insuranceTaxonomy": {key: list(value) for key, value in INSURANCE_TAXONOMY.items()},
        "sourceSnippets": snippets,
        "contextTruncated": truncated,
        "knownLimitations": [
            "Descriptions must distinguish observed structure from inferred business meaning."
        ],
    }


def _enum_context(model: DiscoveryModel, enum_id: str, root: Path) -> dict[str, Any]:
    enum = next(item for item in model.enums if item.id == enum_id)
    referencing_fields = [
        {
            "entity": entity.name,
            "attribute": attribute.name,
        }
        for entity in model.entities
        for attribute in entity.attributes
        if attribute.type.reference_id == enum.id
    ]
    snippets, truncated = _source_snippets(model, {enum.id}, root)
    return {
        "enum": enum.model_dump(mode="json", by_alias=True),
        "referencingFields": referencing_fields,
        "repositorySignals": _repository_signals(model),
        "insuranceTaxonomy": {key: list(value) for key, value in INSURANCE_TAXONOMY.items()},
        "sourceSnippets": snippets,
        "contextTruncated": truncated,
    }


def _repository_signals(model: DiscoveryModel) -> dict[str, Any]:
    return {
        "region": model.region,
        "system": model.system,
        "endpoints": [
            {"name": item.name, "method": item.method, "route": item.route}
            for item in model.operations
        ],
        "entities": [item.name for item in model.entities],
        "enums": [item.name for item in model.enums],
    }


def _source_snippets(
    model: DiscoveryModel,
    subject_ids: set[str],
    root: Path,
    *,
    operation_window: bool = False,
) -> tuple[list[dict[str, Any]], bool]:
    locations: dict[str, list[tuple[int, int]]] = {}
    for item in model.lineage:
        if item.subject_id not in subject_ids or item.start_line is None:
            continue
        locations.setdefault(item.path, []).append(
            (item.start_line, item.end_line or item.start_line)
        )

    snippets: list[dict[str, Any]] = []
    used = 0
    truncated = False
    root = root.resolve()
    for relative_path in sorted(locations):
        candidate = (root / relative_path).resolve()
        try:
            candidate.relative_to(root)
        except ValueError:
            continue
        if candidate.suffix.lower() != ".cs" or not candidate.is_file():
            continue
        lines = candidate.read_text(encoding="utf-8", errors="replace").splitlines()
        ranges = locations[relative_path]
        first = max(1, min(item[0] for item in ranges) - 8)
        extra = 80 if operation_window else 16
        last = min(len(lines), max(item[1] for item in ranges) + extra)
        text = "\n".join(f"{number:>5}: {lines[number - 1]}" for number in range(first, last + 1))
        text = _redact_likely_secrets(text)
        remaining = MAX_CONTEXT_CHARACTERS - used
        if remaining <= 0:
            truncated = True
            break
        if len(text) > remaining:
            text = text[:remaining] + "\n[context truncated]"
            truncated = True
        snippets.append(
            {
                "path": relative_path.replace("\\", "/"),
                "startLine": first,
                "endLine": last,
                "text": text,
            }
        )
        used += len(text)
    return snippets, truncated


def _redact_likely_secrets(value: str) -> str:
    return redact(value)


def _render_artifacts(
    model: DiscoveryModel,
    repository_root: Path,
    model_name: str,
    endpoint_contexts: list[dict[str, Any]],
    entity_contexts: list[dict[str, Any]],
    enum_contexts: list[dict[str, Any]],
    endpoints: list[EndpointSemantic],
    entities: list[EntitySemantic],
    enums: list[EnumSemantic],
    investigations: list[dict[str, Any]],
    retrieval_stats: dict[str, Any],
    provider_ready: bool,
    errors: list[str],
) -> dict[str, bytes]:
    document = _generate_openapi(model, endpoints, entities, enums, model_name)
    validation_errors = _validate_openapi_document(document, model)
    evidence_errors = _validate_semantic_evidence(model, endpoints, entities, enums)
    errors = [*errors, *validation_errors, *evidence_errors]
    semantic_metadata = {
        "schemaVersion": "1.0",
        "phase": "semantic-openapi-generation",
        "region": model.region,
        "system": model.system,
        "model": model_name,
        "providerStatus": "ready" if provider_ready else "failed",
        "retrieval": retrieval_stats,
        "endpoints": [item.model_dump(mode="json", by_alias=True) for item in endpoints],
        "entities": [item.model_dump(mode="json", by_alias=True) for item in entities],
        "enums": [item.model_dump(mode="json", by_alias=True) for item in enums],
        "investigations": investigations,
    }
    evidence_map = _build_evidence_map(
        model,
        model_name,
        endpoint_contexts,
        entity_contexts,
        enum_contexts,
        endpoints,
        entities,
        enums,
    )
    enriched_attribute_count = sum(len(item.attributes) for item in entities)
    discovered_attribute_count = sum(len(item.attributes) for item in model.entities)
    confidence_bands = _confidence_bands(endpoints, entities, enums)
    missing_endpoint_ids = sorted(
        {item.id for item in model.operations} - {item.operation_id for item in endpoints}
    )
    missing_entity_ids = sorted(
        {item.id for item in model.entities} - {item.entity_id for item in entities}
    )
    missing_enum_ids = sorted({item.id for item in model.enums} - {item.enum_id for item in enums})
    incomplete = bool(
        errors
        or missing_endpoint_ids
        or missing_entity_ids
        or missing_enum_ids
        or confidence_bands["needsMoreContext"]
    )
    report = {
        "schemaVersion": "1.0",
        "status": "partial" if incomplete else "complete",
        "model": model_name,
        "providerStatus": "ready" if provider_ready else "failed",
        "retrieval": retrieval_stats,
        "endpointsDiscovered": len(model.operations),
        "endpointsEnriched": len(endpoints),
        "domainsClassified": sum(item.domain.name != "UNCLASSIFIED" for item in endpoints),
        "capabilitiesClassified": sum(item.capability.name != "UNCLASSIFIED" for item in endpoints),
        "entitiesDiscovered": len(model.entities),
        "entitiesEnriched": len(entities),
        "enumsDiscovered": len(model.enums),
        "enumsEnriched": len(enums),
        "attributesDiscovered": discovered_attribute_count,
        "attributesEnriched": enriched_attribute_count,
        "missingEndpointIds": missing_endpoint_ids,
        "missingEntityIds": missing_entity_ids,
        "missingEnumIds": missing_enum_ids,
        "autoAcceptCandidates": confidence_bands["autoAccept"],
        "reviewTargets": confidence_bands["review"],
        "needsMoreContextTargets": confidence_bands["needsMoreContext"],
        "investigations": investigations,
        "truncatedContextCount": sum(
            bool(item.get("contextTruncated"))
            for item in [*endpoint_contexts, *entity_contexts, *enum_contexts]
        ),
        "validationErrors": errors,
        "limitations": [
            "Semantic descriptions are inferred from bounded source evidence and require "
            "human review.",
            "Service call paths, persistence, integrations, and security are not claimed "
            "unless Phase 1 extracted them.",
        ],
    }
    harness_fields = _harness_report_fields(
        model,
        repository_root,
        endpoints,
        entities,
        enums,
        confidence_bands["needsMoreContext"],
        errors,
    )
    if harness_fields["status"] == "partial":
        report["status"] = "partial"
    report.update(harness_fields)
    return {
        "enriched-openapi.yaml": yaml.safe_dump(
            document, sort_keys=False, allow_unicode=True
        ).encode("utf-8"),
        "semantic-metadata.json": _json_bytes(semantic_metadata),
        "evidence-map.json": _json_bytes(evidence_map),
        "enrichment-report.json": _json_bytes(report),
        "entity-relationship-diagram.mmd": render_er_mermaid(model).encode("utf-8"),
        "entity-relationship-diagram.svg": render_er_svg(model).encode("utf-8"),
    }


def _harness_report_fields(
    model: DiscoveryModel,
    repository_root: Path,
    endpoints: list[EndpointSemantic],
    entities: list[EntitySemantic],
    enums: list[EnumSemantic],
    needs_more_context: list[str],
    errors: list[str],
) -> dict[str, Any]:
    repository_root = repository_root.resolve()
    target_ids = {item.operation_id for item in endpoints}
    target_ids.update(item.entity_id for item in entities)
    target_ids.update(attribute.attribute_id for item in entities for attribute in item.attributes)
    target_ids.update(item.enum_id for item in enums)
    evidence: list[dict[str, Any]] = []
    claims: list[dict[str, Any]] = []
    gaps: list[dict[str, Any]] = []
    evidence_by_target: dict[str, list[str]] = {}

    for lineage in model.lineage:
        if lineage.subject_id not in target_ids or lineage.start_line is None:
            continue
        source = (repository_root / lineage.path).resolve()
        try:
            source.relative_to(repository_root)
        except ValueError:
            continue
        if not source.is_file():
            continue
        raw = source.read_bytes()
        line_count = len(raw.splitlines())
        end_line = min(lineage.end_line or lineage.start_line, line_count)
        if not 1 <= lineage.start_line <= end_line:
            continue
        evidence.append(
            {
                "id": lineage.id,
                "path": lineage.path.replace("\\", "/"),
                "sha256": sha256(raw).hexdigest(),
                "start_line": lineage.start_line,
                "end_line": end_line,
            }
        )
        evidence_by_target.setdefault(lineage.subject_id, []).append(lineage.id)

    for target_id in sorted(target_ids):
        citations = sorted(evidence_by_target.get(target_id, []))
        claims.append(
            {
                "id": f"claim-{target_id}",
                "classification": "inferred" if citations else "unknown",
                "evidence_ids": citations,
            }
        )
        if not citations:
            gaps.append(
                {
                    "id": f"gap-evidence-{target_id}",
                    "status": "open",
                    "reason": (
                        "No repository source-line evidence is available for this semantic target."
                    ),
                }
            )

    analyzed_endpoint_ids = sorted(item.operation_id for item in endpoints)
    missing_endpoints = sorted({item.id for item in model.operations} - set(analyzed_endpoint_ids))
    for target_id in missing_endpoints:
        gaps.append(
            {
                "id": f"gap-analysis-{target_id}",
                "status": "open",
                "reason": "The discovered endpoint was not semantically analyzed.",
            }
        )
    for target_id in needs_more_context:
        gaps.append(
            {
                "id": f"gap-context-{target_id}",
                "status": "open",
                "reason": "Confidence remains below 0.70 after bounded context investigation.",
            }
        )
    for index, error in enumerate(errors, 1):
        gaps.append(
            {
                "id": f"gap-error-{index}",
                "status": "open",
                "reason": error,
            }
        )

    complete = not gaps and len(analyzed_endpoint_ids) == len(model.operations)
    return {
        "schema_version": "1.0",
        "status": "complete" if complete else "partial",
        "stop_reason": "no_open_gaps" if complete else "stagnation",
        "inventory_endpoint_ids": sorted(item.id for item in model.operations),
        "analyzed_endpoint_ids": analyzed_endpoint_ids,
        "evidence": sorted(evidence, key=lambda item: item["id"]),
        "claims": claims,
        "gaps": gaps,
    }


def _generate_openapi(
    model: DiscoveryModel,
    endpoints: list[EndpointSemantic],
    entities: list[EntitySemantic],
    enums: list[EnumSemantic],
    model_name: str,
) -> dict[str, Any]:
    endpoint_by_id = {item.operation_id: item for item in endpoints}
    entity_by_id = {item.entity_id: item for item in entities}
    enum_by_id = {item.enum_id: item for item in enums}
    component_names = _component_names(model)
    type_targets = _type_targets(model, component_names)
    validation_by_target: dict[str, list[Any]] = {}
    for item in model.validations:
        validation_by_target.setdefault(item.target_id, []).append(item)

    schemas: dict[str, Any] = {}
    for enum in model.enums:
        semantic = enum_by_id.get(enum.id)
        schema = {
            "type": "string"
            if all(isinstance(item.value, str) for item in enum.values)
            else "integer",
            "enum": [item.value for item in enum.values],
        }
        if semantic:
            schema.update(
                {
                    "description": semantic.description,
                    "x-domain": _domain_extension(semantic.domain),
                    "x-business-concept": semantic.business_concept,
                    "x-source": _subject_sources(model, enum.id, enum.name),
                    "x-confidence": semantic.confidence,
                }
            )
        schemas[component_names[enum.id]] = schema
    for entity in model.entities:
        semantic = entity_by_id.get(entity.id)
        attribute_semantics = (
            {item.attribute_id: item for item in semantic.attributes} if semantic else {}
        )
        properties: dict[str, Any] = {}
        required: list[str] = []
        for attribute in entity.attributes:
            schema = _type_schema(attribute.type, component_names, type_targets)
            attribute_semantic = attribute_semantics.get(attribute.id)
            if attribute_semantic:
                schema["description"] = attribute_semantic.description
                schema["x-business-concept"] = attribute_semantic.business_concept
                schema["x-business-purpose"] = attribute_semantic.business_meaning
                schema["x-source"] = _subject_sources(
                    model, attribute.id, f"{entity.name}.{attribute.original_name}"
                )
                schema["x-confidence"] = attribute_semantic.confidence
            else:
                schema["description"] = (
                    f"Discovered {attribute.original_name} field on {entity.original_name}."
                )
                schema["x-source"] = _subject_sources(
                    model, attribute.id, f"{entity.name}.{attribute.original_name}"
                )
            _apply_validations(schema, validation_by_target.get(attribute.id, []))
            properties[attribute.name] = schema
            if attribute.required:
                required.append(attribute.name)
        schema: dict[str, Any] = {"type": "object", "properties": properties}
        if semantic:
            schema["description"] = semantic.description
            schema["x-domain"] = _domain_extension(semantic.domain)
            schema["x-business-concept"] = semantic.business_concept
            schema["x-source"] = _subject_sources(model, entity.id, entity.name)
            schema["x-confidence"] = semantic.confidence
        else:
            schema["description"] = f"Discovered API contract model {entity.original_name}."
            schema["x-source"] = _subject_sources(model, entity.id, entity.name)
        if required:
            schema["required"] = sorted(required)
        if entity.base_entity_id and entity.base_entity_id in component_names:
            schema = {
                "allOf": [
                    {"$ref": f"#/components/schemas/{component_names[entity.base_entity_id]}"},
                    schema,
                ]
            }
        schemas[component_names[entity.id]] = schema

    paths: dict[str, Any] = {}
    for operation in model.operations:
        semantic = endpoint_by_id.get(operation.id)
        route = re.sub(r"\{([^}:]+)(?::[^}]+)?\}", r"{\1}", operation.route)
        operation_doc: dict[str, Any] = {
            "operationId": operation.name,
        }
        if semantic:
            operation_doc.update(
                {
                    "summary": semantic.summary,
                    "description": semantic.description,
                    "tags": [semantic.domain.name],
                    "x-domain": _domain_extension(semantic.domain),
                    "x-capability": {
                        "name": semantic.capability.name,
                        "confidence": semantic.capability.confidence,
                        **(
                            {"suggestedName": semantic.capability.suggested_name}
                            if semantic.capability.suggested_name
                            else {}
                        ),
                    },
                    "x-business-purpose": semantic.business_purpose,
                    "x-source": _subject_sources(model, operation.id, operation.name),
                    "x-confidence": {
                        "semanticDescription": semantic.confidence,
                        "domain": semantic.domain.confidence,
                        "capability": semantic.capability.confidence,
                    },
                }
            )
        parameters = []
        for parameter in operation.parameters:
            if parameter.location.value == "body":
                continue
            parameters.append(
                {
                    "name": parameter.name,
                    "in": "path"
                    if parameter.location.value == "route"
                    else parameter.location.value,
                    "required": True if parameter.location.value == "route" else parameter.required,
                    "description": (
                        f"Discovered {parameter.location.value} parameter {parameter.name}."
                    ),
                    "schema": _type_schema(parameter.type, component_names, type_targets),
                    "x-source": _subject_sources_with_fallback(
                        model,
                        [parameter.id, operation.id],
                        f"{operation.name}.{parameter.name}",
                    ),
                }
            )
        if parameters:
            operation_doc["parameters"] = parameters
        body_parameter = next(
            (item for item in operation.parameters if item.location.value == "body"), None
        )
        if (
            operation.request_entity_id and operation.request_entity_id in component_names
        ) or body_parameter:
            request_schema = (
                {"$ref": (f"#/components/schemas/{component_names[operation.request_entity_id]}")}
                if operation.request_entity_id and operation.request_entity_id in component_names
                else _type_schema(body_parameter.type, component_names, type_targets)
            )
            request_body: dict[str, Any] = {
                "required": body_parameter.required if body_parameter else True,
                "content": {"application/json": {"schema": request_schema}},
            }
            if semantic:
                request_body["description"] = semantic.request_description
            else:
                request_body["description"] = (
                    "Request body using the discovered "
                    f"{component_names[operation.request_entity_id]} contract."
                    if operation.request_entity_id
                    and operation.request_entity_id in component_names
                    else f"Request body using the discovered {body_parameter.type.name} type."
                )
            request_body["x-source"] = _subject_sources_with_fallback(
                model,
                [
                    *([body_parameter.id] if body_parameter else []),
                    *([operation.request_entity_id] if operation.request_entity_id else []),
                    operation.id,
                ],
                (
                    f"{operation.name}.{body_parameter.name}"
                    if body_parameter
                    else component_names[operation.request_entity_id]
                ),
            )
            operation_doc["requestBody"] = request_body
        else:
            operation_doc["requestBody"] = {
                "required": False,
                "description": "No request body model was discovered.",
                "content": {"application/json": {"schema": {}}},
                "x-source": _subject_sources(model, operation.id, operation.name),
            }
        operation_doc["responses"] = {}
        semantic_responses = (
            {item.status_code: item.description for item in semantic.responses} if semantic else {}
        )
        for response in operation.responses:
            structural_description = response.description or _status_description(
                response.status_code
            )
            response_doc: dict[str, Any] = {
                "description": semantic_responses.get(response.status_code, structural_description)
            }
            if response.entity_id and response.entity_id in component_names:
                response_model_name = component_names[response.entity_id]
                if response.status_code not in semantic_responses:
                    response_doc["description"] = (
                        f"HTTP {response.status_code} response using the discovered "
                        f"{response_model_name} contract."
                    )
                response_doc["content"] = {
                    "application/json": {
                        "schema": {
                            "$ref": f"#/components/schemas/{component_names[response.entity_id]}"
                        }
                    }
                }
                response_entity = next(
                    item for item in model.entities if item.id == response.entity_id
                )
                response_semantic = entity_by_id.get(response.entity_id)
                response_attribute_semantics = (
                    {item.attribute_id: item for item in response_semantic.attributes}
                    if response_semantic
                    else {}
                )
                response_doc["x-response-model"] = {
                    "name": response_model_name,
                    "schemaRef": f"#/components/schemas/{response_model_name}",
                    "description": (
                        response_semantic.description
                        if response_semantic
                        else f"Discovered API contract model {response_entity.original_name}."
                    ),
                    "attributes": [
                        {
                            "name": attribute.name,
                            "required": attribute.required,
                            "description": (
                                response_attribute_semantics[attribute.id].description
                                if attribute.id in response_attribute_semantics
                                else (
                                    f"Discovered {attribute.original_name} field on "
                                    f"{response_entity.original_name}."
                                )
                            ),
                            "schema": _type_schema(attribute.type, component_names, type_targets),
                        }
                        for attribute in response_entity.attributes
                    ],
                }
            elif response.type:
                response_doc["content"] = {
                    "application/json": {
                        "schema": _type_schema(response.type, component_names, type_targets)
                    }
                }
            else:
                response_doc["content"] = {"application/json": {"schema": {}}}
            response_doc["x-source"] = _subject_sources_with_fallback(
                model,
                [response.id, response.entity_id, operation.id],
                f"{operation.name} response {response.status_code}",
            )
            operation_doc["responses"][str(response.status_code)] = response_doc
        if not operation_doc["responses"]:
            operation_doc["responses"]["default"] = {
                "description": "No response body model was discovered.",
                "content": {"application/json": {"schema": {}}},
                "x-source": _subject_sources(model, operation.id, operation.name),
            }
        paths.setdefault(route, {})[operation.method.lower()] = operation_doc

    used_domains = sorted({item.domain.name for item in endpoints})
    return {
        "openapi": "3.0.3",
        "info": {
            "title": f"{model.system} enriched API",
            "version": "1.0.0",
            "description": (
                "Generated from Phase 1 structural discovery and evidence-grounded "
                "semantic enrichment."
            ),
            "x-source": {
                "phase1RunId": model.run.id,
                "semanticModel": model_name,
            },
        },
        "tags": [
            {
                "name": name,
                "description": DOMAIN_DESCRIPTIONS.get(
                    name, f"Repository-derived {name} domain endpoints."
                ),
            }
            for name in used_domains
        ],
        "servers": [
            {
                "url": "/",
                "description": "Relative API root; no deployment server was discovered.",
            }
        ],
        "paths": paths,
        "components": {"schemas": schemas},
    }


def _domain_extension(domain: DomainSemantic) -> dict[str, Any]:
    return {
        "name": domain.name,
        "confidence": domain.confidence,
        **({"suggestedName": domain.suggested_name} if domain.suggested_name else {}),
    }


def _subject_sources(model: DiscoveryModel, subject_id: str, symbol: str) -> list[dict[str, Any]]:
    return [
        {
            "path": item.path,
            "symbol": symbol,
            **({"startLine": item.start_line} if item.start_line else {}),
            **({"endLine": item.end_line} if item.end_line else {}),
            **({"pointer": item.pointer} if item.pointer else {}),
        }
        for item in model.lineage
        if item.subject_id == subject_id
    ]


def _subject_sources_with_fallback(
    model: DiscoveryModel,
    subject_ids: list[str | None],
    symbol: str,
) -> list[dict[str, Any]]:
    for subject_id in subject_ids:
        if subject_id:
            sources = _subject_sources(model, subject_id, symbol)
            if sources:
                return sources
    return []


def _component_names(model: DiscoveryModel) -> dict[str, str]:
    result: dict[str, str] = {}
    used: set[str] = set()
    for item in [*model.enums, *model.entities]:
        base = re.sub(r"[^A-Za-z0-9_.-]", "", item.name.rsplit(".", 1)[-1]) or "Schema"
        candidate = base
        if candidate in used:
            candidate = f"{base}_{item.id.rsplit('-', 1)[-1][:8]}"
        used.add(candidate)
        result[item.id] = candidate
    return result


def _type_targets(
    model: DiscoveryModel,
    component_names: dict[str, str],
) -> dict[str, str]:
    targets: dict[str, str] = {}
    for item in model.enums:
        for name in {item.name, item.name.rsplit(".", 1)[-1]}:
            targets[_normalize_clr_type(name)] = component_names[item.id]
    for item in model.entities:
        for name in {
            item.name,
            item.original_name,
            item.name.rsplit(".", 1)[-1],
            item.original_name.rsplit(".", 1)[-1],
        }:
            targets[_normalize_clr_type(name)] = component_names[item.id]
    return targets


def _normalize_clr_type(value: str) -> str:
    value = value.replace("global::", "").strip().rstrip("?")
    generic = re.search(r"<([^<>]+)>$", value)
    if generic:
        value = generic.group(1).split(",", 1)[0].strip()
    value = value.removesuffix("[]").rsplit(".", 1)[-1]
    return re.sub(r"[^A-Za-z0-9_]", "", value).lower()


def _type_schema(
    type_ref: TypeRef,
    component_names: dict[str, str],
    type_targets: dict[str, str] | None = None,
) -> dict[str, Any]:
    resolved_component = (type_targets or {}).get(_normalize_clr_type(type_ref.name))
    if type_ref.reference_id in component_names:
        schema: dict[str, Any] = {
            "$ref": f"#/components/schemas/{component_names[type_ref.reference_id]}"
        }
    elif resolved_component:
        schema = {"$ref": f"#/components/schemas/{resolved_component}"}
    else:
        types = {
            TypeKind.STRING: "string",
            TypeKind.INTEGER: "integer",
            TypeKind.NUMBER: "number",
            TypeKind.BOOLEAN: "boolean",
            TypeKind.UUID: "string",
            TypeKind.DATE_TIME: "string",
            TypeKind.OBJECT: "object",
            TypeKind.ENUM: "string",
            TypeKind.UNKNOWN: "string",
        }
        schema = {"type": types[type_ref.kind]}
        if type_ref.kind == TypeKind.UUID:
            schema["format"] = "uuid"
        elif type_ref.kind == TypeKind.DATE_TIME:
            schema["format"] = type_ref.format or "date-time"
        elif type_ref.format:
            schema["format"] = type_ref.format
        if type_ref.kind == TypeKind.UNKNOWN:
            schema["x-unresolved-clr-type"] = type_ref.name
    if type_ref.nullable:
        schema["nullable"] = True
    if type_ref.collection:
        schema = {"type": "array", "items": schema}
    return schema


def _apply_validations(schema: dict[str, Any], validations: list[Any]) -> None:
    for validation in validations:
        rule = validation.rule.lower()
        arguments = validation.arguments
        value = arguments.get("value")
        values = arguments.get("values", [])
        if (
            rule
            in {"minimum", "maximum", "minlength", "maxlength", "minitems", "maxitems", "pattern"}
            and value is not None
        ):
            key = {
                "minlength": "minLength",
                "maxlength": "maxLength",
                "minitems": "minItems",
                "maxitems": "maxItems",
            }.get(rule, rule)
            schema[key] = value
        elif rule == "range" and len(values) >= 3:
            schema["minimum"] = _number(values[-2])
            schema["maximum"] = _number(values[-1])
        elif rule == "stringlength" and values:
            schema["maxLength"] = int(values[0])
            for item in values[1:]:
                if str(item).lower().startswith("minimumlength="):
                    schema["minLength"] = int(str(item).split("=", 1)[1])
        elif rule == "regularexpression" and values:
            schema["pattern"] = values[0]


def _number(value: Any) -> int | float:
    number = float(value)
    return int(number) if number.is_integer() else number


def _status_description(status_code: int) -> str:
    if 200 <= status_code < 300:
        return "Successful response"
    if 400 <= status_code < 500:
        return "Client error response"
    if status_code >= 500:
        return "Server error response"
    return "Response"


def _validate_openapi_document(document: dict[str, Any], source: DiscoveryModel) -> list[str]:
    try:
        with TemporaryDirectory(prefix="semantic-openapi-validation-") as temporary:
            path = Path(temporary) / "enriched-openapi.yaml"
            path.write_text(yaml.safe_dump(document, sort_keys=False), encoding="utf-8")
            parsed = discover_openapi(path, source.region, source.system)
        if len(parsed.operations) != len(source.operations):
            return [
                f"Generated OpenAPI contains {len(parsed.operations)} operations; "
                f"Phase 1 contains {len(source.operations)}."
            ]
    except (OSError, TypeError, ValueError, yaml.YAMLError) as exc:
        return [f"Generated OpenAPI validation failed: {exc}"]
    return []


def _validate_semantic_evidence(
    model: DiscoveryModel,
    endpoints: list[EndpointSemantic],
    entities: list[EntitySemantic],
    enums: list[EnumSemantic],
) -> list[str]:
    subjects = {item.subject_id for item in model.lineage}
    targets = {item.operation_id for item in endpoints}
    targets.update(item.entity_id for item in entities)
    targets.update(attribute.attribute_id for item in entities for attribute in item.attributes)
    targets.update(item.enum_id for item in enums)
    missing = sorted(targets - subjects)
    return [f"Semantic target has no Phase 1 source lineage: {item}" for item in missing]


def _build_evidence_map(
    model: DiscoveryModel,
    model_name: str,
    endpoint_contexts: list[dict[str, Any]],
    entity_contexts: list[dict[str, Any]],
    enum_contexts: list[dict[str, Any]],
    endpoints: list[EndpointSemantic],
    entities: list[EntitySemantic],
    enums: list[EnumSemantic],
) -> dict[str, Any]:
    context_by_operation = {item["operation"]["id"]: item for item in endpoint_contexts}
    context_by_entity = {item["entity"]["id"]: item for item in entity_contexts}
    context_by_enum = {item["enum"]["id"]: item for item in enum_contexts}
    items: list[dict[str, Any]] = []
    for item in endpoints:
        context = context_by_operation[item.operation_id]
        items.append(
            {
                "targetType": "endpoint",
                "targetId": item.operation_id,
                "generatedBy": model_name,
                "classification": "inferred",
                "confidence": {
                    "semanticDescription": item.confidence,
                    "domain": item.domain.confidence,
                    "capability": item.capability.confidence,
                },
                "evidence": _context_locations(context),
            }
        )
    for entity in entities:
        context = context_by_entity[entity.entity_id]
        locations = _context_locations(context)
        items.append(
            {
                "targetType": "entity",
                "targetId": entity.entity_id,
                "generatedBy": model_name,
                "classification": "inferred",
                "confidence": entity.confidence,
                "evidence": locations,
            }
        )
        for attribute in entity.attributes:
            attribute_locations = [
                line.model_dump(mode="json", by_alias=True)
                for line in model.lineage
                if line.subject_id == attribute.attribute_id
            ]
            items.append(
                {
                    "targetType": "attribute",
                    "targetId": attribute.attribute_id,
                    "generatedBy": model_name,
                    "classification": "inferred",
                    "confidence": attribute.confidence,
                    "evidence": attribute_locations or locations,
                }
            )
    for enum in enums:
        context = context_by_enum[enum.enum_id]
        items.append(
            {
                "targetType": "enum",
                "targetId": enum.enum_id,
                "generatedBy": model_name,
                "classification": "inferred",
                "confidence": enum.confidence,
                "evidence": _context_locations(context),
            }
        )
    return {"schemaVersion": "1.0", "items": items}


def _context_locations(context: dict[str, Any]) -> list[dict[str, Any]]:
    return [
        {"path": item["path"], "startLine": item["startLine"], "endLine": item["endLine"]}
        for item in context.get("sourceSnippets", [])
    ]


def _confidence_bands(
    endpoints: list[EndpointSemantic],
    entities: list[EntitySemantic],
    enums: list[EnumSemantic],
) -> dict[str, list[str]]:
    scores: dict[str, float] = {
        item.operation_id: _endpoint_minimum_confidence(item) for item in endpoints
    }
    for entity in entities:
        scores[entity.entity_id] = min(entity.confidence, entity.domain.confidence)
        scores.update({item.attribute_id: item.confidence for item in entity.attributes})
    scores.update({item.enum_id: min(item.confidence, item.domain.confidence) for item in enums})
    return {
        "autoAccept": sorted(
            key for key, value in scores.items() if value >= AUTO_ACCEPT_THRESHOLD
        ),
        "review": sorted(
            key
            for key, value in scores.items()
            if REVIEW_THRESHOLD <= value < AUTO_ACCEPT_THRESHOLD
        ),
        "needsMoreContext": sorted(
            key for key, value in scores.items() if value < REVIEW_THRESHOLD
        ),
    }


def _json_bytes(value: Any) -> bytes:
    return (json.dumps(value, indent=2, sort_keys=True) + "\n").encode("utf-8")
