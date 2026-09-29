"""Deterministic ACORD OpenAPI extraction, artifacts, and semantic chunks."""

from __future__ import annotations

import json
from copy import deepcopy
from hashlib import sha256
from typing import Any

import yaml

ACORD_ARTIFACTS = {
    "API Catalog": "api-catalog.json",
    "Data Model": "data-model.json",
    "Relationship Graph": "relationship-graph.json",
    "Validation and enums": "validation-enums.json",
    "Lineage": "lineage.json",
}

HTTP_METHODS = ("get", "post", "put", "patch", "delete", "head", "options", "trace")
CONSTRAINT_KEYS = (
    "minimum",
    "maximum",
    "exclusiveMinimum",
    "exclusiveMaximum",
    "multipleOf",
    "minLength",
    "maxLength",
    "pattern",
    "minItems",
    "maxItems",
    "uniqueItems",
    "minProperties",
    "maxProperties",
    "additionalProperties",
    "readOnly",
    "writeOnly",
    "deprecated",
    "default",
    "const",
)
MAX_DOCUMENT_BYTES = 10_000_000
MAX_CHUNK_CHARACTERS = 5_000


def _stable_id(kind: str, *parts: str) -> str:
    value = "\x1f".join((kind, *parts))
    return f"{kind}-{sha256(value.encode('utf-8')).hexdigest()[:20]}"


def _escape(value: str) -> str:
    return value.replace("~", "~0").replace("/", "~1")


def _load_document(content: bytes, filename: str) -> dict[str, Any]:
    if not content:
        raise ValueError("The ACORD document is empty")
    if len(content) > MAX_DOCUMENT_BYTES:
        raise ValueError("The ACORD document exceeds the 10 MB ingestion limit")
    suffix = filename.lower().rsplit(".", 1)[-1] if "." in filename else ""
    if suffix not in {"json", "yaml", "yml"}:
        raise ValueError("Upload an ACORD OpenAPI document in JSON or YAML format")
    try:
        text = content.decode("utf-8-sig")
        loaded = json.loads(text) if suffix == "json" else yaml.safe_load(text)
    except (UnicodeDecodeError, json.JSONDecodeError, yaml.YAMLError) as exc:
        raise ValueError(f"Invalid ACORD {suffix.upper()} document: {exc}") from exc
    if not isinstance(loaded, dict):
        raise ValueError("The ACORD document root must be an object")
    version = str(loaded.get("openapi", ""))
    if not version.startswith("3."):
        raise ValueError("ACORD ingestion currently supports OpenAPI 3.x YAML/JSON documents")
    if not isinstance(loaded.get("paths", {}), dict):
        raise ValueError("OpenAPI paths must be an object")
    return loaded


