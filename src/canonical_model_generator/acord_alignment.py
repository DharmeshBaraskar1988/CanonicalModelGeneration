"""Deterministic ACORD alignment proposals and human-approved canonical artifacts."""

from __future__ import annotations

import json
import re
from copy import deepcopy
from difflib import SequenceMatcher
from hashlib import sha256
from pathlib import Path
from typing import Any

from canonical_model_generator.regional_review import build_regional_review

FULL_MATCH = "Full match"
PARTIAL_MATCH = "Partial match"
NOT_MATCHED = "Not matched"
USE_ACORD = "Use ACORD standard"
USE_BASELINE = "Use canonical baseline"
USE_GENERATED = "Use generated proposal"
MANUAL = "Manual canonical name"
MATCH_STATUSES = (FULL_MATCH, PARTIAL_MATCH, NOT_MATCHED)
ALIGNMENT_SELECTIONS = (USE_BASELINE, USE_ACORD, USE_GENERATED, MANUAL)


def build_regional_alignment_source(
    region: str,
    model_tree: list[dict[str, Any]],
    approved_review: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Return the approved regional view or a deterministic original-name projection."""
    if approved_review and approved_review.get("region") == region:
        return deepcopy(approved_review)
    source = build_regional_review(region, model_tree, {}, {})
    source["status"] = "Unapproved regional catalog"
    return source


def propose_acord_alignment(
    *,
    region: str,
    regional_source: dict[str, Any],
    regional_domain_tree: list[dict[str, Any]],
    regional_endpoints: list[dict[str, Any]],
    acord_model: dict[str, Any],
    acord_run_id: str,
    canonical_baseline: dict[str, Any] | None = None,
    baseline_version: int | None = None,
) -> dict[str, Any]:
    """Propose baseline-first matches with ACORD fallback for review."""
    acord_entities = acord_model.get("entities", [])
    entity_matches = [
        _entity_match(entity, acord_entities) for entity in regional_source.get("entities", [])
    ]
    acord_domains = _acord_domains(acord_model)
    domain_matches = [_domain_match(domain, acord_domains) for domain in regional_domain_tree]
    if canonical_baseline:
        entity_matches = _combine_match_lists(
            [
                _entity_match(entity, _baseline_entities(canonical_baseline))
                for entity in regional_source.get("entities", [])
            ],
            entity_matches,
            child_key="attributes",
        )
        domain_matches = _combine_match_lists(
            [
                _domain_match(domain, _baseline_domains(canonical_baseline))
                for domain in regional_domain_tree
            ],
            domain_matches,
            child_key="capabilities",
        )
    all_matches = [
        *entity_matches,
        *(field for entity in entity_matches for field in entity["attributes"]),
        *domain_matches,
        *(capability for domain in domain_matches for capability in domain["capabilities"]),
    ]
    return {
        "version": "2.0" if canonical_baseline else "1.0",
        "region": region,
        "regionalSourceStatus": regional_source.get("status", "Unknown"),
        "acordRunId": acord_run_id,
        "acordReference": deepcopy(acord_model.get("source", {})),
        "baselineCanonicalVersion": baseline_version,
        "baselineRegions": (_artifact_regions(canonical_baseline) if canonical_baseline else []),
        "canonicalBaseline": (
            {
                "canonicalModel": deepcopy(canonical_baseline.get("canonicalModel", {})),
                "canonicalEndpoints": deepcopy(canonical_baseline.get("canonicalEndpoints", [])),
                "alignmentMappings": deepcopy(canonical_baseline.get("alignmentMappings", [])),
                "regions": _artifact_regions(canonical_baseline),
            }
            if canonical_baseline
            else None
        ),
        "entities": entity_matches,
        "domains": domain_matches,
        "regionalEndpoints": deepcopy(regional_endpoints),
        "matchSummary": _match_summary(all_matches),
    }


def default_alignment_decisions(proposal: dict[str, Any]) -> dict[str, Any]:
    """Create review defaults without silently approving any proposal."""
    entities: dict[str, Any] = {}
    for entity in proposal["entities"]:
        entities[entity["regionalId"]] = {
            **_default_decision(entity),
            "approved": False,
            "attributes": {
                field["regionalId"]: {**_default_decision(field), "approved": False}
                for field in entity["attributes"]
            },
        }
    domains: dict[str, Any] = {}
    for domain in proposal["domains"]:
        domains[domain["regionalId"]] = {
            **_default_decision(domain),
            "approved": False,
            "capabilities": {
                capability["regionalId"]: {
                    **_default_decision(capability),
                    "approved": False,
                }
                for capability in domain["capabilities"]
            },
        }
    return {"entities": entities, "domains": domains}


def attach_generated_gap_proposal(
    proposal: dict[str, Any], regional_id: str, generated: dict[str, Any]
) -> dict[str, Any]:
    """Attach one bounded generated proposal to a true unresolved gap."""
    name = str(generated.get("name", "")).strip()
    description = str(generated.get("description", "")).strip()
    constraints = generated.get("constraints", {})
    if not name or not description:
        raise ValueError("Generated gap proposals require a name and description")
    if not isinstance(constraints, dict):
        raise ValueError("Generated gap constraints must be a JSON object")
    updated = deepcopy(proposal)
    match = _find_match(updated, regional_id)
    if match is None:
        raise ValueError(f"Unknown regional alignment item: {regional_id}")
    if match["status"] != NOT_MATCHED:
        raise ValueError("Generated proposals are limited to items still not matched")
    match["generatedProposal"] = {
        "name": name,
        "description": description,
        "type": str(generated.get("type") or match.get("regionalType") or "").strip(),
        "constraints": deepcopy(constraints),
        "rationale": str(generated.get("rationale", "")).strip(),
    }
    return updated


def validate_alignment_decisions(proposal: dict[str, Any], decisions: dict[str, Any]) -> list[str]:
    """Return every missing or invalid human-review input."""
    errors: list[str] = []
    for entity in proposal["entities"]:
        decision = decisions.get("entities", {}).get(entity["regionalId"], {})
        _validate_decision(entity, decision, f"Entity {entity['regionalName']}", errors)
        for field in entity["attributes"]:
            field_decision = decision.get("attributes", {}).get(field["regionalId"], {})
            _validate_decision(
                field,
                field_decision,
                f"Attribute {entity['regionalName']}.{field['regionalName']}",
                errors,
            )
    for domain in proposal["domains"]:
        decision = decisions.get("domains", {}).get(domain["regionalId"], {})
        _validate_decision(domain, decision, f"Domain {domain['regionalName']}", errors)
        for capability in domain["capabilities"]:
            capability_decision = decision.get("capabilities", {}).get(capability["regionalId"], {})
            _validate_decision(
                capability,
                capability_decision,
                f"Capability {domain['regionalName']}.{capability['regionalName']}",
                errors,
            )
    return errors


def approve_acord_alignment(proposal: dict[str, Any], decisions: dict[str, Any]) -> dict[str, Any]:
    """Build a canonical review artifact only when every proposed item is resolved."""
    errors = validate_alignment_decisions(proposal, decisions)
    if errors:
        raise ValueError("Alignment review is incomplete: " + "; ".join(errors[:10]))

    canonical_entities = []
    entity_names: dict[str, str] = {}
    endpoint_entities: dict[tuple[str, str, str], list[dict[str, str]]] = {}
    mappings = []
    for entity in proposal["entities"]:
        decision = decisions["entities"][entity["regionalId"]]
        canonical_name = _resolved_name(entity, decision)
        canonical_id = _stable_id("canonical-entity", proposal["region"], canonical_name)
        entity_names[entity["regionalId"]] = canonical_name
        attributes = []
        for field in entity["attributes"]:
            field_decision = decision["attributes"][field["regionalId"]]
            canonical_field_name = _resolved_name(field, field_decision)
            standard = _selected_candidate(field, field_decision)
            reviewed_field_status = _review_status(field, field_decision)
            reviewed_field_description = _review_description(field, field_decision)
            attributes.append(
                {
                    "id": _stable_id(
                        "canonical-attribute",
                        canonical_id,
                        canonical_field_name,
                        field["regionalType"],
                    ),
                    "name": canonical_field_name,
                    "description": reviewed_field_description,
                    "type": (
                        standard.get("type", field["regionalType"])
                        if standard
                        else field_decision.get("manualType") or field["regionalType"]
                    ),
                    "constraints": (
                        deepcopy(standard.get("constraints", {}))
                        if standard
                        else _manual_constraints(field_decision)
                    ),
                    "required": field.get("required", False),
                    "standard": field_decision["selection"],
                    "matchStatus": reviewed_field_status,
                    "proposedMatchStatus": field["status"],
                    "matchPercent": field["matchPercent"],
                    "reviewDescription": reviewed_field_description,
                    "reviewerReason": field_decision["reason"].strip(),
                }
            )
            mappings.append(
                {
                    "kind": "Attribute",
                    "regional": f"{entity['regionalName']}.{field['regionalName']}",
                    "baseline": _candidate_path(entity, field, "baselineCandidate"),
                    "acord": (
                        f"{(entity.get('acordCandidate') or {}).get('name', '')}."
                        f"{(field.get('acordCandidate') or {}).get('name', '')}"
                        if field.get("acordCandidate")
                        else ""
                    ),
                    "canonical": f"{canonical_name}.{canonical_field_name}",
                    "status": reviewed_field_status,
                    "proposedStatus": field["status"],
                    "matchPercent": field["matchPercent"],
                    "selection": field_decision["selection"],
                    "generated": _generated_name(field),
                    "description": reviewed_field_description,
                    "reason": field_decision["reason"].strip(),
                }
            )
        entity_standard = _selected_candidate(entity, decision)
        reviewed_entity_status = _review_status(entity, decision)
        reviewed_entity_description = _review_description(entity, decision)
        canonical_entities.append(
            {
                "id": canonical_id,
                "name": canonical_name,
                "description": reviewed_entity_description,
                "comments": deepcopy(entity_standard.get("comments", []))
                if entity_standard
                else [],
                "attributes": attributes,
                "sourceApis": entity.get("sourceApis", []),
                "standard": decision["selection"],
                "matchStatus": reviewed_entity_status,
                "proposedMatchStatus": entity["status"],
                "matchPercent": entity["matchPercent"],
                "reviewDescription": reviewed_entity_description,
                "reviewerReason": decision["reason"].strip(),
            }
        )
        mappings.append(
            {
                "kind": "Entity",
                "regional": entity["regionalName"],
                "baseline": (entity.get("baselineCandidate") or {}).get("name", ""),
                "acord": (entity.get("acordCandidate") or {}).get("name", ""),
                "canonical": canonical_name,
                "status": reviewed_entity_status,
                "proposedStatus": entity["status"],
                "matchPercent": entity["matchPercent"],
                "selection": decision["selection"],
                "generated": _generated_name(entity),
                "description": reviewed_entity_description,
                "reason": decision["reason"].strip(),
            }
        )
        for endpoint in entity.get("endpoints", []):
            key = (endpoint["API"], endpoint["Method"], endpoint["Route"])
            endpoint_entities.setdefault(key, []).append(
                {"entity": canonical_name, "usage": endpoint.get("Usage", "Contract")}
            )

    domain_names: dict[str, str] = {}
    capability_names: dict[tuple[str, str], str] = {}
    for domain in proposal["domains"]:
        decision = decisions["domains"][domain["regionalId"]]
        canonical_domain = _resolved_name(domain, decision)
        domain_names[domain["regionalName"]] = canonical_domain
        mappings.append(
            {
                "kind": "Domain",
                "regional": domain["regionalName"],
                "baseline": (domain.get("baselineCandidate") or {}).get("name", ""),
                "acord": (domain.get("acordCandidate") or {}).get("name", ""),
                "canonical": canonical_domain,
                "status": domain["status"],
                "matchPercent": domain["matchPercent"],
                "selection": decision["selection"],
                "generated": _generated_name(domain),
                "reason": decision["reason"].strip(),
            }
        )
        for capability in domain["capabilities"]:
            capability_decision = decision["capabilities"][capability["regionalId"]]
            canonical_capability = _resolved_name(capability, capability_decision)
            capability_names[(domain["regionalName"], capability["regionalName"])] = (
                canonical_capability
            )
            mappings.append(
                {
                    "kind": "Capability",
                    "regional": f"{domain['regionalName']}.{capability['regionalName']}",
                    "baseline": _candidate_path(domain, capability, "baselineCandidate"),
                    "acord": (capability.get("acordCandidate") or {}).get("name", ""),
                    "canonical": f"{canonical_domain}.{canonical_capability}",
                    "status": capability["status"],
                    "matchPercent": capability["matchPercent"],
                    "selection": capability_decision["selection"],
                    "generated": _generated_name(capability),
                    "reason": capability_decision["reason"].strip(),
                }
            )

    canonical_endpoints = []
    for endpoint in proposal["regionalEndpoints"]:
        key = (endpoint["API"], endpoint["Method"], endpoint["Route"])
        source_domain = endpoint["Domain"]
        source_capability = endpoint["Capability"]
        canonical_endpoints.append(
            {
                "api": endpoint["API"],
                "operation": endpoint["Endpoint"],
                "method": endpoint["Method"],
                "route": endpoint["Route"],
                "domain": domain_names.get(source_domain, source_domain),
                "capability": capability_names.get(
                    (source_domain, source_capability), source_capability
                ),
                "entities": sorted(
                    endpoint_entities.get(key, []), key=lambda item: (item["usage"], item["entity"])
                ),
                "description": endpoint.get("Description"),
            }
        )

    artifact = {
        "version": "2.0" if proposal.get("canonicalBaseline") else "1.0",
        "status": "Approved",
        "region": proposal["region"],
        "regionalSourceStatus": proposal["regionalSourceStatus"],
        "acordRunId": proposal["acordRunId"],
        "acordReference": proposal["acordReference"],
        "baselineCanonicalVersion": proposal.get("baselineCanonicalVersion"),
        "regions": sorted({*proposal.get("baselineRegions", []), proposal["region"]}),
        "matchSummary": proposal["matchSummary"],
        "summary": {
            "canonicalEntities": len(canonical_entities),
            "canonicalAttributes": sum(len(entity["attributes"]) for entity in canonical_entities),
            "canonicalEndpoints": len(canonical_endpoints),
            "canonicalDomains": len(domain_names),
            "canonicalCapabilities": len(capability_names),
        },
        "canonicalModel": {"entities": canonical_entities},
        "canonicalEndpoints": canonical_endpoints,
        "alignmentMappings": mappings,
    }
    if proposal.get("canonicalBaseline"):
        artifact = _merge_with_canonical_baseline(
            proposal["canonicalBaseline"], artifact, proposal, decisions
        )
    return artifact


def save_alignment_artifact(root: Path, alignment_id: str, artifact: dict[str, Any]) -> Path:
    if not re.fullmatch(r"[0-9a-f]{32}", alignment_id):
        raise ValueError("Alignment ID must be a UUID hex value")
    path = root.resolve() / alignment_id
    path.mkdir(parents=True, exist_ok=True)
    (path / "canonical-alignment.json").write_text(
        json.dumps(artifact, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    return path


def load_alignment_artifacts(root: Path) -> dict[str, dict[str, Any]]:
    loaded: dict[str, dict[str, Any]] = {}
    if not root.is_dir():
        return loaded
    for path in sorted(root.iterdir()):
        if not path.is_dir() or not re.fullmatch(r"[0-9a-f]{32}", path.name):
            continue
        try:
            artifact = json.loads((path / "canonical-alignment.json").read_text(encoding="utf-8"))
            if artifact.get("status") == "Approved":
                loaded[path.name] = artifact
        except (OSError, TypeError, ValueError, json.JSONDecodeError):
            continue
    return loaded


def delete_alignment_artifact(root: Path, alignment_id: str) -> bool:
    """Delete exactly one saved alignment artifact and no downstream versions."""
    if not re.fullmatch(r"[0-9a-f]{32}", alignment_id):
        raise ValueError("Alignment ID must be a UUID hex value")
    resolved_root = root.resolve()
    path = (resolved_root / alignment_id).resolve()
    try:
        path.relative_to(resolved_root)
    except ValueError as exc:
        raise ValueError("Alignment path is outside the configured history root") from exc
    if not path.exists():
        return False
    if not path.is_dir():
        raise OSError("Alignment record path is not a directory")
    expected = path / "canonical-alignment.json"
    children = list(path.iterdir())
    if children != [expected] and set(children) != {expected}:
        raise OSError("Alignment directory contains unexpected files and was not deleted")
    expected.unlink()
    path.rmdir()
    return True


def _entity_match(regional: dict[str, Any], acord_entities: list[dict[str, Any]]) -> dict[str, Any]:
    candidates = [_score_entity(regional, acord) for acord in acord_entities]
    best = (
        max(candidates, key=lambda item: (item["score"], item["candidate"]["name"]))
        if candidates
        else None
    )
    attributes = (
        best["attributes"]
        if best
        else [_unmatched_attribute(field) for field in regional.get("attributes", [])]
    )
    score = best["score"] if best else 0.0
    if best and score >= 85 and all(item["status"] == FULL_MATCH for item in attributes):
        status = FULL_MATCH
    elif best and (score >= 40 or any(item["status"] != NOT_MATCHED for item in attributes)):
        status = PARTIAL_MATCH
    else:
        status = NOT_MATCHED
    used = {field["acordCandidate"]["id"] for field in attributes if field.get("acordCandidate")}
    unmatched_acord = [
        item["name"]
        for item in (best["candidate"].get("attributes", []) if best else [])
        if item["id"] not in used
    ]
    unmatched_regional = [
        item["regionalName"] for item in attributes if item["status"] != FULL_MATCH
    ]
    return {
        "regionalId": regional["id"],
        "regionalName": regional["name"],
        "regionalDescription": regional.get("description"),
        "sourceApis": regional.get("apis", []),
        "endpoints": regional.get("endpoints", []),
        "acordCandidate": _public_entity(best["candidate"]) if best else None,
        "status": status,
        "matchPercent": round(score, 1),
        "attributes": attributes,
        "unmatchedDetails": {
            "regionalAttributes": unmatched_regional,
            "acordAttributes": unmatched_acord,
        },
    }


def _score_entity(regional: dict[str, Any], acord: dict[str, Any]) -> dict[str, Any]:
    regional_fields = regional.get("attributes", [])
    acord_fields = acord.get("attributes", [])
    scored_pairs = [
        _score_attribute(field, candidate)
        for field in regional_fields
        for candidate in acord_fields
    ]
    assignments: dict[str, dict[str, Any]] = {}
    used_candidates: set[str] = set()
    for scored in sorted(
        scored_pairs,
        key=lambda item: (
            -item["matchPercent"],
            item["regionalName"].casefold(),
            item["acordCandidate"]["name"].casefold(),
        ),
    ):
        regional_id = scored["regionalId"]
        candidate_id = scored["acordCandidate"]["id"]
        if regional_id not in assignments and candidate_id not in used_candidates:
            assignments[regional_id] = scored
            used_candidates.add(candidate_id)
    attributes = [
        assignments.get(field["id"], _unmatched_attribute(field)) for field in regional_fields
    ]
    name_score = _name_similarity(regional["name"], acord["name"])
    attribute_score = (
        sum(item["matchPercent"] for item in attributes) / len(attributes)
        if attributes
        else 100.0
        if not acord.get("attributes")
        else 0.0
    )
    description_score = _text_similarity(
        regional.get("description", ""), acord.get("description", "")
    )
    score = name_score * 0.5 + attribute_score * 0.4 + description_score * 0.1
    return {"candidate": acord, "score": score, "attributes": attributes}


def _score_attribute(regional: dict[str, Any], acord: dict[str, Any]) -> dict[str, Any]:
    name_score = _name_similarity(regional["name"], acord["name"])
    type_score = 100.0 if _compatible_types(regional.get("type"), acord.get("type")) else 0.0
    description_score = _text_similarity(
        regional.get("description", ""), acord.get("description", "")
    )
    score = name_score * 0.7 + type_score * 0.2 + description_score * 0.1
    status = _status(score, full=85, partial=50)
    return {
        "regionalId": regional["id"],
        "regionalName": regional["name"],
        "regionalDescription": regional.get("description"),
        "regionalType": regional.get("type", "unknown"),
        "required": regional.get("requiredInAllSources", False),
        "acordCandidate": _public_attribute(acord),
        "status": status,
        "matchPercent": round(score, 1),
    }


def _unmatched_attribute(regional: dict[str, Any]) -> dict[str, Any]:
    return {
        "regionalId": regional["id"],
        "regionalName": regional["name"],
        "regionalDescription": regional.get("description"),
        "regionalType": regional.get("type", "unknown"),
        "required": regional.get("requiredInAllSources", False),
        "acordCandidate": None,
        "status": NOT_MATCHED,
        "matchPercent": 0.0,
    }


def _domain_match(regional: dict[str, Any], acord_domains: list[dict[str, Any]]) -> dict[str, Any]:
    candidates = [_score_domain(regional, acord) for acord in acord_domains]
    best = (
        max(candidates, key=lambda item: (item["score"], item["candidate"]["name"]))
        if candidates
        else None
    )
    capabilities = (
        best["capabilities"]
        if best
        else [
            _unmatched_capability(item, domain_name=regional["name"])
            for item in regional.get("capabilities", [])
        ]
    )
    score = best["score"] if best else 0.0
    if best and score >= 85 and all(item["status"] == FULL_MATCH for item in capabilities):
        status = FULL_MATCH
    elif best and (score >= 40 or any(item["status"] != NOT_MATCHED for item in capabilities)):
        status = PARTIAL_MATCH
    else:
        status = NOT_MATCHED
    used = {item["acordCandidate"]["id"] for item in capabilities if item.get("acordCandidate")}
    return {
        "regionalId": _stable_id("regional-domain", regional["name"]),
        "regionalName": regional["name"],
        "acordCandidate": deepcopy(best["candidate"]) if best else None,
        "status": status,
        "matchPercent": round(score, 1),
        "capabilities": capabilities,
        "unmatchedDetails": {
            "regionalCapabilities": [
                item["regionalName"] for item in capabilities if item["status"] != FULL_MATCH
            ],
            "acordCapabilities": [
                item["name"]
                for item in (best["candidate"].get("capabilities", []) if best else [])
                if item["id"] not in used
            ],
        },
    }


def _score_domain(regional: dict[str, Any], acord: dict[str, Any]) -> dict[str, Any]:
    regional_capabilities = regional.get("capabilities", [])
    acord_capabilities = acord.get("capabilities", [])
    domain_name = regional["name"]
    scored_pairs = [
        _score_capability(capability, candidate, domain_name=domain_name)
        for capability in regional_capabilities
        for candidate in acord_capabilities
    ]
    assignments: dict[str, dict[str, Any]] = {}
    used_candidates: set[str] = set()
    for scored in sorted(
        scored_pairs,
        key=lambda item: (
            -item["matchPercent"],
            item["regionalName"].casefold(),
            item["acordCandidate"]["name"].casefold(),
        ),
    ):
        regional_id = scored["regionalId"]
        candidate_id = scored["acordCandidate"]["id"]
        if regional_id not in assignments and candidate_id not in used_candidates:
            assignments[regional_id] = scored
            used_candidates.add(candidate_id)
    capabilities = [
        assignments.get(
            _stable_id("regional-capability", domain_name, capability["name"]),
            _unmatched_capability(capability, domain_name=domain_name),
        )
        for capability in regional_capabilities
    ]
    name_score = _name_similarity(regional["name"], acord["name"])
    capability_score = (
        sum(item["matchPercent"] for item in capabilities) / len(capabilities)
        if capabilities
        else 100.0
        if not acord.get("capabilities")
        else 0.0
    )
    return {
        "candidate": acord,
        "score": name_score * 0.7 + capability_score * 0.3,
        "capabilities": capabilities,
    }


def _score_capability(
    regional: dict[str, Any], acord: dict[str, Any], *, domain_name: str
) -> dict[str, Any]:
    score = (
        _name_similarity(regional["name"], acord["name"]) * 0.8
        + _text_similarity(_regional_capability_text(regional), acord.get("description", "")) * 0.2
    )
    return {
        "regionalId": _stable_id("regional-capability", domain_name, regional["name"]),
        "regionalName": regional["name"],
        "acordCandidate": deepcopy(acord),
        "status": _status(score, full=85, partial=45),
        "matchPercent": round(score, 1),
    }


def _unmatched_capability(regional: dict[str, Any], *, domain_name: str) -> dict[str, Any]:
    return {
        "regionalId": _stable_id("regional-capability", domain_name, regional["name"]),
        "regionalName": regional["name"],
        "acordCandidate": None,
        "status": NOT_MATCHED,
        "matchPercent": 0.0,
    }


def _acord_domains(model: dict[str, Any]) -> list[dict[str, Any]]:
    grouped: dict[str, dict[str, Any]] = {}
    for endpoint in model.get("endpoints", []):
        tags = endpoint.get("tags") or [_route_domain(endpoint.get("route", ""))]
        capability_name = endpoint.get("summary") or endpoint.get("operationId") or "Unclassified"
        capability_id = _stable_id(
            "acord-capability", endpoint.get("method", ""), endpoint.get("route", "")
        )
        for tag in tags:
            domain = grouped.setdefault(
                str(tag),
                {
                    "id": _stable_id("acord-domain", str(tag)),
                    "name": str(tag),
                    "description": "",
                    "capabilities": [],
                },
            )
            domain["capabilities"].append(
                {
                    "id": capability_id,
                    "name": str(capability_name),
                    "operationId": endpoint.get("operationId"),
                    "description": " ".join(
                        part
                        for part in (
                            endpoint.get("summary"),
                            endpoint.get("description"),
                            endpoint.get("operationId"),
                        )
                        if part
                    ),
                    "method": endpoint.get("method"),
                    "route": endpoint.get("route"),
                }
            )
    for domain in grouped.values():
        domain["capabilities"] = sorted(
            _unique_by_id(domain["capabilities"]), key=lambda item: item["name"].casefold()
        )
        domain["description"] = " ".join(
            item["description"] for item in domain["capabilities"] if item["description"]
        )
    return sorted(grouped.values(), key=lambda item: item["name"].casefold())


def _baseline_entities(artifact: dict[str, Any]) -> list[dict[str, Any]]:
    return [
        {
            "id": entity["id"],
            "name": entity["name"],
            "description": entity.get("description"),
            "comments": deepcopy(entity.get("comments", [])),
            "attributes": [
                {
                    "id": attribute["id"],
                    "name": attribute["name"],
                    "description": attribute.get("description"),
                    "type": attribute.get("type", "unknown"),
                    "constraints": deepcopy(attribute.get("constraints", {})),
                }
                for attribute in entity.get("attributes", [])
            ],
        }
        for entity in artifact.get("canonicalModel", {}).get("entities", [])
    ]


def _baseline_domains(artifact: dict[str, Any]) -> list[dict[str, Any]]:
    grouped: dict[str, dict[str, Any]] = {}
    for endpoint in artifact.get("canonicalEndpoints", []):
        domain_name = str(endpoint.get("domain") or "Unclassified")
        capability_name = str(endpoint.get("capability") or "Unclassified")
        domain = grouped.setdefault(
            domain_name,
            {
                "id": _stable_id("canonical-domain", domain_name),
                "name": domain_name,
                "description": "",
                "capabilities": [],
            },
        )
        domain["capabilities"].append(
            {
                "id": _stable_id("canonical-capability", domain_name, capability_name),
                "name": capability_name,
                "description": endpoint.get("description") or "",
                "operationId": endpoint.get("operation"),
                "method": endpoint.get("method"),
                "route": endpoint.get("route"),
            }
        )
    for domain in grouped.values():
        domain["capabilities"] = sorted(
            _unique_by_id(domain["capabilities"]), key=lambda item: item["name"].casefold()
        )
        domain["description"] = " ".join(
            item["description"] for item in domain["capabilities"] if item["description"]
        )
    return sorted(grouped.values(), key=lambda item: item["name"].casefold())


def _combine_match_lists(
    baseline_matches: list[dict[str, Any]],
    acord_matches: list[dict[str, Any]],
    *,
    child_key: str,
) -> list[dict[str, Any]]:
    acord_by_id = {item["regionalId"]: item for item in acord_matches}
    combined = []
    for baseline in baseline_matches:
        acord = acord_by_id[baseline["regionalId"]]
        item = _combine_match(baseline, acord)
        baseline_children = {child["regionalId"]: child for child in baseline.get(child_key, [])}
        item[child_key] = [
            _combine_match(baseline_children[child["regionalId"]], child)
            for child in acord.get(child_key, [])
        ]
        combined.append(item)
    return combined


def _combine_match(baseline: dict[str, Any], acord: dict[str, Any]) -> dict[str, Any]:
    item = deepcopy(acord)
    item["baselineCandidate"] = deepcopy(baseline.get("acordCandidate"))
    item["baselineStatus"] = baseline["status"]
    item["baselineMatchPercent"] = baseline["matchPercent"]
    item["acordStatus"] = acord["status"]
    item["acordMatchPercent"] = acord["matchPercent"]
    if baseline["status"] == FULL_MATCH:
        selected = baseline
        source = "Canonical baseline"
    elif _status_rank(acord["status"]) > _status_rank(baseline["status"]):
        selected = acord
        source = "ACORD"
    elif baseline.get("acordCandidate"):
        selected = baseline
        source = "Canonical baseline"
    elif acord.get("acordCandidate"):
        selected = acord
        source = "ACORD"
    else:
        selected = acord
        source = "Unresolved"
    item["status"] = selected["status"]
    item["matchPercent"] = selected["matchPercent"]
    item["candidateSource"] = source
    item["unmatchedDetails"] = deepcopy(selected.get("unmatchedDetails", {}))
    return item


def _status_rank(status: str) -> int:
    return {NOT_MATCHED: 0, PARTIAL_MATCH: 1, FULL_MATCH: 2}[status]


def _artifact_regions(artifact: dict[str, Any] | None) -> list[str]:
    if not artifact:
        return []
    regions = artifact.get("regions")
    if isinstance(regions, list):
        return sorted({str(region) for region in regions if region})
    region = artifact.get("region")
    return [str(region)] if region else []


def _find_match(proposal: dict[str, Any], regional_id: str) -> dict[str, Any] | None:
    for entity in proposal.get("entities", []):
        if entity["regionalId"] == regional_id:
            return entity
        for attribute in entity.get("attributes", []):
            if attribute["regionalId"] == regional_id:
                return attribute
    for domain in proposal.get("domains", []):
        if domain["regionalId"] == regional_id:
            return domain
        for capability in domain.get("capabilities", []):
            if capability["regionalId"] == regional_id:
                return capability
    return None


def _candidate_path(parent: dict[str, Any], child: dict[str, Any], candidate_key: str) -> str:
    candidate = child.get(candidate_key) or {}
    if not candidate:
        return ""
    parent_candidate = parent.get(candidate_key) or {}
    parent_name = parent_candidate.get("name")
    return f"{parent_name}.{candidate['name']}" if parent_name else str(candidate["name"])


def _generated_name(match: dict[str, Any]) -> str:
    return str((match.get("generatedProposal") or {}).get("name", ""))


def _default_decision(match: dict[str, Any]) -> dict[str, str]:
    source = match.get("candidateSource")
    if match.get("status") == NOT_MATCHED and "baselineStatus" in match:
        selection = USE_GENERATED if match.get("generatedProposal") else MANUAL
    elif source == "Canonical baseline":
        selection = USE_BASELINE
    elif match.get("acordCandidate"):
        selection = USE_ACORD
    elif match.get("generatedProposal"):
        selection = USE_GENERATED
    else:
        selection = MANUAL
    selected_candidate = {
        USE_BASELINE: match.get("baselineCandidate"),
        USE_ACORD: match.get("acordCandidate"),
        USE_GENERATED: match.get("generatedProposal"),
    }.get(selection)
    return {
        "selection": selection,
        "reviewStatus": str(match.get("status") or NOT_MATCHED),
        "reviewDescription": str(
            (selected_candidate or {}).get("description") or match.get("regionalDescription") or ""
        ),
        "manualName": "",
        "manualDescription": str(match.get("regionalDescription") or ""),
        "manualType": str(match.get("regionalType") or ""),
        "manualConstraints": "{}",
        "reason": "",
    }


def _validate_decision(
    match: dict[str, Any], decision: dict[str, Any], label: str, errors: list[str]
) -> None:
    review_status = decision.get("reviewStatus", match["status"])
    if review_status not in MATCH_STATUSES:
        errors.append(f"{label} needs a valid review status")
    selection = decision.get("selection")
    if selection not in ALIGNMENT_SELECTIONS:
        errors.append(f"{label} needs a standard selection")
        return
    if selection == USE_BASELINE and not match.get("baselineCandidate"):
        errors.append(f"{label} has no canonical baseline candidate")
    if selection == USE_ACORD and not match.get("acordCandidate"):
        errors.append(f"{label} has no ACORD candidate; enter a manual canonical name")
    if selection == USE_GENERATED and not match.get("generatedProposal"):
        errors.append(f"{label} has no generated proposal")
    if selection == MANUAL and not str(decision.get("manualName", "")).strip():
        errors.append(f"{label} needs a manual canonical name")
    try:
        _manual_constraints(decision)
    except ValueError:
        errors.append(f"{label} manual constraints must be a JSON object")
    if (
        review_status != FULL_MATCH
        or review_status != match["status"]
        or selection in {MANUAL, USE_GENERATED}
    ) and not str(decision.get("reason", "")).strip():
        errors.append(f"{label} needs a reviewer reason")
    if "approved" in decision and decision.get("approved") is not True:
        errors.append(f"{label} needs explicit approval")


def _review_status(match: dict[str, Any], decision: dict[str, Any]) -> str:
    status = decision.get("reviewStatus", match["status"])
    return str(status) if status in MATCH_STATUSES else str(match["status"])


def _review_description(match: dict[str, Any], decision: dict[str, Any]) -> str:
    reviewed = str(decision.get("reviewDescription", "")).strip()
    if reviewed:
        return reviewed
    candidate = _selected_candidate(match, decision)
    return str(
        (candidate or {}).get("description")
        or decision.get("manualDescription")
        or match.get("regionalDescription")
        or ""
    ).strip()


def _resolved_name(match: dict[str, Any], decision: dict[str, Any]) -> str:
    candidate = _selected_candidate(match, decision)
    if candidate:
        return str(candidate["name"])
    return str(decision["manualName"]).strip()


def _selected_candidate(match: dict[str, Any], decision: dict[str, Any]) -> dict[str, Any] | None:
    selection = decision.get("selection")
    if selection == USE_BASELINE:
        return match.get("baselineCandidate")
    if selection == USE_ACORD:
        return match.get("acordCandidate")
    if selection == USE_GENERATED:
        return match.get("generatedProposal")
    return None


def _manual_constraints(decision: dict[str, Any]) -> dict[str, Any]:
    raw = decision.get("manualConstraints", "{}")
    if isinstance(raw, dict):
        return deepcopy(raw)
    if not str(raw).strip():
        return {}
    parsed = json.loads(str(raw))
    if not isinstance(parsed, dict):
        raise ValueError("Manual constraints must be a JSON object")
    return parsed


def _merge_with_canonical_baseline(
    baseline: dict[str, Any],
    regional_artifact: dict[str, Any],
    proposal: dict[str, Any],
    decisions: dict[str, Any],
) -> dict[str, Any]:
    """Merge one approved regional delta into an immutable canonical baseline copy."""
    del decisions  # Decisions are already materialized in regional_artifact.
    result = deepcopy(regional_artifact)
    baseline_regions = [str(item) for item in baseline.get("regions", [])]
    target_region = proposal["region"]
    entities = deepcopy(baseline.get("canonicalModel", {}).get("entities", []))
    by_name = {_comparison_key(item["name"]): item for item in entities}
    for entity in entities:
        entity["sourceRegions"] = sorted(set(entity.get("sourceRegions", baseline_regions)))
    for incoming in regional_artifact["canonicalModel"]["entities"]:
        existing = by_name.get(_comparison_key(incoming["name"]))
        incoming["sourceRegions"] = [target_region]
        if existing is None:
            entities.append(incoming)
            by_name[_comparison_key(incoming["name"])] = incoming
            continue
        existing["sourceRegions"] = sorted({*existing.get("sourceRegions", []), target_region})
        existing["sourceApis"] = sorted(
            {*existing.get("sourceApis", []), *incoming.get("sourceApis", [])}
        )
        existing_attributes = {
            _comparison_key(item["name"]): item for item in existing.get("attributes", [])
        }
        for attribute in incoming.get("attributes", []):
            if _comparison_key(attribute["name"]) not in existing_attributes:
                existing.setdefault("attributes", []).append(attribute)
        existing["attributes"] = sorted(
            existing.get("attributes", []), key=lambda item: item["name"].casefold()
        )
    result["canonicalModel"] = {
        "entities": sorted(entities, key=lambda item: item["name"].casefold())
    }

    endpoints = []
    seen_endpoints: set[tuple[str, str, str, str, str]] = set()
    baseline_region = baseline_regions[0] if baseline_regions else "Baseline"
    endpoint_sources = [
        (endpoint, baseline_region) for endpoint in deepcopy(baseline.get("canonicalEndpoints", []))
    ] + [
        (deepcopy(endpoint), target_region)
        for endpoint in regional_artifact.get("canonicalEndpoints", [])
    ]
    for endpoint, endpoint_region in endpoint_sources:
        endpoint.setdefault("region", endpoint_region)
        key = (
            str(endpoint.get("region")),
            str(endpoint.get("api")),
            str(endpoint.get("operation")),
            str(endpoint.get("method")),
            str(endpoint.get("route")),
        )
        if key not in seen_endpoints:
            endpoints.append(endpoint)
            seen_endpoints.add(key)
    result["canonicalEndpoints"] = endpoints

    mappings = []
    for mapping in deepcopy(baseline.get("alignmentMappings", [])):
        mapping.setdefault("region", baseline_region)
        mappings.append(mapping)
    for mapping in regional_artifact.get("alignmentMappings", []):
        mappings.append({**mapping, "region": target_region})
    result["alignmentMappings"] = mappings
    result["regions"] = sorted({*baseline_regions, target_region})
    result["summary"] = {
        "canonicalEntities": len(entities),
        "canonicalAttributes": sum(len(item.get("attributes", [])) for item in entities),
        "canonicalEndpoints": len(endpoints),
        "canonicalDomains": len({item.get("domain") for item in endpoints if item.get("domain")}),
        "canonicalCapabilities": len(
            {
                (item.get("domain"), item.get("capability"))
                for item in endpoints
                if item.get("domain") and item.get("capability")
            }
        ),
    }
    return result


def _match_summary(matches: list[dict[str, Any]]) -> dict[str, Any]:
    counts = {
        status: sum(item["status"] == status for item in matches) for status in MATCH_STATUSES
    }
    total = len(matches)
    weighted = counts[FULL_MATCH] + counts[PARTIAL_MATCH] * 0.5
    return {
        "total": total,
        "fullMatch": counts[FULL_MATCH],
        "partialMatch": counts[PARTIAL_MATCH],
        "notMatched": counts[NOT_MATCHED],
        "matchedPercent": round(weighted / total * 100, 1) if total else 0.0,
        "unmatchedPercent": round(counts[NOT_MATCHED] / total * 100, 1) if total else 0.0,
    }


def _public_entity(entity: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": entity["id"],
        "name": entity["name"],
        "description": entity.get("description"),
        "comments": deepcopy(entity.get("comments", [])),
        "attributes": [_public_attribute(item) for item in entity.get("attributes", [])],
    }


def _public_attribute(attribute: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": attribute["id"],
        "name": attribute["name"],
        "type": attribute.get("type", "unknown"),
        "description": attribute.get("description"),
        "constraints": deepcopy(attribute.get("constraints", {})),
    }


def _regional_capability_text(capability: dict[str, Any]) -> str:
    return " ".join(
        str(value)
        for api in capability.get("apis", [])
        for endpoint in api.get("endpoints", [])
        for value in (
            endpoint.get("Summary"),
            endpoint.get("Description"),
            endpoint.get("Business purpose"),
        )
        if value and value != "Awaiting API Analyzer"
    )


def _route_domain(route: str) -> str:
    segment = next((item for item in route.split("/") if item and not item.startswith("{")), "API")
    return re.sub(r"[-_]", " ", segment).strip().title() or "API"


def _name_similarity(left: str, right: str) -> float:
    compact_left = _comparison_key(left)
    compact_right = _comparison_key(right)
    if not compact_left or not compact_right:
        return 0.0
    sequence = SequenceMatcher(None, compact_left, compact_right).ratio()
    tokens_left = _tokens(left)
    tokens_right = _tokens(right)
    token_score = len(tokens_left & tokens_right) / len(tokens_left | tokens_right)
    return max(sequence, token_score) * 100


def _text_similarity(left: str | None, right: str | None) -> float:
    left_tokens = _tokens(left or "")
    right_tokens = _tokens(right or "")
    if not left_tokens or not right_tokens:
        return 0.0
    return len(left_tokens & right_tokens) / len(left_tokens | right_tokens) * 100


def _tokens(value: str) -> set[str]:
    split = re.sub(r"(?<=[a-z0-9])(?=[A-Z])", " ", value)
    return set(re.findall(r"[a-z0-9]+", f"{value} {split}".casefold()))


def _comparison_key(value: str) -> str:
    return re.sub(r"[^a-z0-9]", "", value.casefold())


def _compatible_types(left: str | None, right: str | None) -> bool:
    aliases = {
        "int": "integer",
        "int32": "integer",
        "int64": "integer",
        "long": "integer",
        "float": "number",
        "double": "number",
        "decimal": "number",
        "uuid": "string",
        "guid": "string",
        "datetime": "string",
        "date-time": "string",
    }

    def normalize(value: str | None) -> str:
        text = (value or "unknown").casefold().replace("?", "")
        text = re.sub(r"^(list|array)\[|\]$", "", text)
        return aliases.get(text, text)

    return normalize(left) == normalize(right)


def _status(score: float, *, full: float, partial: float) -> str:
    if score >= full:
        return FULL_MATCH
    if score >= partial:
        return PARTIAL_MATCH
    return NOT_MATCHED


def _stable_id(kind: str, *parts: str) -> str:
    digest = sha256("\x1f".join((kind, *parts)).encode()).hexdigest()[:20]
    return f"{kind}-{digest}"


def _unique_by_id(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return list({item["id"]: item for item in items}.values())
