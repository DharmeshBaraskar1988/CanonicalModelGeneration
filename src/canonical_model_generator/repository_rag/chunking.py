"""Bounded Roslyn syntax hierarchy and source-preserving code chunks."""

from __future__ import annotations

import json
import os
import re
import subprocess
from hashlib import sha256
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any

MAX_FILES = 5000
MAX_FILE_BYTES = 1_000_000
MAX_TOTAL_BYTES = 30_000_000
MAX_CHUNKS = 20_000
CHUNK_CHARACTERS = 1800
EXCLUDED_PARTS = {
    ".git",
    ".vs",
    ".venv",
    ".tmp",
    ".rag",
    ".pytest_cache",
    ".ruff_cache",
    "__pycache__",
    "bin",
    "obj",
    "node_modules",
    "packages",
}
SUFFIXES = {".cs", ".cshtml", ".razor", ".csproj", ".json", ".yaml", ".yml", ".config"}


def digest(value: str) -> str:
    return sha256(value.encode("utf-8")).hexdigest()


def redact(value: str) -> str:
    # Keep line numbers stable, remove whole assignment lines including quoted values with spaces.
    value = re.sub(
        r"-----BEGIN [^-]*PRIVATE KEY-----[\s\S]*?-----END [^-]*PRIVATE KEY-----",
        lambda match: "[REDACTED PRIVATE KEY]" + "\n" * match.group().count("\n"),
        value,
    )
    value = re.sub(r"(?i)\bsk-[a-z0-9_-]{12,}", "[REDACTED]", value)
    return "\n".join(
        "// [REDACTED secret-bearing line]"
        if re.search(
            r"(?i)(password|passwd|api[_-]?key|secret|connectionstrings?|access[_-]?token)"
            r"[\"']?\s*[:=]",
            line,
        )
        else line
        for line in value.split("\n")
    )


def read_sources(root: Path) -> tuple[list[dict[str, str]], list[str]]:
    root = root.resolve(strict=True)
    files: list[dict[str, str]] = []
    gaps: list[str] = []
    total = 0
    for directory, directories, names in os.walk(root, followlinks=False):
        directories[:] = sorted(
            name
            for name in directories
            if name.lower() not in EXCLUDED_PARTS
            and not (Path(directory) / name).is_symlink()
            and (Path(directory) / name).resolve().is_relative_to(root)
        )
        for name in sorted(names):
            path = Path(directory) / name
            if path.suffix.lower() not in SUFFIXES or name.lower() == "secrets.json":
                continue
            relative = path.relative_to(root).as_posix()
            if path.is_symlink() or not path.resolve().is_relative_to(root):
                gaps.append(f"Excluded linked source: {relative}")
                continue
            if name.lower().endswith((".g.cs", ".generated.cs", ".designer.cs")):
                continue
            if len(files) >= MAX_FILES or total >= MAX_TOTAL_BYTES:
                gaps.append("Repository file/total-byte limit reached")
                return files, gaps
            try:
                with path.open("rb") as source:
                    raw = source.read(min(MAX_FILE_BYTES, MAX_TOTAL_BYTES - total) + 1)
                if len(raw) > min(MAX_FILE_BYTES, MAX_TOTAL_BYTES - total):
                    gaps.append(f"File exceeds byte budget: {relative}")
                    continue
                total += len(raw)
                files.append(
                    {
                        "path": relative,
                        "text": redact(raw.decode("utf-8-sig")),
                        "sha256": sha256(raw).hexdigest(),
                    }
                )
            except (OSError, UnicodeError):
                gaps.append(f"Unreadable source: {relative}")
    return files, gaps


def roslyn_hierarchy(files: list[dict[str, str]]) -> list[dict[str, Any]]:
    sources = [
        {"path": item["path"], "text": item["text"]}
        for item in files
        if item["path"].endswith(".cs")
    ]
    if not sources:
        return []
    sidecar = Path(__file__).resolve().parents[3] / "dotnet/src/CanonicalModel.Discovery"
    with TemporaryDirectory(prefix="canonical-code-syntax-") as temporary:
        request, response = Path(temporary) / "input.json", Path(temporary) / "output.json"
        request.write_text(json.dumps(sources), encoding="utf-8")
        result = subprocess.run(
            [
                "dotnet",
                "run",
                "--project",
                str(sidecar),
                "--no-build",
                "--",
                "--chunk-input",
                str(request),
                "--output",
                str(response),
            ],
            capture_output=True,
            text=True,
            timeout=120,
            check=False,
        )
        if result.returncode or not response.exists():
            raise RuntimeError(
                "Roslyn code chunker failed. Build CanonicalModelGenerator.sln first."
            )
        return json.loads(response.read_text(encoding="utf-8"))