class _Extractor:
    def __init__(self, document: dict[str, Any], filename: str, content: bytes) -> None:
        self.document = document
        self.filename = filename
        self.content = content
        self.entities: dict[str, dict[str, Any]] = {}
        self.enums: dict[str, dict[str, Any]] = {}
        self.relationships: list[dict[str, Any]] = []
        self.validations: list[dict[str, Any]] = []
        self.lineage: list[dict[str, Any]] = []
        self.diagnostics: list[dict[str, str]] = []
        self._building: set[str] = set()

    def resolve(self, value: Any, pointer: str) -> tuple[Any, str]:
        if not isinstance(value, dict) or "$ref" not in value:
            return value, pointer
        reference = value["$ref"]
        if not isinstance(reference, str) or not reference.startswith("#/"):
            self.diagnostics.append(
                {
                    "severity": "warning",
                    "code": "EXTERNAL_REFERENCE",
                    "message": f"External reference was not resolved at {pointer}: {reference}",
                }
            )
            return value, pointer
        current: Any = self.document
        try:
            for token in reference[2:].split("/"):
                current = current[token.replace("~1", "/").replace("~0", "~")]
        except (KeyError, TypeError):
            self.diagnostics.append(
                {
                    "severity": "error",
                    "code": "BROKEN_REFERENCE",
                    "message": f"Reference does not resolve at {pointer}: {reference}",
                }
            )
            return value, pointer
        return current, reference

    def flatten(self, schema: Any, pointer: str) -> tuple[dict[str, Any], str]:
        resolved, resolved_pointer = self.resolve(schema, pointer)
        if not isinstance(resolved, dict):
            return {}, resolved_pointer
        if "allOf" not in resolved:
            return resolved, resolved_pointer
        merged: dict[str, Any] = {
            key: deepcopy(value) for key, value in resolved.items() if key != "allOf"
        }
        merged.setdefault("type", "object")
        merged.setdefault("properties", {})
        merged.setdefault("required", [])
        for index, part in enumerate(resolved.get("allOf", [])):
            nested, _ = self.flatten(part, f"{resolved_pointer}/allOf/{index}")
            merged["properties"].update(deepcopy(nested.get("properties", {})))
            merged["required"].extend(nested.get("required", []))
            for key in ("description", "title", "$comment"):
                if key not in merged and key in nested:
                    merged[key] = nested[key]
        merged["required"] = sorted(set(merged["required"]))
        return merged, resolved_pointer

    def semantic_text(self, value: dict[str, Any]) -> tuple[str | None, list[str]]:
        description = _clean_text(value.get("description"))
        comments: list[str] = []
        for key, raw_note in sorted(value.items()):
            normalized_key = key.casefold()
            if (
                key == "description"
                or key == "externalDocs"
                or not (
                    key == "$comment"
                    or any(token in normalized_key for token in ("comment", "note", "description"))
                )
            ):
                continue
            text = _semantic_text_value(raw_note)
            if text and text != description and text not in comments:
                comments.append(text)
        external = value.get("externalDocs")
        if isinstance(external, dict):
            parts = [
                _clean_text(external.get("description")),
                _clean_text(external.get("url")),
            ]
            note = " — ".join(part for part in parts if part)
            if note:
                comments.append(f"External documentation: {note}")
        return description, comments

    def constraints(self, schema: dict[str, Any]) -> dict[str, Any]:
        result = {
            key: deepcopy(schema[key])
            for key in CONSTRAINT_KEYS
            if key in schema and _bounded_json_value(schema[key])
        }
        if "enum" in schema:
            result["allowedValues"] = deepcopy(schema["enum"])
        if "example" in schema and _bounded_json_value(schema["example"]):
            result["example"] = deepcopy(schema["example"])
        return result

    def ensure_entity(self, name: str, schema: Any, pointer: str) -> str:
        flattened, resolved_pointer = self.flatten(schema, pointer)
        entity_id = _stable_id("acord-entity", name, resolved_pointer)
        if entity_id in self.entities or entity_id in self._building:
            return entity_id
        if "enum" in flattened and not flattened.get("properties"):
            enum_id = _stable_id("acord-enum", name, resolved_pointer)
            if enum_id not in self.enums:
                self.enums[enum_id] = self.enum_record(name, flattened, resolved_pointer)
            return enum_id
        self._building.add(entity_id)
        description, comments = self.semantic_text(flattened)
        entity = {
            "id": entity_id,
            "name": name,
            "title": _clean_text(flattened.get("title")),
            "description": description,
            "comments": comments,
            "constraints": self.constraints(flattened),
            "attributes": [],
            "sourcePointer": resolved_pointer,
        }
        self.entities[entity_id] = entity
        self.trace(entity_id, "Entity", name, resolved_pointer)
        required = set(flattened.get("required", []))
        properties = flattened.get("properties", {})
        if not isinstance(properties, dict):
            properties = {}
        for property_name, property_schema in sorted(properties.items()):
            property_pointer = f"{resolved_pointer}/properties/{_escape(str(property_name))}"
            attribute = self.attribute_record(
                entity,
                str(property_name),
                property_schema,
                property_pointer,
                property_name in required,
            )
            entity["attributes"].append(attribute)
            self.relationships.append(
                {
                    "type": "CONTAINS",
                    "from": entity_id,
                    "to": attribute["id"],
                    "via": property_name,
                }
            )
            if attribute["referencedEntityId"]:
                self.relationships.append(
                    {
                        "type": "REFERENCES",
                        "from": attribute["id"],
                        "to": attribute["referencedEntityId"],
                        "via": property_name,
                    }
                )
        self._building.remove(entity_id)
        return entity_id

    def attribute_record(
        self,
        parent: dict[str, Any],
        name: str,
        original: Any,
        pointer: str,
        required: bool,
    ) -> dict[str, Any]:
        schema, resolved_pointer = self.flatten(original, pointer)
        collection = schema.get("type") == "array"
        value_schema: Any = schema.get("items", {}) if collection else original
        value_pointer = f"{pointer}/items" if collection else pointer
        flattened_value, _ = self.flatten(value_schema, value_pointer)
        reference_name = _reference_name(value_schema)
        referenced_entity_id: str | None = None
        if reference_name:
            referenced_entity_id = self.ensure_entity(reference_name, value_schema, value_pointer)
        elif flattened_value.get("properties") or flattened_value.get("type") == "object":
            inline_name = f"{parent['name']}.{name}"
            referenced_entity_id = self.ensure_entity(inline_name, value_schema, value_pointer)
            reference_name = inline_name
        attribute_id = _stable_id("acord-attribute", parent["id"], name)
        description, comments = self.semantic_text(schema)
        constraints = self.constraints(schema)
        if required:
            constraints = {"required": True, **constraints}
        attribute = {
            "id": attribute_id,
            "name": name,
            "type": reference_name or _schema_type(flattened_value),
            "format": flattened_value.get("format") or schema.get("format"),
            "required": required,
            "nullable": bool(schema.get("nullable", False)),
            "collection": collection,
            "description": description,
            "comments": comments,
            "constraints": constraints,
            "referencedEntityId": referenced_entity_id,
            "sourcePointer": resolved_pointer,
        }
        self.trace(attribute_id, "Attribute", f"{parent['name']}.{name}", resolved_pointer)
        for rule, value in constraints.items():
            self.validations.append(
                {
                    "targetId": attribute_id,
                    "target": f"{parent['name']}.{name}",
                    "rule": rule,
                    "value": deepcopy(value),
                    "sourcePointer": resolved_pointer,
                }
            )
        return attribute

    def enum_record(self, name: str, schema: dict[str, Any], pointer: str) -> dict[str, Any]:
        enum_id = _stable_id("acord-enum", name, pointer)
        description, comments = self.semantic_text(schema)
        record = {
            "id": enum_id,
            "name": name,
            "values": deepcopy(schema.get("enum", [])),
            "description": description,
            "comments": comments,
            "sourcePointer": pointer,
        }
        self.trace(enum_id, "Enum", name, pointer)
        return record

    def trace(self, subject_id: str, subject_type: str, subject: str, pointer: str) -> None:
        self.lineage.append(
            {
                "subjectId": subject_id,
                "subjectType": subject_type,
                "subject": subject,
                "source": self.filename,
                "pointer": pointer,
            }
        )

    def schema_target(self, schema: Any, pointer: str, fallback_name: str) -> dict[str, Any] | None:
        if not isinstance(schema, dict) or not schema:
            return None
        collection = schema.get("type") == "array"
        value_schema = schema.get("items", {}) if collection else schema
        value_pointer = f"{pointer}/items" if collection else pointer
        reference_name = _reference_name(value_schema)
        flattened, _ = self.flatten(value_schema, value_pointer)
        schema_description, schema_comments = self.semantic_text(flattened)
        entity_id = None
        entity_name = None
        if reference_name:
            entity_name = reference_name
            entity_id = self.ensure_entity(reference_name, value_schema, value_pointer)
        elif flattened.get("properties") or flattened.get("type") == "object":
            entity_name = fallback_name
            entity_id = self.ensure_entity(fallback_name, value_schema, value_pointer)
        return {
            "entityId": entity_id,
            "entity": entity_name,
            "type": entity_name or _schema_type(flattened),
            "format": flattened.get("format"),
            "collection": collection,
            "constraints": self.constraints(schema),
            "schemaDescription": schema_description,
            "schemaComments": schema_comments,
        }

    def endpoint_record(
        self, route: str, method: str, operation: dict[str, Any], path_item: dict[str, Any]
    ) -> dict[str, Any]:
        pointer = f"#/paths/{_escape(route)}/{method}"
        operation_id = _stable_id("acord-endpoint", method.upper(), route)
        description, comments = self.semantic_text(operation)
        endpoint = {
            "id": operation_id,
            "operationId": operation.get("operationId") or f"{method}-{route}",
            "method": method.upper(),
            "route": route,
            "summary": _clean_text(operation.get("summary")),
            "description": description,
            "comments": comments,
            "tags": [str(item) for item in operation.get("tags", [])],
            "deprecated": bool(operation.get("deprecated", False)),
            "parameters": [],
            "requestBodies": [],
            "responses": [],
            "sourcePointer": pointer,
        }
        self.trace(
            operation_id,
            "Endpoint",
            f"{method.upper()} {route} ({endpoint['operationId']})",
            pointer,
        )
        parameters = [*path_item.get("parameters", []), *operation.get("parameters", [])]
        for index, raw_parameter in enumerate(parameters):
            parameter_pointer = f"{pointer}/parameters/{index}"
            parameter, resolved_pointer = self.resolve(raw_parameter, parameter_pointer)
            if not isinstance(parameter, dict):
                continue
            schema, _ = self.flatten(parameter.get("schema", {}), f"{resolved_pointer}/schema")
            parameter_description, parameter_comments = self.semantic_text(parameter)
            constraints = self.constraints(schema)
            if parameter.get("required"):
                constraints = {"required": True, **constraints}
            endpoint["parameters"].append(
                {
                    "name": str(parameter.get("name", f"parameter-{index + 1}")),
                    "location": str(parameter.get("in", "query")),
                    "required": bool(parameter.get("required", False)),
                    "type": _schema_type(schema),
                    "format": schema.get("format"),
                    "description": parameter_description,
                    "comments": parameter_comments,
                    "constraints": constraints,
                    "sourcePointer": resolved_pointer,
                }
            )
        request_body = operation.get("requestBody")
        if isinstance(request_body, dict):
            request_body, request_pointer = self.resolve(request_body, f"{pointer}/requestBody")
            request_description, request_comments = self.semantic_text(request_body)
            for media_type, media in sorted(request_body.get("content", {}).items()):
                schema_pointer = f"{request_pointer}/content/{_escape(media_type)}/schema"
                target = self.schema_target(
                    media.get("schema", {}), schema_pointer, f"{endpoint['operationId']}.Request"
                )
                if target:
                    endpoint["requestBodies"].append(
                        {
                            "mediaType": media_type,
                            "required": bool(request_body.get("required", False)),
                            "description": request_description,
                            "comments": request_comments,
                            **target,
                        }
                    )
                    if target["entityId"]:
                        self.relationships.append(
                            {
                                "type": "ACCEPTS",
                                "from": operation_id,
                                "to": target["entityId"],
                                "via": media_type,
                            }
                        )
        for status, raw_response in sorted(operation.get("responses", {}).items()):
            response_pointer = f"{pointer}/responses/{_escape(str(status))}"
            response, resolved_pointer = self.resolve(raw_response, response_pointer)
            if not isinstance(response, dict):
                continue
            response_description, response_comments = self.semantic_text(response)
            bodies = []
            for media_type, media in sorted(response.get("content", {}).items()):
                schema_pointer = f"{resolved_pointer}/content/{_escape(media_type)}/schema"
                target = self.schema_target(
                    media.get("schema", {}),
                    schema_pointer,
                    f"{endpoint['operationId']}.Response{status}",
                )
                if target:
                    bodies.append({"mediaType": media_type, **target})
                    if target["entityId"]:
                        self.relationships.append(
                            {
                                "type": "RETURNS",
                                "from": operation_id,
                                "to": target["entityId"],
                                "via": str(status),
                            }
                        )
            endpoint["responses"].append(
                {
                    "status": str(status),
                    "description": response_description,
                    "comments": response_comments,
                    "bodies": bodies,
                    "sourcePointer": resolved_pointer,
                }
            )
        return endpoint

    def extract(self, reference_label: str, reference_version: str) -> dict[str, Any]:
        schemas = self.document.get("components", {}).get("schemas", {})
        if not isinstance(schemas, dict):
            raise ValueError("OpenAPI components.schemas must be an object")
        for name, schema in sorted(schemas.items()):
            self.ensure_entity(str(name), schema, f"#/components/schemas/{_escape(str(name))}")
        endpoints = []
        for route, path_item in sorted(self.document.get("paths", {}).items()):
            if not isinstance(path_item, dict):
                continue
            for method in HTTP_METHODS:
                operation = path_item.get(method)
                if isinstance(operation, dict):
                    endpoints.append(self.endpoint_record(str(route), method, operation, path_item))
        info = self.document.get("info", {}) if isinstance(self.document.get("info"), dict) else {}
        info_description, info_comments = self.semantic_text(info)
        source = {
            "filename": self.filename,
            "sha256": sha256(self.content).hexdigest(),
            "openapiVersion": str(self.document.get("openapi")),
            "title": _clean_text(info.get("title")),
            "documentVersion": _clean_text(info.get("version")),
            "referenceLabel": reference_label,
            "referenceVersion": reference_version,
            "description": info_description,
            "comments": info_comments,
        }
        return {
            "schemaVersion": "acord-ingestion/1.0",
            "source": source,
            "endpoints": sorted(endpoints, key=lambda item: (item["route"], item["method"])),
            "entities": sorted(self.entities.values(), key=lambda item: item["name"]),
            "enums": sorted(self.enums.values(), key=lambda item: item["name"]),
            "relationships": sorted(
                _deduplicate(self.relationships),
                key=lambda item: (item["from"], item["type"], item["to"], item["via"]),
            ),
            "validations": sorted(
                _deduplicate(self.validations),
                key=lambda item: (item["target"], item["rule"]),
            ),
            "lineage": sorted(
                _deduplicate(self.lineage),
                key=lambda item: (item["subjectType"], item["subject"], item["pointer"]),
            ),
            "diagnostics": self.diagnostics,
            "summary": {
                "endpointCount": len(endpoints),
                "entityCount": len(self.entities),
                "attributeCount": sum(
                    len(entity["attributes"]) for entity in self.entities.values()
                ),
                "enumCount": len(self.enums),
                "relationshipCount": len(_deduplicate(self.relationships)),
                "validationCount": len(_deduplicate(self.validations)),
                "diagnosticCount": len(self.diagnostics),
            },
        }


