"""Deterministic YAML and JSON config file discovery for the repository."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

import yaml

from canonical_model_generator.discovery_agent.model import (
    Diagnostic,
    DiscoveryModel,
    RunMetadata,
    RunStatus,
    Severity,
    SourceDescriptor,
    SourceKind,
    Summary,
    stable_id,
)

# Config file names scanned at any depth inside the repository.
_CONFIG_FILENAMES = frozenset(
    {
        "host.json",
        "local.settings.json",
        "local.settings.sample.json",
        "appsettings.json",
        "appsettings.Development.json",
        "appsettings.Production.json",
        "extensions.json",
        "function.json",
    }
)

_YAML_EXTENSIONS = frozenset({".yml", ".yaml"})

# Directory names that are never scanned.
_SKIP_DIRS = frozenset({"bin", "obj", ".git", "node_modules", ".github", ".vs", "packages"})


def discover_yaml_config(repository: Path, region: str, system: str) -> DiscoveryModel:
    """Scan *repository* for YAML/JSON config files and return a DiscoveryModel.

    The returned model contains only sources and parse-error diagnostics —
    no operations, entities, evidence, or lineage.  Evidence and lineage require
    subject_ids that reference model items (operations, entities, attributes);
    config files are not model items.  Sources are the useful contract-level
    signal: they record which config files exist in the repository.

    The model is merged into the primary Roslyn/OpenAPI model by the
    discovery workflow's reconcile step.
    """
    sources: list[SourceDescriptor] = []
    diagnostics: list[Diagnostic] = []

    for path in _iter_config_files(repository):
        relative = path.relative_to(repository).as_posix()
        try:
            sha = _sha256(path)
        except OSError as exc:
            diagnostics.append(
                Diagnostic(
                    id=stable_id("diagnostic", "yaml_config_read_error", relative),
                    severity=Severity.WARNING,
                    code="YAML001",
                    message=f"Could not read {relative}: {exc}",
                )
            )
            continue

        source_id = stable_id("source", "yaml_config", relative)
        sources.append(
            SourceDescriptor(id=source_id, kind=SourceKind.YAML_CONFIG, path=relative, sha256=sha)
        )

        # Validate that the file is parseable; record errors as warnings.
        try:
            _load(path)
        except Exception as exc:
            diagnostics.append(
                Diagnostic(
                    id=stable_id("diagnostic", "yaml_config_parse_error", relative),
                    severity=Severity.WARNING,
                    code="YAML002",
                    message=f"Could not parse {relative}: {exc}",
                )
            )

    run_id = stable_id("run", "yaml_config", region, system)
    return DiscoveryModel(
        run=RunMetadata(id=run_id, status=RunStatus.COMPLETE, tool_version="0.1.0"),
        region=region,
        system=system,
        sources=sorted(sources, key=lambda s: s.path),
        operations=[],
        entities=[],
        enums=[],
        validations=[],
        relationships=[],
        evidence=[],
        lineage=[],
        diagnostics=sorted(diagnostics, key=lambda d: d.id),
        summary=Summary(
            operation_count=0,
            entity_count=0,
            enum_count=0,
            relationship_count=0,
            diagnostic_count=len(diagnostics),
        ),
    )


def config_metadata(repository: Path) -> dict[str, Any]:
    """Return a plain dict with configuration observations for the repository.

    This is a separate, non-model function for callers that want richer config
    data (host.json version, app-setting keys, pipeline trigger info) without
    needing it in the DiscoveryModel contract.  Values are redacted: connection
    strings and credentials are never returned.
    """
    result: dict[str, Any] = {
        "configFiles": [],
        "functionsHostVersion": None,
        "functionsWorkerRuntime": None,
        "appSettingKeys": [],
        "extensionBundleId": None,
        "pipelineFiles": [],
    }

    for path in _iter_config_files(repository):
        relative = path.relative_to(repository).as_posix()
        result["configFiles"].append(relative)

        try:
            data = _load(path)
        except Exception:
            continue

        if not isinstance(data, dict):
            continue

        filename = path.name.lower()

        if filename == "host.json":
            result["functionsHostVersion"] = data.get("version")
            bundle = data.get("extensionBundle")
            if isinstance(bundle, dict):
                result["extensionBundleId"] = bundle.get("id")

        elif filename in {"local.settings.json", "local.settings.sample.json"}:
            values = data.get("Values")
            if isinstance(values, dict):
                # Keys only, never values — connection strings may be secrets.
                result["appSettingKeys"] = sorted(values.keys())
                runtime = values.get("FUNCTIONS_WORKER_RUNTIME")
                if runtime:
                    result["functionsWorkerRuntime"] = runtime

        elif path.suffix.lower() in _YAML_EXTENSIONS:
            if "jobs" in data or "stages" in data or "trigger" in data:
                result["pipelineFiles"].append(relative)

    return result


# ---------------------------------------------------------------------------
# Utilities
# ---------------------------------------------------------------------------


def _iter_config_files(repository: Path):
    """Yield config and YAML files under *repository*, skipping build dirs."""
    for path in sorted(repository.rglob("*")):
        if not path.is_file():
            continue
        if any(part in _SKIP_DIRS for part in path.relative_to(repository).parts):
            continue
        if path.name in _CONFIG_FILENAMES or path.suffix.lower() in _YAML_EXTENSIONS:
            yield path


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _load(path: Path) -> Any:
    text = path.read_text(encoding="utf-8")
    if path.suffix.lower() in _YAML_EXTENSIONS:
        return yaml.safe_load(text) or {}
    return json.loads(text)
