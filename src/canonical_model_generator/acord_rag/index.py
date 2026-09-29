"""Persistent semantic index for one independently ingested ACORD reference."""

from __future__ import annotations

import json
import math
import re
from collections import Counter
from hashlib import sha256
from pathlib import Path
from typing import Any

import chromadb
from chromadb.config import Settings

from canonical_model_generator.repository_rag.embeddings import (
    Embedder,
    EmbeddingConfig,
    create_embedder,
)

VERSION = "acord-rag/1.0"


def _tokens(value: str) -> set[str]:
    split = re.sub(r"(?<=[a-z0-9])(?=[A-Z])", " ", value)
    return set(re.findall(r"[a-z0-9_]+", value.casefold() + " " + split.casefold()))


class AcordDocumentIndex:
    """One immutable ACORD document snapshot and embedding profile per directory."""

    def __init__(self, storage_path: Path, embedder: Embedder | None = None) -> None:
        self.storage_path = storage_path.resolve()
        self.storage_path.mkdir(parents=True, exist_ok=True)
        self.manifest_path = self.storage_path / "acord-rag-manifest.json"
        self.manifest: dict[str, Any] = {}
        if self.manifest_path.is_file():
            self.manifest = json.loads(self.manifest_path.read_text(encoding="utf-8"))
            if self.manifest.get("schemaVersion") != VERSION:
                raise ValueError("Unsupported ACORD RAG artifact version; rebuild the index")
            config = EmbeddingConfig.model_validate(self.manifest["embedding"])
            if embedder is not None and embedder.config != config:
                raise ValueError("Embedding model mismatch; rebuild the ACORD index")
            embedder = embedder or create_embedder(config)
        self.embedder = embedder or create_embedder()
        self._client = chromadb.PersistentClient(
            path=str(self.storage_path / "chroma"), settings=Settings(anonymized_telemetry=False)
        )
        self._collection = None
        if self.manifest:
            self._collection = self._client.get_collection(
                self.manifest["collection"], embedding_function=None
            )
            if self._collection.count() != len(self.manifest["chunks"]):
                raise ValueError("Incomplete ACORD Chroma index; rebuild the ingestion")
            self._prepare()

    def _prepare(self) -> None:
        self._chunks = {item["id"]: item for item in self.manifest["chunks"]}
        if len(self._chunks) != len(self.manifest["chunks"]):
            raise ValueError("Duplicate ACORD chunk identities in the saved index")
        self._terms = {key: _tokens(item["text"]) for key, item in self._chunks.items()}
        self._frequency = Counter(term for terms in self._terms.values() for term in terms)

    def ingest(
        self,
        model: dict[str, Any],
        chunks: list[dict[str, Any]],
        *,
        progress=None,
    ) -> dict[str, Any]:
        if not chunks:
            raise ValueError("The ACORD document produced no retrieval chunks")
        model_json = json.dumps(model, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
        model_digest = sha256(model_json.encode("utf-8")).hexdigest()
        if self.manifest:
            if self.manifest.get("modelDigest") != model_digest:
                raise ValueError("ACORD document changed; build a new independent index")
            return self.manifest["stats"]
        ids = [item["id"] for item in chunks]
        if len(ids) != len(set(ids)):
            raise ValueError("Duplicate ACORD chunk identity before indexing")
        fingerprint = sha256(
            json.dumps(
                {
                    "modelDigest": model_digest,
                    "embedding": self.embedder.config.model_dump(),
                    "version": VERSION,
                },
                sort_keys=True,
            ).encode("utf-8")
        ).hexdigest()
        collection_name = "acord-" + fingerprint[:32]
        self._collection = self._client.get_or_create_collection(
            collection_name, embedding_function=None, metadata={"hnsw:space": "cosine"}
        )
        dimensions = None
        for start in range(0, len(chunks), 32):
            batch = chunks[start : start + 32]
            documents = [item["text"] for item in batch]
            vectors = self.embedder.embed(documents)
            if len(vectors) != len(batch):
                raise ValueError("Embedding count does not match the ACORD chunks")
            for vector in vectors:
                dimensions = dimensions or len(vector)
                if not vector or len(vector) != dimensions or not all(map(math.isfinite, vector)):
                    raise ValueError("Invalid ACORD embedding dimensions or values")
            self._collection.upsert(
                ids=[item["id"] for item in batch],
                documents=documents,
                embeddings=vectors,
                metadatas=[
                    {
                        "kind": item["kind"],
                        "subject": item["subject"],
                        "sourcePointer": item["sourcePointer"],
                    }
                    for item in batch
                ],
            )
            if progress:
                progress(f"Embedded {min(start + 32, len(chunks))}/{len(chunks)} ACORD chunks")
        stats = {
            "provider": "chroma",
            "embedding": self.embedder.config.model,
            "documentsIndexed": 1,
            "chunksIndexed": len(chunks),
            "endpointChunks": sum(item["kind"] == "endpoint" for item in chunks),
            "entityChunks": sum(item["kind"] == "entity" for item in chunks),
            "storage": "persistent-local",
            "dimensions": dimensions,
        }
        self.manifest = {
            "schemaVersion": VERSION,
            "snapshotId": fingerprint,
            "collection": collection_name,
            "embedding": self.embedder.config.model_dump(),
            "source": model["source"],
            "modelDigest": model_digest,
            "chunks": chunks,
            "stats": stats,
        }
        self._prepare()
        pending = self.storage_path / "acord-rag-manifest.pending.json"
        pending.write_text(
            json.dumps(self.manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
        pending.replace(self.manifest_path)
        return stats

    def query(
        self,
        query_text: str,
        *,
        limit: int = 8,
        max_characters: int = 20_000,
    ) -> list[dict[str, Any]]:
        if not self.manifest or self._collection is None:
            return []
        if not query_text.strip() or len(query_text) > 2_000:
            raise ValueError("ACORD query must contain 1-2000 characters")
        if not 1 <= limit <= 30 or not 1 <= max_characters <= 48_000:
            raise ValueError("ACORD retrieval bounds exceeded")
        terms = _tokens(query_text)
        scores: dict[str, float] = {}
        reasons: dict[str, str] = {}
        for key, chunk_terms in self._terms.items():
            common = terms & chunk_terms
            if common:
                scores[key] = sum(
                    math.log(1 + len(self._chunks) / self._frequency[term]) for term in common
                )
                reasons[key] = "lexical"
        exact = [
            key
            for key, item in self._chunks.items()
            if query_text.casefold() in {alias.casefold() for alias in item.get("aliases", [])}
        ]
        query_vector = self.embedder.embed([query_text])
        results = self._collection.query(
            query_embeddings=query_vector,
            n_results=min(40, len(self._chunks)),
            include=["distances"],
        )
        for rank, key in enumerate(results["ids"][0]):
            scores[key] = scores.get(key, 0.0) + 1 / (60 + rank)
            reasons[key] = "lexical+vector" if reasons.get(key) == "lexical" else "vector"
        for rank, key in enumerate(exact):
            scores[key] = 100.0 - rank / 1000
            reasons[key] = "exact-subject"
        remaining = max_characters
        snippets = []
        for key in sorted(scores, key=lambda item: (-scores[item], item)):
            chunk = self._chunks[key]
            text = chunk["text"][:remaining]
            snippets.append(
                {
                    **chunk,
                    "chunkId": key,
                    "text": text,
                    "truncated": chunk["truncated"] or len(text) < len(chunk["text"]),
                    "retrievalMethod": "exact+lexical+chroma",
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