def parse_acord_document(
    content: bytes,
    filename: str,
    *,
    reference_label: str,
    reference_version: str,
) -> dict[str, Any]:
    """Parse one authorized ACORD OpenAPI document into deterministic structural truth."""
    if not reference_label.strip() or not reference_version.strip():
        raise ValueError("ACORD reference label and version are required")
    document = _load_document(content, filename)
    return _Extractor(document, filename, content).extract(
        reference_label.strip(), reference_version.strip()
    )


def generate_acord_artifacts(model: dict[str, Any]) -> dict[str, bytes]:
    """Render the five Discovery-equivalent operator artifacts."""
    entities_by_id = {item["id"]: item for item in model["entities"]}
    enums_by_id = {item["id"]: item for item in model["enums"]}
    names = {key: value["name"] for key, value in {**entities_by_id, **enums_by_id}.items()}

    def model_tree(entity_id: str | None) -> dict[str, Any] | None:
        if not entity_id or entity_id not in entities_by_id:
            return None
        pending = [entity_id]
        visited: set[str] = set()
        models = []
        relations = []
        while pending:
            current_id = pending.pop(0)
            if current_id in visited or current_id not in entities_by_id:
                continue
            visited.add(current_id)
            entity = entities_by_id[current_id]
            fields = []
            for field in entity["attributes"]:
                fields.append(_public_attribute(field, names))
                related = field.get("referencedEntityId")
                if related in entities_by_id:
                    relations.append(
                        {
                            "from": entity["name"],
                            "relationship": "contains many" if field["collection"] else "contains",
                            "viaField": field["name"],
                            "to": entities_by_id[related]["name"],
                        }
                    )
                    if related not in visited:
                        pending.append(related)
            models.append(
                {
                    "name": entity["name"],
                    "title": entity["title"],
                    "description": entity["description"],
                    "comments": entity["comments"],
                    "constraints": entity["constraints"],
                    "fields": fields,
                    "source": _location(model, entity["sourcePointer"]),
                }
            )
        return {
            "rootModel": entities_by_id[entity_id]["name"],
            "models": models,
            "relations": relations,
        }

    operations = []
    for endpoint in model["endpoints"]:
        requests = []
        for body in endpoint["requestBodies"]:
            requests.append(
                {
                    **_public_body(body, names),
                    "modelTree": model_tree(body.get("entityId")),
                }
            )
        responses = []
        for response in endpoint["responses"]:
            responses.append(
                {
                    "status": response["status"],
                    "description": response["description"],
                    "comments": response["comments"],
                    "bodies": [
                        {
                            **_public_body(body, names),
                            "modelTree": model_tree(body.get("entityId")),
                        }
                        for body in response["bodies"]
                    ],
                    "source": _location(model, response["sourcePointer"]),
                }
            )
        operations.append(
            {
                "operation": endpoint["operationId"],
                "method": endpoint["method"],
                "route": endpoint["route"],
                "summary": endpoint["summary"],
                "description": endpoint["description"],
                "comments": endpoint["comments"],
                "tags": endpoint["tags"],
                "deprecated": endpoint["deprecated"],
                "parameters": [
                    {key: value for key, value in parameter.items() if key != "sourcePointer"}
                    | {"source": _location(model, parameter["sourcePointer"])}
                    for parameter in endpoint["parameters"]
                ],
                "requestBodies": requests,
                "responses": responses,
                "source": _location(model, endpoint["sourcePointer"]),
            }
        )
    data_model = {
        "entities": [
            {
                "name": entity["name"],
                "title": entity["title"],
                "description": entity["description"],
                "comments": entity["comments"],
                "constraints": entity["constraints"],
                "fields": [_public_attribute(field, names) for field in entity["attributes"]],
                "source": _location(model, entity["sourcePointer"]),
            }
            for entity in model["entities"]
        ],
        "enums": [_public_enum(item, model) for item in model["enums"]],
        "entityCount": model["summary"]["entityCount"],
        "enumCount": model["summary"]["enumCount"],
    }
    subject_names = _subject_names(model)
    relationship_graph = {
        "relationships": [
            {
                "relationship": (
                    f"{subject_names.get(item['from'], 'Unknown')} "
                    f"{item['type'].lower()} {subject_names.get(item['to'], 'Unknown')}"
                ),
                "type": item["type"],
                "from": subject_names.get(item["from"], "Unknown"),
                "to": subject_names.get(item["to"], "Unknown"),
                "via": item["via"],
            }
            for item in model["relationships"]
        ],
        "relationshipCount": model["summary"]["relationshipCount"],
    }
    validation_enums = {
        "validations": [
            {
                "target": item["target"],
                "rule": item["rule"],
                "value": item["value"],
                "source": _location(model, item["sourcePointer"]),
            }
            for item in model["validations"]
        ],
        "enums": [_public_enum(item, model) for item in model["enums"]],
    }
    lineage = {
        "source": model["source"],
        "lineage": [
            {
                "subject": item["subject"],
                "subjectType": item["subjectType"],
                "source": _location(model, item["pointer"]),
            }
            for item in model["lineage"]
        ],
        "diagnostics": model["diagnostics"],
        "lineageCount": len(model["lineage"]),
        "diagnosticCount": len(model["diagnostics"]),
    }
    payloads = {
        "API Catalog": {"operations": operations, "operationCount": len(operations)},
        "Data Model": data_model,
        "Relationship Graph": relationship_graph,
        "Validation and enums": validation_enums,
        "Lineage": lineage,
    }
    return {
        label: (json.dumps(payload, indent=2, sort_keys=True) + "\n").encode("utf-8")
        for label, payload in payloads.items()
    }


