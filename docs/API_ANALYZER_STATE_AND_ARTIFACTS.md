# API Analyzer: state, steps, and artifacts

This describes the current **Phase 2** LangGraph in
[workflow.py](../src/canonical_model_generator/api_analyzer/workflow.py). A graph node returns
state updates; the last node renders four output artifacts. The required cross-agent input is
serialized `discovery-model.json`, **not** Discovery's live graph state or its five operator
views.

## Input boundary and initial state

`run_api_analyzer_agent` validates the serialized Discovery artifact and creates a private
`DiscoveryModel` for its own graph. The public call also accepts a repository root, semantic
provider, and optionally a saved RAG index path and embedder. Before entering the graph, a
provided saved index is checked against the repository snapshot and DiscoveryModel.

| Initial `Phase2State` key | Meaning |
| --- | --- |
| `discovery_model` | Validated private copy of the serialized Discovery artifact; structural truth |
| `repository_root` | Local source boundary, or temporary directory for YAML-only input |
| `vector_store_path` | Saved RAG directory or temporary index directory |
| `has_repository` | Whether implementation code is available |
| `persistent_index` | Whether an existing saved RAG index was supplied |
| `errors` | Initial issues; YAML-only starts with an implementation-evidence gap |

## Graph step-by-step

Normal path: `build_contexts` → `validate_provider` → `ingest_repository` →
`analyze_endpoints` → `analyze_entities` → `analyze_enums` → `render_and_validate`.
If provider validation fails, the graph goes directly to `render_and_validate` and emits
partial output. YAML-only input passes through `ingest_repository` without indexing code.

| Step | Uses from state | Produces/updates state | Final artifact yet? |
| --- | --- | --- | --- |
| `build_contexts` | `discovery_model`, `repository_root` | `endpoint_contexts`, `entity_contexts`, `enum_contexts`: structural facts plus bounded lineage/source snippets | No |
| `validate_provider` | Provider configuration; `errors` | `provider_ready`; sanitized error on failure | No |
| `ingest_repository` | Contexts, repository root, vector store, DiscoveryModel | Adds exact/hybrid retrieved code to contexts; `retrieval_stats`. YAML-only sets `status=specification-only` | No |
| `analyze_endpoints` | `endpoint_contexts`, index, provider | `endpoint_semantics`, `investigations`, `errors`. May do one bounded low-confidence retrieval and re-analysis | No |
| `analyze_entities` | `entity_contexts`, provider | `entity_semantics` for each model and its attributes as one batch; `errors` | No |
| `analyze_enums` | `enum_contexts`, provider | `enum_semantics`, `errors` | No |
| `render_and_validate` | DiscoveryModel, contexts, semantic results, investigations, retrieval stats, provider status, errors | `artifacts` mapping filenames to bytes | **Four output files** |

Endpoint/entity/enum semantic results are typed **internal graph values**, not files sent
between agents. Structural IDs, routes, response codes, fields, and types come from Discovery;
the provider adds descriptions and classifications. Rendering validates the generated OpenAPI,
compares discovered and enriched coverage, preserves evidence/gaps, and can produce partial
artifacts when provider or evidence work fails.

## Final API Analyzer files

| File | Generated from | Purpose / consumer |
| --- | --- | --- |
| `enriched-openapi.yaml` | Discovery structure plus validated endpoint/entity/enum semantics | Self-contained OpenAPI contract; intended normal input for future Phase 3 ACORD alignment (Phase 3 is **not implemented**) |
| `semantic-metadata.json` | Typed provider results, investigations, retrieval stats | Inspect model classifications/descriptions, confidence, and investigation details |
| `evidence-map.json` | Discovery lineage plus source contexts/results | Inspect which source evidence was considered for semantic targets |
| `enrichment-report.json` | Independent coverage and validation checks, gaps, errors, confidence bands | Decide whether run is complete or partial and what needs review |

`run_api_analyzer_agent` returns these as `dict[str, bytes]`; Streamlit keeps them in
`st.session_state["phase_2_artifacts"]` for preview/download. The graph's `artifacts` key is the
return value, not a new agent handoff to Discovery.

In the UI, each completed Discovery submission has a session-scoped application profile (region,
application name, repository ZIP name) and its own Discovery bytes, repository archive, fresh
RAG path, and Phase 2 outputs. Identical uploads remain separate runs and never inherit an index.
The Phase 2 selector activates one profile before running; the readiness checklist requires only
that profile's RAG index for repository input, a key, a model, and explicit source-sharing
consent. Profiles do not survive a browser-session or server restart. A password-masked key
override is session-only and never serialized into an artifact.

The UI retains a failure message on the selected application profile. A successful or failed run
immediately exposes a retry action for that same profile; retry clears only its previous Phase 2
outputs/error and reuses its Discovery artifact, repository archive, and RAG index.

## Focused interpretation is a separate path

The RAG tab's **Explain selected target** action calls
[inspect.py](../src/canonical_model_generator/api_analyzer/inspect.py), not the full Phase 2
graph. It uses one target ID, the serialized DiscoveryModel, and retrieved chunks. For an
attribute, it analyzes the owning entity's fields together, then returns the selected field plus
separate code claims with validated chunk IDs. A free code query has no Discovery target and
returns code claims only. These focused dictionaries are UI session values, **not** any of the
four full-run output files.

Previous: [Discovery Agent state and artifacts](DISCOVERY_AGENT_STATE_AND_ARTIFACTS.md) and
[Repository RAG state and artifacts](REPOSITORY_RAG_STATE_AND_ARTIFACTS.md).