def build_chunks(files: list[dict[str, str]]) -> tuple[list[dict], list[dict], list[str]]:
    hierarchy = {item["path"]: item for item in roslyn_hierarchy(files)}
    chunks: list[dict] = []
    edges: list[dict] = []
    gaps: list[str] = []
    for source in files:
        path, text = source["path"], source["text"]
        lines = text.splitlines() or [""]
        file_id = digest(f"file:{path}:{source['sha256']}")
        entry = hierarchy.get(path, {})
        if entry.get("hasSyntaxErrors"):
            gaps.append(f"Syntax errors or redacted code in {path}; hierarchy may be partial")
        nodes = entry.get("nodes", [])
        ids = {node["key"]: digest(f"{file_id}:{node['key']}:{node['symbol']}") for node in nodes}
        definitions = [
            {
                "id": file_id,
                "kind": "file",
                "symbol": path,
                "name": path,
                "startLine": 1,
                "endLine": len(lines),
                "parentId": None,
                "references": [],
            },
            *[
                {**node, "id": ids[node["key"]], "parentId": ids.get(node["parentKey"], file_id)}
                for node in nodes
            ],
        ]
        for node in definitions:
            content = "\n".join(lines[node["startLine"] - 1 : node["endLine"]])
            chunk = {
                key: node[key]
                for key in ("id", "kind", "symbol", "name", "startLine", "endLine", "parentId")
            }
            chunk.update(
                path=path,
                sha256=source["sha256"],
                text=content[:CHUNK_CHARACTERS],
                truncated=len(content) > CHUNK_CHARACTERS,
                references=node["references"],
                subjectIds=[],
            )
            chunks.append(chunk)
            if chunk["parentId"]:
                edges.append(
                    {
                        "source": chunk["parentId"],
                        "target": chunk["id"],
                        "kind": "CONTAINS",
                        "resolution": "syntax",
                    }
                )
            # Member/file windows preserve the complete body while parents remain bounded previews.
            # Files also cover top-level statements and using/DI declarations outside named members.
            if len(content) > CHUNK_CHARACTERS:
                start_line, buffer = node["startLine"], ""
                buffer_end = start_line
                window_index = 0
                for line_number, line in enumerate(content.splitlines(), node["startLine"]):
                    pieces = [
                        line[i : i + CHUNK_CHARACTERS]
                        for i in range(0, max(1, len(line)), CHUNK_CHARACTERS)
                    ]
                    for piece in pieces:
                        if buffer and len(buffer) + len(piece) + 1 > CHUNK_CHARACTERS:
                            _window(
                                chunks, edges, chunk, buffer, start_line, buffer_end, window_index
                            )
                            window_index += 1
                            buffer, start_line = "", line_number
                        buffer += ("\n" if buffer else "") + piece
                        buffer_end = line_number
                if buffer:
                    _window(chunks, edges, chunk, buffer, start_line, node["endLine"], window_index)
            if len(chunks) > MAX_CHUNKS:
                raise ValueError("Repository exceeds the 20,000 code-chunk limit; narrow the input")
    by_name: dict[str, list[str]] = {}
    for chunk in chunks:
        if chunk["kind"] not in {"file", "window"}:
            by_name.setdefault(chunk["name"], []).append(chunk["id"])
    for chunk in chunks:
        chunk["unresolvedReferences"] = []
        for reference in chunk.pop("references", []):
            candidates = [
                target for target in by_name.get(reference["name"], []) if target != chunk["id"]
            ]
            if not candidates:
                chunk["unresolvedReferences"].append(reference)
            for target in candidates[:20]:
                edges.append(
                    {
                        "source": chunk["id"],
                        "target": target,
                        "kind": reference["kind"],
                        "resolution": "candidate",
                    }
                )
            if len(candidates) > 20:
                gaps.append(f"Reference candidate limit: {chunk['symbol']} -> {reference['name']}")
    return chunks, sorted(edges, key=lambda e: (e["source"], e["kind"], e["target"])), gaps


def _window(
    chunks: list, edges: list, parent: dict, text: str, start: int, end: int, index: int
) -> None:
    identity = digest(f"{parent['id']}:window:{index}:{start}:{end}:{text}")
    chunks.append(
        {
            **parent,
            "id": identity,
            "parentId": parent["id"],
            "kind": "window",
            "text": text,
            "startLine": start,
            "endLine": end,
            "windowIndex": index,
            "truncated": False,
            "references": [],
            "subjectIds": [],
        }
    )
    edges.append(
        {"source": parent["id"], "target": identity, "kind": "CONTAINS", "resolution": "syntax"}
    )