def build_acord_chunks(model: dict[str, Any]) -> list[dict[str, Any]]:
    """Create bounded endpoint/entity chunks that retain descriptive and constraint context."""
    chunks: list[dict[str, Any]] = []
    source = model["source"]
    overview = [
        f"ACORD reference: {source['referenceLabel']} {source['referenceVersion']}",
        f"OpenAPI title: {source.get('title') or 'Not supplied'}",
        f"Document version: {source.get('documentVersion') or 'Not supplied'}",
    ]
    if source.get("description"):
        overview.append(f"Description: {source['description']}")
    overview.extend(f"Comment: {comment}" for comment in source.get("comments", []))
    chunks.append(_chunk("reference", source["referenceLabel"], "#", "\n".join(overview)))

    entity_names = {item["id"]: item["name"] for item in model["entities"]}
    for endpoint in model["endpoints"]:
        lines = [
            f"Endpoint {endpoint['method']} {endpoint['route']}",
            f"Operation: {endpoint['operationId']}",
        ]
        _append_semantics(lines, endpoint)
        if endpoint["tags"]:
            lines.append("Tags: " + ", ".join(endpoint["tags"]))
        for parameter in endpoint["parameters"]:
            lines.append(_describe_parameter(parameter))
        for body in endpoint["requestBodies"]:
            lines.append(
                f"Request {body['mediaType']}: "
                f"{entity_names.get(body.get('entityId'), body['type'])}; "
                f"required={body['required']}; constraints={_compact(body['constraints'])}"
            )
            if body.get("description"):
                lines.append(f"Request description: {body['description']}")
            lines.extend(f"Request comment: {item}" for item in body.get("comments", []))
            if body.get("schemaDescription"):
                lines.append(f"Request schema description: {body['schemaDescription']}")
            lines.extend(
                f"Request schema comment: {item}" for item in body.get("schemaComments", [])
            )
        for response in endpoint["responses"]:
            lines.append(
                f"Response {response['status']}: {response.get('description') or 'No description'}"
            )
            lines.extend(f"Response comment: {item}" for item in response.get("comments", []))
            for body in response["bodies"]:
                lines.append(
                    f"Response {response['status']} {body['mediaType']}: "
                    f"{entity_names.get(body.get('entityId'), body['type'])}; "
                    f"constraints={_compact(body['constraints'])}"
                )
                if body.get("schemaDescription"):
                    lines.append(
                        f"Response {response['status']} schema description: "
                        f"{body['schemaDescription']}"
                    )
                lines.extend(
                    f"Response {response['status']} schema comment: {item}"
                    for item in body.get("schemaComments", [])
                )
        chunks.extend(
            _bounded_subject_chunks(
                "endpoint",
                endpoint["id"],
                endpoint["sourcePointer"],
                lines,
                aliases=[endpoint["operationId"], f"{endpoint['method']} {endpoint['route']}"],
            )
        )

    for entity in model["entities"]:
        header = [f"Entity {entity['name']}"]
        if entity.get("title"):
            header.append(f"Title: {entity['title']}")
        _append_semantics(header, entity)
        if entity["constraints"]:
            header.append(f"Entity constraints: {_compact(entity['constraints'])}")
        field_sections = []
        for field in entity["attributes"]:
            section = [
                f"Attribute {entity['name']}.{field['name']}: "
                f"type={field['type']}; required={field['required']}; "
                f"nullable={field['nullable']}; collection={field['collection']}; "
                f"format={field.get('format') or 'none'}"
            ]
            _append_semantics(section, field)
            if field["constraints"]:
                section.append(f"Constraints: {_compact(field['constraints'])}")
            field_sections.append("\n".join(section))
        chunks.extend(
            _bounded_subject_chunks(
                "entity",
                entity["id"],
                entity["sourcePointer"],
                [*header, *field_sections],
                aliases=[entity["name"]],
            )
        )
    return sorted(chunks, key=lambda item: (item["kind"], item["subject"], item["id"]))


