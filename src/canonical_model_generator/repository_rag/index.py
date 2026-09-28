"""Persistent Chroma index with exact attribution and hybrid graph-aware retrieval."""

from __future__ import annotations

import json
import math
import re
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

import chromadb
from chromadb.config import Settings

from canonical_model_generator.discovery_agent.model import DiscoveryModel
from canonical_model_generator.repository_rag.chunking import build_chunks, digest, read_sources
from canonical_model_generator.repository_rag.embeddings import (
    Embedder,
    EmbeddingConfig,
    create_embedder,
)

VERSION = "repository-rag/1.0"


def _model_digest(model: DiscoveryModel | None) -> str:
    return digest(model.model_dump_json(by_alias=True)) if model else ""


def _tokens(value: str) -> set[str]:
    split = re.sub(r"(?<=[a-z0-9])(?=[A-Z])", " ", value)
    return set(re.findall(r"[a-z0-9_]+", value.lower() + " " + split.lower()))


class ChromaRepositoryIndex:
    """One immutable repository snapshot and embedding profile per directory."""

    def __init__(self, storage_path: Path, embedder: Embedder | None = None) -> None:
        self.storage_path = storage_path.resolve()
        self.manifest_path = self.storage_path / "rag-manifest.json"
        self.manifest: dict[str, Any] = {}
        if self.manifest_path.exists():
            self.manifest = json.loads(self.manifest_path.read_text(encoding="utf-8"))
            if self.manifest.get("schemaVersion") != VERSION:
                raise ValueError("Unsupported RAG artifact version; rebuild the index")
            config = EmbeddingConfig.model_validate(self.manifest["embedding"])
            if embedder is not None and embedder.config != config:
                raise ValueError("Embedding model mismatch; rebuild into a new index directory")
            embedder = embedder or create_embedder(config)
        self.embedder = embedder or create_embedder()
        self._client = chromadb.PersistentClient(
            path=str(self.storage_path / "chroma"), settings=Settings(anonymized_telemetry=False)
        )
        self._collection = None
        if self.manifest:
            try:
                self._collection = self._client.get_collection(
                    self.manifest["collection"], embedding_function=None
                )
                if self._collection.count() != len(self.manifest["chunks"]):
                    raise ValueError("Incomplete Chroma index; rebuild the RAG artifact")
                self._prepare()
            except Exception:
                self._client.close()
                raise

    def _prepare(self) -> None:
        self._chunks = {chunk["id"]: chunk for chunk in self.manifest["chunks"]}
        if len(self._chunks) != len(self.manifest["chunks"]):
            raise ValueError("Duplicate chunk identities in RAG artifact")
        self._neighbors: dict[str, list[tuple[str, str, str]]] = defaultdict(list)
        self._terms = {
            key: _tokens(value["symbol"] + " " + value["text"])
            for key, value in self._chunks.items()
        }
        self._frequency = Counter(term for terms in self._terms.values() for term in terms)
        for edge in self.manifest["relationships"]:
            if edge["source"] not in self._chunks or edge["target"] not in self._chunks:
                raise ValueError("Dangling RAG relationship")
            self._neighbors[edge["source"]].append(
                (edge["target"], edge["kind"], edge["resolution"])
            )
            self._neighbors[edge["target"]].append(
                (edge["source"], edge["kind"], edge["resolution"])
            )

    def ingest(
        self, repository_root: Path, model: DiscoveryModel | None = None, progress=None
    ) -> dict[str, Any]:
        files, gaps = read_sources(repository_root)
        hashes = {item["path"]: item["sha256"] for item in files}
        if self.manifest:
            self.validate_snapshot(repository_root, model)
            return self.manifest["stats"]
        if not files:
            raise ValueError("No supported repository source files to index")
        if progress:
            progress(f"Parsing code hierarchy for {len(files)} source files")
        chunks, edges, syntax_gaps = build_chunks(files)
        ids = [chunk["id"] for chunk in chunks]
        duplicate_ids = [key for key, count in Counter(ids).items() if count > 1]
        if duplicate_ids:
            duplicate = next(chunk for chunk in chunks if chunk["id"] == duplicate_ids[0])
            raise ValueError(
                "Duplicate code-chunk identity before indexing: "
                f"{duplicate['path']}:{duplicate['startLine']} ({duplicate['kind']}); "
                "the source was not upserted"
            )
        bindings, targets, binding_gaps = _bind_subjects(chunks, edges, model)
        fingerprint = digest(
            json.dumps(
                {
                    "files": hashes,
                    "embedding": self.embedder.config.model_dump(),
                    "discovery": _model_digest(model),
                    "version": VERSION,
                    "chunkIdentity": "window-ordinal-v2",
                },
                sort_keys=True,
            )
        )
        collection_name = "code-" + fingerprint[:32]
        self._collection = self._client.get_or_create_collection(
            collection_name, embedding_function=None, metadata={"hnsw:space": "cosine"}
        )
        dimensions = None
        for start in range(0, len(chunks), 32):
            batch = chunks[start : start + 32]
            documents = [f"{item['path']}\n{item['symbol']}\n{item['text']}" for item in batch]
            vectors = self.embedder.embed(documents)
            if len(vectors) != len(batch):
                raise ValueError("Embedding count does not match the source chunks")
            for vector in vectors:
                dimensions = dimensions or len(vector)
                if not vector or len(vector) != dimensions or not all(map(math.isfinite, vector)):
                    raise ValueError("Invalid embedding dimensions or values")
            self._collection.upsert(
                ids=[item["id"] for item in batch],
                documents=documents,
                embeddings=vectors,
                metadatas=[
                    {
                        key: item[key]
                        for key in ("path", "kind", "symbol", "startLine", "endLine", "sha256")
                    }
                    for item in batch
                ],
            )
            if progress:
                progress(f"Embedded {min(start + 32, len(chunks))}/{len(chunks)} code chunks")
        all_gaps = sorted(set([*gaps, *syntax_gaps, *binding_gaps]))
        stats = {
            "provider": "chroma",
            "embedding": self.embedder.config.model,
            "filesIndexed": len(files),
            "chunksIndexed": len(chunks),
            "relationshipsIndexed": len(edges),
            "subjectsBound": len(bindings),
            "skippedFiles": len(gaps),
            "truncated": bool(all_gaps),
            "storage": "persistent-local",
            "gaps": all_gaps,
            "referenceResolution": "syntax-candidates",
            "dimensions": dimensions,
        }
        self.manifest = {
            "schemaVersion": VERSION,
            "snapshotId": fingerprint,
            "collection": collection_name,
            "embedding": self.embedder.config.model_dump(),
            "files": hashes,
            "discoveryDigest": _model_digest(model),
            "chunks": chunks,
            "relationships": edges,
            "bindings": bindings,
            "targets": targets,
            "stats": stats,
        }
        self._prepare()
        staged = self.storage_path / "rag-manifest.pending.json"
        staged.write_text(json.dumps(self.manifest, indent=2, sort_keys=True), encoding="utf-8")
        staged.replace(self.manifest_path)
        return stats

    def validate_snapshot(self, repository_root: Path, model: DiscoveryModel | None = None) -> None:
        files, _ = read_sources(repository_root)
        if {item["path"]: item["sha256"] for item in files} != self.manifest.get("files"):
            raise ValueError("Repository snapshot changed; rebuild the RAG index")
        if model is not None and _model_digest(model) != self.manifest.get("discoveryDigest"):
            raise ValueError("Discovery artifact changed; rebuild the RAG index")

    def query(
        self,
        query_text: str,
        *,
        limit: int = 8,
        subject_id: str | None = None,
        max_characters: int = 12_000,
    ) -> list[dict[str, Any]]:
        if not 1 <= limit <= 30 or not 1 <= max_characters <= 48_000:
            raise ValueError("Retrieval bounds exceeded")
        if not self.manifest or self._collection is None:
            return []
        if not query_text.strip() or len(query_text) > 2000:
            raise ValueError("Query must contain 1-2000 characters")
        if subject_id and subject_id not in {t["id"] for t in self.manifest["targets"]}:
            raise ValueError("Unknown discovery subject ID")
        exact = list(self.manifest["bindings"].get(subject_id, [])) if subject_id else []
        if not subject_id:
            matching = [
                target
                for target in self.manifest["targets"]
                if query_text.casefold() in [alias.casefold() for alias in target["aliases"]]
            ]
            exact = list(
                dict.fromkeys(
                    key
                    for target in matching
                    for key in self.manifest["bindings"].get(target["id"], [])
                )
            )
        terms = _tokens(query_text)
        scores: dict[str, float] = defaultdict(float)
        reasons: dict[str, str] = {}
        lexical = sorted(
            self._chunks,
            key=lambda key: (
                -sum(
                    math.log(1 + len(self._chunks) / self._frequency[term])
                    for term in terms & self._terms[key]
                ),
                key,
            ),
        )
        for rank, key in enumerate(lexical[:40]):
            if terms & self._terms[key]:
                scores[key] += 1 / (60 + rank)
                reasons[key] = "lexical"
        vectors = self.embedder.embed([query_text])
        results = self._collection.query(
            query_embeddings=vectors, n_results=min(40, len(self._chunks)), include=["distances"]
        )
        for rank, key in enumerate(results["ids"][0]):
            scores[key] += 1 / (60 + rank)
            reasons[key] = "lexical+vector" if key in reasons else "vector"
        for rank, key in enumerate(exact):
            scores[key] = 10 - rank / 1000
            reasons[key] = "exact-lineage"
        seeds = exact or sorted(scores, key=lambda key: (-scores[key], key))[:3]
        for key in seeds[:12]:
            for neighbor, kind, resolution in self._neighbors[key][:100]:
                if neighbor not in exact:
                    priority = 1.0 if resolution != "candidate" else 0.5
                    if priority > scores[neighbor]:
                        scores[neighbor] = priority
                        reasons[neighbor] = f"{kind}:{resolution}"
        ordered = sorted(scores, key=lambda key: (-scores[key], key))
        snippets: list[dict[str, Any]] = []
        seen: set[tuple] = set()
        remaining = max_characters
        for key in ordered:
            chunk = self._chunks[key]
            identity = (
                chunk["path"],
                chunk["startLine"],
                chunk["endLine"],
                chunk["text"],
                chunk["kind"],
                chunk["symbol"],
                chunk.get("windowIndex"),
            )
            if identity in seen:
                continue
            seen.add(identity)
            text = chunk["text"][:remaining]
            snippets.append(
                {
                    **chunk,
                    "chunkId": key,
                    "text": text,
                    "truncated": chunk["truncated"] or len(text) < len(chunk["text"]),
                    "retrievalMethod": "exact+lexical+chroma+relationships",
                    "retrievalReason": reasons[key],
                    "relevance": round(scores[key], 6),
                }
            )
            remaining -= len(text)
            if len(snippets) >= limit or remaining <= 0:
                break
        return snippets

    def close(self) -> None:
        self._client.close()


