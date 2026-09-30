"""Sequential LangGraph orchestration for deterministic discovery."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, TypedDict

from langgraph.graph import END, START, StateGraph

from canonical_model_generator.discovery_agent.artifacts import generate_artifacts
from canonical_model_generator.discovery_agent.model import DiscoveryModel, Summary
from canonical_model_generator.discovery_agent.openapi import discover_openapi
from canonical_model_generator.discovery_agent.reconcile import reconcile
from canonical_model_generator.discovery_agent.roslyn import extract_roslyn
from canonical_model_generator.discovery_agent.yaml_config import discover_yaml_config


class DiscoveryState(TypedDict, total=False):
    region: str
    system: str
    repository: str
    project: str
    openapi: str
    output: str
    roslyn_model: DiscoveryModel
    openapi_model: DiscoveryModel
    yaml_model: DiscoveryModel
    model: DiscoveryModel
    artifacts: dict[str, str]
    errors: list[str]
    events: list[dict[str, Any]]


def build_graph():
    builder = StateGraph(DiscoveryState)
    builder.add_node("validate_inputs", _validate_inputs)
    builder.add_node("yaml_config", _yaml_config)
    builder.add_node("roslyn", _roslyn)
    builder.add_node("openapi", _openapi)
    builder.add_node("reconcile", _reconcile)
    builder.add_node("validate_model", _validate_model)
    builder.add_node("generate_artifacts", _generate_artifacts)
    builder.add_edge(START, "validate_inputs")
    builder.add_edge("validate_inputs", "yaml_config")
    builder.add_edge("yaml_config", "roslyn")
    builder.add_edge("roslyn", "openapi")
    builder.add_edge("openapi", "reconcile")
    builder.add_edge("reconcile", "validate_model")
    builder.add_edge("validate_model", "generate_artifacts")
    builder.add_edge("generate_artifacts", END)
    return builder.compile()


def run_discovery(
    *,
    region: str,
    system: str,
    output: Path,
    repository: Path | None = None,
    project: Path | None = None,
    openapi: Path | None = None,
) -> DiscoveryState:
    return build_graph().invoke(
        {
            "region": region,
            "system": system,
            "repository": str(repository) if repository else "",
            "project": str(project) if project else "",
            "openapi": str(openapi) if openapi else "",
            "output": str(output),
            "errors": [],
            "events": [],
        }
    )


def _unique_by_id(items: list[Any]) -> list[Any]:
    return list({item.id: item for item in reversed(items)}.values())[::-1]


def _validate_inputs(state: DiscoveryState) -> DiscoveryState:
    errors = list(state.get("errors", []))
    repository = Path(state["repository"]).resolve() if state["repository"] else None
    if not repository or not state["project"]:
        errors.append("A repository boundary and project are required; OpenAPI is optional")
    if repository and not repository.is_dir():
        errors.append("Repository directory does not exist")
    for label, value in (("Project", state["project"]), ("OpenAPI", state["openapi"])):
        if not value:
            continue
        path = Path(value).resolve()
        if not path.is_file():
            errors.append(f"{label} file does not exist")
        try:
            if repository:
                path.relative_to(repository)
        except ValueError:
            errors.append(f"{label} file is outside the repository boundary")
    if not state["region"].strip() or not state["system"].strip():
        errors.append("Region and system are required")
    return _event(state, "validate_inputs", "error" if errors else "ok", errors=errors)


def _yaml_config(state: DiscoveryState) -> DiscoveryState:
    if state.get("errors") or not state.get("repository"):
        return _event(state, "yaml_config", "skipped")
    try:
        yaml_model = discover_yaml_config(
            Path(state["repository"]), state["region"], state["system"]
        )
        return _event(state, "yaml_config", "ok", yaml_model=yaml_model)
    except Exception as exc:
        # YAML config is supplementary — log the error but do not block the workflow.
        return _event(state, "yaml_config", "error", errors=[*state.get("errors", []), str(exc)])


def _roslyn(state: DiscoveryState) -> DiscoveryState:
    if state.get("errors") or not state["project"]:
        return _event(state, "roslyn", "skipped")
    try:
        model = extract_roslyn(
            Path(state["project"]), Path(state["repository"]), state["region"], state["system"]
        )
        return _event(state, "roslyn", "ok", roslyn_model=model)
    except Exception as exc:  # graph boundary converts failures to structured state
        return _event(state, "roslyn", "error", errors=[*state["errors"], str(exc)])


def _openapi(state: DiscoveryState) -> DiscoveryState:
    if state.get("errors") or not state["openapi"]:
        return _event(state, "openapi", "skipped")
    try:
        model = discover_openapi(
            Path(state["openapi"]),
            state["region"],
            state["system"],
            Path(state["repository"]),
        )
        return _event(state, "openapi", "ok", openapi_model=model)
    except Exception as exc:
        return _event(state, "openapi", "error", errors=[*state["errors"], str(exc)])


def _reconcile(state: DiscoveryState) -> DiscoveryState:
    if state.get("errors"):
        return _event(state, "reconcile", "skipped")
    if "roslyn_model" in state and "openapi_model" in state:
        model = reconcile(state["roslyn_model"], state["openapi_model"])
    else:
        model = state["roslyn_model"]
    if state.get("yaml_model") is not None:
        model = _merge_yaml_into_model(model, state["yaml_model"])
    return _event(state, "reconcile", "ok", model=model)


def _merge_yaml_into_model(model: DiscoveryModel, yaml_model: DiscoveryModel) -> DiscoveryModel:
    """Merge YAML config sources and diagnostics into *model*.

    Evidence and lineage from the YAML config are intentionally excluded: the model
    validator requires evidence subject_ids to reference operations, entities, or
    attributes, but YAML config evidence references source descriptors.  Sources and
    parse-error diagnostics are the useful contract-level signals that survive the
    validator.
    """
    merged = model.model_copy(deep=True)
    merged.sources = sorted(
        _unique_by_id([*model.sources, *yaml_model.sources]),
        key=lambda s: s.path,
    )
    merged.diagnostics = sorted(
        _unique_by_id([*model.diagnostics, *yaml_model.diagnostics]),
        key=lambda d: d.id,
    )
    merged.summary = Summary(
        operation_count=len(merged.operations),
        entity_count=len(merged.entities),
        enum_count=len(merged.enums),
        relationship_count=len(merged.relationships),
        diagnostic_count=len(merged.diagnostics),
    )
    return merged


def _validate_model(state: DiscoveryState) -> DiscoveryState:
    if state.get("errors"):
        return _event(state, "validate_model", "skipped")
    model = DiscoveryModel.model_validate_json(state["model"].model_dump_json(by_alias=True))
    return _event(state, "validate_model", "ok", model=model)


def _generate_artifacts(state: DiscoveryState) -> DiscoveryState:
    if state.get("errors"):
        return _event(state, "generate_artifacts", "skipped")
    artifacts = generate_artifacts(state["model"], Path(state["output"]))
    return _event(state, "generate_artifacts", "ok", artifacts=artifacts)


def _event(state: DiscoveryState, node: str, status: str, **updates: Any) -> DiscoveryState:
    event = {"node": node, "status": status}
    return {**updates, "events": [*state.get("events", []), event]}


def event_lines(state: DiscoveryState) -> list[str]:
    return [json.dumps(item, sort_keys=True) for item in state.get("events", [])]