def _bounded_subject_chunks(
    kind: str,
    subject_id: str,
    pointer: str,
    sections: list[str],
    *,
    aliases: list[str],
) -> list[dict[str, Any]]:
    header = "\n".join(sections[:2])
    output: list[dict[str, Any]] = []
    current = ""
    for section in sections:
        candidate = f"{current}\n{section}".strip()
        if current and len(candidate) > MAX_CHUNK_CHARACTERS:
            output.append(
                _chunk(kind, subject_id, pointer, current, aliases=aliases, ordinal=len(output))
            )
            current = f"{header}\n{section}".strip()
        else:
            current = candidate
    if current:
        output.append(
            _chunk(kind, subject_id, pointer, current, aliases=aliases, ordinal=len(output))
        )
    return output


def _chunk(
    kind: str,
    subject: str,
    pointer: str,
    text: str,
    *,
    aliases: list[str] | None = None,
    ordinal: int = 0,
) -> dict[str, Any]:
    bounded = text[:MAX_CHUNK_CHARACTERS]
    return {
        "id": _stable_id("acord-chunk", kind, subject, pointer, str(ordinal), bounded),
        "kind": kind,
        "subject": subject,
        "aliases": aliases or [subject],
        "sourcePointer": pointer,
        "text": bounded,
        "truncated": len(text) > len(bounded),
    }


