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
MANUAL = "Manual canonical name"
MATCH_STATUSES = (FULL_MATCH, PARTIAL_MATCH, NOT_MATCHED)


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
) -> dict[str, Any]:
    """Propose deterministic entity/field and domain/capability matches for review."""
    acord_entities = acord_model.get("entities", [])
    entity_matches = [
        _entity_match(entity, acord_entities) for entity in regional_source.get("entities", [])
    ]
    acord_domains = _acord_domains(acord_model)
    domain_matches = [_domain_match(domain, acord_domains) for domain in regional_domain_tree]
    all_matches = [
        *entity_matches,
        *(field for entity in entity_matches for field in entity["attributes"]),
        *domain_matches,
        *(capability for domain in domain_matches for capability in domain["capabilities"]),
    ]
    return {
        "version": "1.0",
        "region": region,
        "regionalSourceStatus": regional_source.get("status", "Unknown"),
        "acordRunId": acord_run_id,
        "acordReference": deepcopy(acord_model.get("source", {})),
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
            "attributes": {
                field["regionalId"]: _default_decision(field) for field in entity["attributes"]
            },
        }
    domains: dict[str, Any] = {}
    for domain in proposal["domains"]:
        domains[domain["regionalId"]] = {
            **_default_decision(domain),
            "capabilities": {
                capability["regionalId"]: _default_decision(capability)
                for capability in domain["capabilities"]
            },
        }
    return {"entities": entities, "domains": domains}


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
            standard = (
                field.get("acordCandidate") if field_decision["selection"] == USE_ACORD else None
            )
            attributes.append(
                {
                    "id": _stable_id(
                        "canonical-attribute",
                        canonical_id,
                        canonical_field_name,
                        field["regionalType"],
                    ),
                    "name": canonical_field_name,
                    "description": (
                        standard.get("description")
                        if standard and standard.get("description")
                        else field.get("regionalDescription")
                    ),
                    "type": standard.get("type", field["regionalType"])
                    if standard
                    else field["regionalType"],
                    "constraints": deepcopy(standard.get("constraints", {})) if standard else {},
                    "required": field.get("required", False),
                    "standard": field_decision["selection"],
                    "matchStatus": field["status"],
                    "matchPercent": field["matchPercent"],
                    "reviewerReason": field_decision["reason"].strip(),
                }
            )
            mappings.append(
                {
                    "kind": "Attribute",
                    "regional": f"{entity['regionalName']}.{field['regionalName']}",
                    "acord": (
                        f"{entity.get('acordCandidate', {}).get('name', '')}."
                        f"{field.get('acordCandidate', {}).get('name', '')}"
                        if field.get("acordCandidate")
                        else ""
                    ),
                    "canonical": f"{canonical_name}.{canonical_field_name}",
                    "status": field["status"],
                    "matchPercent": field["matchPercent"],
                    "selection": field_decision["selection"],
                    "reason": field_decision["reason"].strip(),
                }
            )
        entity_standard = (
            entity.get("acordCandidate") if decision["selection"] == USE_ACORD else None
        )
        canonical_entities.append(
            {
                "id": canonical_id,
                "name": canonical_name,
                "description": (
                    entity_standard.get("description")
                    if entity_standard and entity_standard.get("description")
                    else entity.get("regionalDescription")
                ),
                "comments": deepcopy(entity_standard.get("comments", []))
                if entity_standard
                else [],
                "attributes": attributes,
                "sourceApis": entity.get("sourceApis", []),
                "standard": decision["selection"],
                "matchStatus": entity["status"],
                "matchPercent": entity["matchPercent"],
                "reviewerReason": decision["reason"].strip(),
            }
        )
        mappings.append(
            {
                "kind": "Entity",
                "regional": entity["regionalName"],
                "acord": entity.get("acordCandidate", {}).get("name", ""),
                "canonical": canonical_name,
                "status": entity["status"],
                "matchPercent": entity["matchPercent"],
                "selection": decision["selection"],
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
                "acord": domain.get("acordCandidate", {}).get("name", ""),
                "canonical": canonical_domain,
                "status": domain["status"],
                "matchPercent": domain["matchPercent"],
                "selection": decision["selection"],
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
                    "acord": capability.get("acordCandidate", {}).get("name", ""),
                    "canonical": f"{canonical_domain}.{canonical_capability}",
                    "status": capability["status"],
                    "matchPercent": capability["matchPercent"],
                    "selection": capability_decision["selection"],
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

    return {
        "version": "1.0",
        "status": "Approved",
        "region": proposal["region"],
        "regionalSourceStatus": proposal["regionalSourceStatus"],
        "acordRunId": proposal["acordRunId"],
        "acordReference": proposal["acordReference"],
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
        else [_unmatched_capability(item) for item in regional.get("capabilities", [])]
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
    scored_pairs = [
        _score_capability(capability, candidate)
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
            _stable_id("regional-capability", capability["name"]),
            _unmatched_capability(capability),
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


def _score_capability(regional: dict[str, Any], acord: dict[str, Any]) -> dict[str, Any]:
    score = (
        _name_similarity(regional["name"], acord["name"]) * 0.8
        + _text_similarity(_regional_capability_text(regional), acord.get("description", "")) * 0.2
    )
    return {
        "regionalId": _stable_id("regional-capability", regional["name"]),
        "regionalName": regional["name"],
        "acordCandidate": deepcopy(acord),
        "status": _status(score, full=85, partial=45),
        "matchPercent": round(score, 1),
    }


def _unmatched_capability(regional: dict[str, Any]) -> dict[str, Any]:
    return {
        "regionalId": _stable_id("regional-capability", regional["name"]),
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


def _default_decision(match: dict[str, Any]) -> dict[str, str]:
    return {
        "selection": USE_ACORD if match.get("acordCandidate") else MANUAL,
        "manualName": "",
        "reason": "",
    }


def _validate_decision(
    match: dict[str, Any], decision: dict[str, Any], label: str, errors: list[str]
) -> None:
    selection = decision.get("selection")
    if selection not in {USE_ACORD, MANUAL}:
        errors.append(f"{label} needs a standard selection")
        return
    if selection == USE_ACORD and not match.get("acordCandidate"):
        errors.append(f"{label} has no ACORD candidate; enter a manual canonical name")
    if selection == MANUAL and not str(decision.get("manualName", "")).strip():
        errors.append(f"{label} needs a manual canonical name")
    if (match["status"] != FULL_MATCH or selection == MANUAL) and not str(
        decision.get("reason", "")
    ).strip():
        errors.append(f"{label} needs a reviewer reason")


def _resolved_name(match: dict[str, Any], decision: dict[str, Any]) -> str:
    if decision["selection"] == USE_ACORD:
        return str(match["acordCandidate"]["name"])
    return str(decision["manualName"]).strip()


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