def _bind_subjects(chunks: list[dict], edges: list[dict], model: DiscoveryModel | None):
    bindings: dict[str, list[str]] = {}
    targets: list[dict] = []
    gaps: list[str] = []
    if model is None:
        return bindings, targets, gaps
    for operation in model.operations:
        targets.append(
            {
                "id": operation.id,
                "kind": "endpoint",
                "label": f"{operation.method} {operation.route} ({operation.name})",
                "aliases": [operation.id, operation.name, f"{operation.method} {operation.route}"],
            }
        )
    for entity in model.entities:
        targets.append(
            {
                "id": entity.id,
                "kind": "entity",
                "label": entity.original_name,
                "aliases": [entity.id, entity.name, entity.original_name],
            }
        )
        for attribute in entity.attributes:
            label = f"{entity.original_name}.{attribute.original_name}"
            targets.append(
                {
                    "id": attribute.id,
                    "kind": "attribute",
                    "label": label,
                    "aliases": [attribute.id, label, f"{entity.name}.{attribute.name}"],
                }
            )
    for enum in model.enums:
        targets.append(
            {"id": enum.id, "kind": "enum", "label": enum.name, "aliases": [enum.id, enum.name]}
        )
    by_path: dict[str, list[dict]] = defaultdict(list)
    for chunk in chunks:
        by_path[chunk["path"]].append(chunk)
    for target in targets:
        candidates: list[dict] = []
        for line in model.lineage:
            if line.subject_id != target["id"] or not line.start_line:
                continue
            matching = [
                chunk
                for chunk in by_path.get(line.path.replace("\\", "/"), [])
                if chunk["startLine"] <= line.start_line <= chunk["endLine"]
                and chunk["kind"] != "window"
            ]
            if matching:
                kinds = {
                    "endpoint": {"MethodDeclaration"},
                    "entity": {"ClassDeclaration", "RecordDeclaration", "StructDeclaration"},
                    "attribute": {"PropertyDeclaration", "FieldDeclaration"},
                    "enum": {"EnumDeclaration"},
                }
                owned = [c for c in matching if c["kind"] in kinds[target["kind"]]]
                named = [
                    c
                    for c in owned
                    if any(
                        alias.rsplit(".", 1)[-1].casefold() == c["name"].casefold()
                        for alias in target["aliases"]
                    )
                ]
                matching = named or owned or matching
                qualified = [
                    c
                    for c in matching
                    if any(
                        c["symbol"].split("(")[0].casefold().endswith(alias.casefold())
                        for alias in target["aliases"]
                        if "." in alias
                    )
                ]
                matching = qualified or matching
                span_size = min(c["endLine"] - c["startLine"] for c in matching)
                smallest = [c for c in matching if c["endLine"] - c["startLine"] == span_size]
                candidates.extend(smallest)
                if len(smallest) > 1:
                    gaps.append(
                        f"Ambiguous source span for {target['label']}; all candidates retained"
                    )
        for chunk in candidates:
            chunk["subjectIds"].append(target["id"])
        if candidates:
            bindings[target["id"]] = sorted({c["id"] for c in candidates})
        else:
            gaps.append(f"No source chunk bound to {target['kind']}: {target['label']}")
    for relation in model.relationships:
        for source in bindings.get(relation.source_id, []):
            for target in bindings.get(relation.target_id, []):
                if source != target:
                    edges.append(
                        {
                            "source": source,
                            "target": target,
                            "kind": relation.kind.value,
                            "resolution": "discovery",
                        }
                    )
    return bindings, targets, gaps