def _append_semantics(lines: list[str], item: dict[str, Any]) -> None:
    if item.get("summary"):
        lines.append(f"Summary: {item['summary']}")
    if item.get("description"):
        lines.append(f"Description: {item['description']}")
    lines.extend(f"Comment: {comment}" for comment in item.get("comments", []))


def _describe_parameter(parameter: dict[str, Any]) -> str:
    description = (
        f"; description={parameter['description']}" if parameter.get("description") else ""
    )
    comments = (
        "; comments=" + " | ".join(parameter["comments"]) if parameter.get("comments") else ""
    )
    return (
        f"Parameter {parameter['name']} in {parameter['location']}: type={parameter['type']}; "
        f"required={parameter['required']}; format={parameter.get('format') or 'none'}; "
        f"constraints={_compact(parameter['constraints'])}{description}{comments}"
    )


def _public_attribute(field: dict[str, Any], names: dict[str, str]) -> dict[str, Any]:
    return {
        "name": field["name"],
        "type": names.get(field.get("referencedEntityId"), field["type"]),
        "format": field["format"],
        "required": field["required"],
        "nullable": field["nullable"],
        "collection": field["collection"],
        "description": field["description"],
        "comments": field["comments"],
        "constraints": field["constraints"],
        "sourcePointer": field["sourcePointer"],
    }


