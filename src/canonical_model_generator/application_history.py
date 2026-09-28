"""Local persistence for trusted Streamlit application profiles."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from canonical_model_generator.discovery_agent.model import DiscoveryModel

HISTORY_VERSION = "1.0"
RUN_ID_PATTERN = re.compile(r"^[a-f0-9]{32}$")


def save_application_record(root: Path, application_id: str, run: dict[str, Any]) -> None:
    """Persist one isolated application run and its derived artifacts locally."""
    if not RUN_ID_PATTERN.fullmatch(application_id):
        raise ValueError("Application ID must be a 32-character lowercase hex value")
    DiscoveryModel.model_validate_json(run["discovery_model"])
    target = root / application_id
    discovery_dir = target / "discovery"
    phase_two_dir = target / "phase-2"
    discovery_dir.mkdir(parents=True, exist_ok=True)
    phase_two_dir.mkdir(parents=True, exist_ok=True)

    (target / "discovery-model.json").write_bytes(run["discovery_model"])
    for label, content in run.get("discovery_artifacts", {}).items():
        filename = _safe_artifact_name(label, ".json")
        (discovery_dir / filename).write_bytes(content)
    repository = run.get("repository_archive")
    if repository is not None:
        (target / "repository.zip").write_bytes(repository)
    for filename, content in run.get("phase_2_artifacts", {}).items():
        safe_name = Path(filename).name
        if safe_name != filename:
            raise ValueError("Phase 2 artifact filename must not contain a path")
        (phase_two_dir / safe_name).write_bytes(content)

    manifest = {
        "version": HISTORY_VERSION,
        "applicationId": application_id,
        "profile": run["profile"],
        "projects": run.get("discovery_projects", []),
        "discoveryArtifacts": {
            label: _safe_artifact_name(label, ".json")
            for label in run.get("discovery_artifacts", {})
        },
        "phase2Artifacts": sorted(run.get("phase_2_artifacts", {})),
        "phase2Error": run.get("phase_2_error"),
        "ragStorePath": run.get("rag_store_path"),
        "ragManifest": run.get("rag_manifest"),
        "hasRepository": repository is not None,
    }
    temporary = target / "record.json.tmp"
    temporary.write_text(json.dumps(manifest, indent=2, sort_keys=True), encoding="utf-8")
    temporary.replace(target / "record.json")


def load_application_records(root: Path) -> dict[str, dict[str, Any]]:
    """Load valid local records; ignore incomplete or invalid directories."""
    records: dict[str, dict[str, Any]] = {}
    if not root.is_dir():
        return records
    for target in sorted(root.iterdir()):
        if not target.is_dir() or not RUN_ID_PATTERN.fullmatch(target.name):
            continue
        try:
            manifest = json.loads((target / "record.json").read_text(encoding="utf-8"))
            if manifest.get("version") != HISTORY_VERSION:
                continue
            discovery_model = (target / "discovery-model.json").read_bytes()
            DiscoveryModel.model_validate_json(discovery_model)
            discovery_artifacts = {
                label: (target / "discovery" / filename).read_bytes()
                for label, filename in manifest.get("discoveryArtifacts", {}).items()
            }
            phase_two_artifacts = {
                filename: (target / "phase-2" / filename).read_bytes()
                for filename in manifest.get("phase2Artifacts", [])
            }
            repository_path = target / "repository.zip"
            records[target.name] = {
                "profile": manifest["profile"],
                "discovery_artifacts": discovery_artifacts,
                "discovery_projects": manifest.get("projects", []),
                "discovery_model": discovery_model,
                "repository_archive": (
                    repository_path.read_bytes() if repository_path.is_file() else None
                ),
                "rag_store_path": manifest.get("ragStorePath"),
                "rag_manifest": manifest.get("ragManifest"),
                "phase_2_artifacts": phase_two_artifacts,
                "phase_2_error": manifest.get("phase2Error"),
            }
        except (KeyError, OSError, TypeError, ValueError, json.JSONDecodeError):
            continue
    return records


def _safe_artifact_name(label: str, suffix: str) -> str:
    normalized = re.sub(r"[^a-z0-9]+", "-", label.casefold()).strip("-")
    if not normalized:
        raise ValueError("Artifact label must contain letters or digits")
    return normalized + suffix
