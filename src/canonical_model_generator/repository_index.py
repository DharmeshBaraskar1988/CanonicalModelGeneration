"""Local, bounded Chroma index for repository retrieval."""

from __future__ import annotations

import math
import re
from hashlib import sha256
from pathlib import Path
from typing import Any

import chromadb
from chromadb.config import Settings

CHUNK_LINES = 100
CHUNK_OVERLAP_LINES = 20
EMBEDDING_DIMENSIONS = 384
MAX_FILES = 5_000
MAX_CHUNKS = 10_000
MAX_FILE_BYTES = 1_000_000
INDEXED_SUFFIXES = {
    ".cs",
    ".cshtml",
    ".razor",
    ".csproj",
    ".props",
    ".targets",
    ".json",
    ".yaml",
    ".yml",
    ".config",
    ".xml",
}
EXCLUDED_PARTS = {".git", ".vs", "bin", "obj", "node_modules", "packages"}
EXCLUDED_NAMES = {".env", "secrets.json"}
COLLECTION_NAME = "repository-context"


class ChromaRepositoryIndex:
    """Persist redacted source chunks locally for one bounded analysis run."""

    def __init__(self, storage_path: Path) -> None:
        self.storage_path = storage_path.resolve()
        self._client = chromadb.PersistentClient(
            path=str(self.storage_path),
            settings=Settings(anonymized_telemetry=False),
        )
        self._collection = self._client.get_or_create_collection(
            COLLECTION_NAME,
            metadata={"hnsw:space": "cosine"},
        )

    def ingest(self, repository_root: Path) -> dict[str, Any]:
        root = repository_root.resolve()
        ids: list[str] = []
        documents: list[str] = []
        embeddings: list[list[float]] = []
        metadatas: list[dict[str, Any]] = []
        indexed_files: set[str] = set()
        skipped_files = 0
        truncated = False

        for path in sorted(root.rglob("*")):
            if len(indexed_files) >= MAX_FILES or len(ids) >= MAX_CHUNKS:
                truncated = True
                break
            if not _is_indexable(path, root):
                continue
            if path.stat().st_size > MAX_FILE_BYTES:
                skipped_files += 1
                continue
            relative = path.relative_to(root).as_posix()
            lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
            if not lines:
                continue
            indexed_files.add(relative)
            for start in range(0, len(lines), CHUNK_LINES - CHUNK_OVERLAP_LINES):
                if len(ids) >= MAX_CHUNKS:
                    truncated = True
                    break
                end = min(len(lines), start + CHUNK_LINES)
                text = _redact_likely_secrets("\n".join(lines[start:end]))
                document = f"Repository path: {relative}\n{text}"
                ids.append(sha256(f"{relative}:{start + 1}:{end}".encode()).hexdigest())
                documents.append(document)
                embeddings.append(_embed(document))
                metadatas.append(
                    {
                        "path": relative,
                        "startLine": start + 1,
                        "endLine": end,
                    }
                )
                if end == len(lines):
                    break

        if ids:
            batch_size = min(500, self._client.get_max_batch_size())
            for start in range(0, len(ids), batch_size):
                end = start + batch_size
                self._collection.upsert(
                    ids=ids[start:end],
                    documents=documents[start:end],
                    embeddings=embeddings[start:end],
                    metadatas=metadatas[start:end],
                )
        return {
            "provider": "chroma",
            "embedding": "local-deterministic-hashing-v1",
            "filesIndexed": len(indexed_files),
            "chunksIndexed": len(ids),
            "skippedFiles": skipped_files,
            "truncated": truncated,
        }

    def query(self, query_text: str, *, limit: int = 8) -> list[dict[str, Any]]:
        count = self._collection.count()
        if count == 0:
            return []
        result = self._collection.query(
            query_embeddings=[_embed(query_text)],
            n_results=min(limit, count),
            include=["documents", "metadatas", "distances"],
        )
        documents = (result.get("documents") or [[]])[0]
        metadatas = (result.get("metadatas") or [[]])[0]
        distances = (result.get("distances") or [[]])[0]
        snippets: list[dict[str, Any]] = []
        for document, metadata, distance in zip(documents, metadatas, distances, strict=True):
            if document is None or metadata is None:
                continue
            snippets.append(
                {
                    "path": str(metadata["path"]),
                    "startLine": int(metadata["startLine"]),
                    "endLine": int(metadata["endLine"]),
                    "text": document,
                    "retrievalMethod": "chroma-vector",
                    "relevance": round(max(0.0, 1.0 - float(distance)), 6),
                }
            )
        return snippets

    def close(self) -> None:
        self._client.close()


def _is_indexable(path: Path, root: Path) -> bool:
    if not path.is_file() or path.suffix.lower() not in INDEXED_SUFFIXES:
        return False
    relative = path.relative_to(root)
    if path.name.lower() in EXCLUDED_NAMES:
        return False
    return not any(part.lower() in EXCLUDED_PARTS for part in relative.parts)


def _embed(value: str) -> list[float]:
    vector = [0.0] * EMBEDDING_DIMENSIONS
    for term in _terms(value):
        digest = sha256(term.encode()).digest()
        index = int.from_bytes(digest[:4], "big") % EMBEDDING_DIMENSIONS
        vector[index] += 1.0 if digest[4] % 2 == 0 else -1.0
    magnitude = math.sqrt(sum(item * item for item in vector))
    if magnitude == 0:
        vector[0] = 1.0
        return vector
    return [item / magnitude for item in vector]


def _terms(value: str) -> list[str]:
    expanded = re.sub(r"(?<=[a-z0-9])(?=[A-Z])", " ", value).lower()
    words = re.findall(r"[a-z0-9_]+", expanded)
    terms = list(words)
    for word in words:
        compact = word.replace("_", "")
        terms.extend(compact[index : index + 3] for index in range(max(0, len(compact) - 2)))
    return terms


def _redact_likely_secrets(value: str) -> str:
    pattern = re.compile(
        r"(?i)(password|passwd|api[_-]?key|secret|connectionstring|access[_-]?token)"
        r"(\s*[:=]\s*)([\"']?)[^\s,;\"']+\3"
    )
    return pattern.sub(r"\1\2[REDACTED]", value)