def _public_body(body: dict[str, Any], names: dict[str, str]) -> dict[str, Any]:
    public = {key: value for key, value in body.items() if key != "entityId"}
    public["model"] = names.get(body.get("entityId"), body.get("entity"))
    public.pop("entity", None)
    return public


def _public_enum(item: dict[str, Any], model: dict[str, Any]) -> dict[str, Any]:
    return {
        "name": item["name"],
        "values": item["values"],
        "description": item["description"],
        "comments": item["comments"],
        "source": _location(model, item["sourcePointer"]),
    }


def _subject_names(model: dict[str, Any]) -> dict[str, str]:
    names = {item["id"]: item["operationId"] for item in model["endpoints"]}
    for entity in model["entities"]:
        names[entity["id"]] = entity["name"]
        names.update(
            {field["id"]: f"{entity['name']}.{field['name']}" for field in entity["attributes"]}
        )
    names.update({item["id"]: item["name"] for item in model["enums"]})
    return names


def _location(model: dict[str, Any], pointer: str) -> str:
    return f"{model['source']['filename']}{pointer}"


def _reference_name(schema: Any) -> str | None:
    if not isinstance(schema, dict):
        return None
    reference = schema.get("$ref")
    return reference.rsplit("/", 1)[-1] if isinstance(reference, str) else None


def _schema_type(schema: dict[str, Any]) -> str:
    if "$ref" in schema:
        return _reference_name(schema) or "object"
    if "oneOf" in schema:
        return "oneOf"
    if "anyOf" in schema:
        return "anyOf"
    return str(schema.get("type", "object" if schema.get("properties") else "unknown"))


def _clean_text(value: Any) -> str | None:
    if value is None:
        return None
    text = " ".join(str(value).split())
    return text or None


def _semantic_text_value(value: Any) -> str | None:
    if isinstance(value, (dict, list)):
        return _compact(value) if _bounded_json_value(value) else None
    return _clean_text(value)


def _bounded_json_value(value: Any) -> bool:
    try:
        return len(json.dumps(value, sort_keys=True)) <= 4_000
    except (TypeError, ValueError):
        return False


def _compact(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def _deduplicate(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    unique: dict[str, dict[str, Any]] = {}
    for item in items:
        unique[_compact(item)] = item
    return list(unique.values())
