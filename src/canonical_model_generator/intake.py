"""Safe, deterministic intake inspection for uploaded repository archives."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from hashlib import sha256
from io import BytesIO
from pathlib import PurePosixPath
from typing import Any
from zipfile import BadZipFile, ZipFile, ZipInfo

import yaml

MAX_ARCHIVE_BYTES = 100 * 1024 * 1024
MAX_ENTRIES = 20_000
MAX_UNCOMPRESSED_BYTES = 500 * 1024 * 1024
OPENAPI_NAMES = ("openapi", "swagger")
OPENAPI_SUFFIXES = (".json", ".yaml", ".yml")


class IntakeError(ValueError):
    """Raised when an uploaded input is unsafe or malformed."""


@dataclass(frozen=True)
class RepositoryInventory:
    archive_sha256: str
    file_count: int
    uncompressed_bytes: int
    solutions: tuple[str, ...]
    projects: tuple[str, ...]
    controllers: tuple[str, ...]
    openapi_candidates: tuple[str, ...]

    @property
    def ready_for_discovery(self) -> bool:
        return bool(self.projects and self.controllers)

    def to_dict(self) -> dict[str, Any]:
        result = asdict(self)
        result["ready_for_discovery"] = self.ready_for_discovery
        return result


def _normalized_member_name(info: ZipInfo) -> str:
    raw_name = info.filename.replace("\\", "/")
    path = PurePosixPath(raw_name)
    if path.is_absolute() or ".." in path.parts:
        raise IntakeError(f"Unsafe archive path: {raw_name}")
    return path.as_posix()


def inspect_repository_zip(archive: bytes) -> RepositoryInventory:
    """Inspect a ZIP without extracting or executing repository content."""
    if not archive:
        raise IntakeError("The repository ZIP is empty.")
    if len(archive) > MAX_ARCHIVE_BYTES:
        raise IntakeError("The repository ZIP exceeds the 100 MB intake limit.")

    try:
        with ZipFile(BytesIO(archive)) as zip_file:
            members = zip_file.infolist()
            if len(members) > MAX_ENTRIES:
                raise IntakeError("The repository ZIP contains too many entries.")
            if any(member.flag_bits & 0x1 for member in members):
                raise IntakeError("Encrypted ZIP entries are not supported.")

            total_size = sum(member.file_size for member in members)
            if total_size > MAX_UNCOMPRESSED_BYTES:
                raise IntakeError("The repository ZIP expands beyond the 500 MB limit.")

            names = sorted(
                _normalized_member_name(member) for member in members if not member.is_dir()
            )
    except BadZipFile as exc:
        raise IntakeError("The uploaded repository is not a valid ZIP file.") from exc

    lowered = {name: name.lower() for name in names}
    solutions = tuple(name for name in names if lowered[name].endswith(".sln"))
    projects = tuple(name for name in names if lowered[name].endswith(".csproj"))
    controllers = tuple(
        name
        for name in names
        if lowered[name].endswith("controller.cs")
        and "/bin/" not in f"/{lowered[name]}"
        and "/obj/" not in f"/{lowered[name]}"
    )
    openapi_candidates = tuple(
        name
        for name in names
        if lowered[name].endswith(OPENAPI_SUFFIXES)
        and any(marker in PurePosixPath(lowered[name]).name for marker in OPENAPI_NAMES)
    )

    return RepositoryInventory(
        archive_sha256=sha256(archive).hexdigest(),
        file_count=len(names),
        uncompressed_bytes=total_size,
        solutions=solutions,
        projects=projects,
        controllers=controllers,
        openapi_candidates=openapi_candidates,
    )


def validate_openapi(document: bytes, filename: str) -> dict[str, Any]:
    """Parse an uploaded OpenAPI document and return bounded summary metadata."""
    if not document:
        raise IntakeError("The OpenAPI document is empty.")
    if len(document) > 10 * 1024 * 1024:
        raise IntakeError("The OpenAPI document exceeds the 10 MB limit.")

    try:
        text = document.decode("utf-8")
        parsed = json.loads(text) if filename.lower().endswith(".json") else yaml.safe_load(text)
    except (UnicodeDecodeError, json.JSONDecodeError, yaml.YAMLError) as exc:
        raise IntakeError("The OpenAPI document is not valid UTF-8 JSON or YAML.") from exc

    if not isinstance(parsed, dict) or not isinstance(parsed.get("openapi"), str):
        raise IntakeError("The document does not declare an OpenAPI version.")
    paths = parsed.get("paths", {})
    schemas = parsed.get("components", {}).get("schemas", {})
    if not isinstance(paths, dict) or not isinstance(schemas, dict):
        raise IntakeError("OpenAPI paths and component schemas must be objects.")

    return {
        "filename": filename,
        "sha256": sha256(document).hexdigest(),
        "openapi_version": parsed["openapi"],
        "path_count": len(paths),
        "schema_count": len(schemas),
    }


def build_intake_manifest(
    *,
    region: str,
    system: str,
    archive_name: str,
    inventory: RepositoryInventory,
    openapi: dict[str, Any] | None,
) -> dict[str, Any]:
    """Create stable intake output without timestamps or environment-specific paths."""
    return {
        "manifestVersion": "1.0",
        "objective": "Deterministic discovery of one regional .NET Quote API",
        "region": region.strip(),
        "system": system.strip(),
        "repository": {"filename": archive_name, **inventory.to_dict()},
        "openapi": openapi,
        "status": "ready" if inventory.ready_for_discovery else "needs-input",
        "nextStage": "DiscoveryModel v1 contract (M1)",
    }
