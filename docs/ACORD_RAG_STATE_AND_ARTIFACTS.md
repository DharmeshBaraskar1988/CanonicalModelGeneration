# ACORD RAG State and Artifacts

Last updated: 2026-09-29

## Boundary

ACORD ingestion is an independent reference pipeline, not a fifth stage of the selected regional
application. It accepts one operator-authorized OpenAPI 3 YAML/JSON document plus an explicit
reference label and approved version. It performs deterministic extraction and local retrieval
indexing only; it does not align the reference with a regional API or create a canonical model.

## Extracted content

- HTTP method, route, operation ID, tags, summaries, descriptions, parameters, request bodies,
  responses, media types, and status descriptions.
- Named component schemas and recursively promoted inline object/array-item schemas.
- Entity attributes, types, formats, requiredness, nullability, collection shape, enums, and local
  references.
- Available `description`, `$comment`, description/comment/note vendor fields, and external-document
  metadata.
- Numeric, string, array, object, read/write, deprecation, default, constant, enum, and example
  constraints when present and within the bounded value limit.
- Source SHA-256 and JSON-pointer lineage for endpoints, entities, attributes, enums, and validation
  rules.

YAML formatting comments are not part of the parsed OpenAPI data model and cannot be preserved.
Use OpenAPI `description`, JSON Schema `$comment`, or a description/comment/note extension when the
prose must enter artifacts and retrieval chunks.

## Five operator artifacts

The ACORD tab mirrors the Discovery artifact view:

1. `api-catalog.json` — endpoints, parameters, request/response bodies, and cycle-safe nested model
   trees with prose and constraints.
2. `data-model.json` — entities, nested-model references, fields, enums, prose, constraints, and
   source pointers.
3. `relationship-graph.json` — readable endpoint-to-model and entity-to-field/model relations.
4. `validation-enums.json` — flattened validation constraints and enum definitions.
5. `lineage.json` — reference provenance, source hash, subject pointers, and parsing diagnostics.

The tab offers individual downloads, a five-artifact ZIP, JSON preview, and the internal
`acord-rag-manifest.json` used to reopen the index.

## Chunking and retrieval

Chunks are structural rather than arbitrary character windows:

- An endpoint chunk keeps method/route, operation prose, tags, parameters, request/response models,
  response descriptions, comments, and constraints together.
- An entity chunk keeps entity prose and complete field sections together, including nested-model
  types and field constraints.
- Oversized subjects split only between semantic sections and repeat their subject header.
- Every chunk retains its source pointer, aliases, stable content-derived ID, kind, and truncation
  state.

The default local Sentence Transformer creates embeddings and Chroma stores them under
`.acord/<run-id>/index/`. Query ranking combines exact subject aliases, lexical matching, and vector
similarity. The UI exposes retrieved text and its source pointer so later alignment input can be
inspected before that capability is implemented.

## Persistence and handling

Each successful ingestion is stored under ignored `.acord/<run-id>/` local storage with the
original reference, deterministic model, five artifacts, manifest, and Chroma directory. The
workspace can reopen a complete saved record after Streamlit restarts. Incomplete or invalid record
directories are ignored.

ACORD references may be licensed material. Operators are responsible for authorizing ingestion,
protecting `.acord/`, and removing local records according to their data-handling policy.
