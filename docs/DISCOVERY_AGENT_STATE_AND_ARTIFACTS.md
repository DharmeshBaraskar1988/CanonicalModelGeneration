# Discovery Agent: state, steps, and artifacts

This describes the current **Phase 1** implementation, not a planned workflow. A graph node
updates in-memory `DiscoveryState`; only `generate_artifacts` writes the final JSON files.
Implementation: [workflow.py](../src/canonical_model_generator/discovery_agent/workflow.py)
and [artifacts.py](../src/canonical_model_generator/discovery_agent/artifacts.py).

## Inputs and state

`run_discovery` starts with `region`, `system`, `repository`, `project`, `openapi`, `output`,
`errors=[]`, and `events=[]`. `DiscoveryState` can subsequently hold:

| State key | Meaning | Produced by |
| --- | --- | --- |
| `roslyn_model` | Deterministic model extracted from a .NET project | `roslyn` |
| `openapi_model` | Deterministic model extracted from YAML/JSON | `openapi` |
| `model` | Reconciled or single-source `DiscoveryModel` | `reconcile`, then `validate_model` |
| `artifacts` | Map of output filenames to written paths | `generate_artifacts` |
| `errors` | Input/extraction failures | Validation or extractor nodes |
| `events` | Node and status (`ok`, `skipped`, `error`) | Every node |

The graph runs sequentially: `validate_inputs` → `roslyn` → `openapi` → `reconcile` →
`validate_model` → `generate_artifacts`. A missing *optional* source causes its extraction node
to be skipped. A recorded error causes downstream work to be skipped; do not treat an absent
`model` or `artifacts` key as an empty successful result.

## Step-by-step handoff

| Step | Reads | Adds/updates state | Writes a final file? |
| --- | --- | --- | --- |
| `validate_inputs` | Input paths, region, system | `errors`, `events`; checks source existence and repository boundary | No |
| `roslyn` | `project`, `repository`, region/system; prior `errors` | `roslyn_model` if a project is supplied and succeeds; `events` | No |
| `openapi` | `openapi`, region/system, repository boundary; prior `errors` | `openapi_model` if a spec is supplied and succeeds; `events` | No |
| `reconcile` | `roslyn_model` and/or `openapi_model` | `model`; merges both evidence sets when both exist, otherwise keeps the available one | No |
| `validate_model` | `model` | Revalidates and replaces `model` with a schema-valid `DiscoveryModel` | No |
| `generate_artifacts` | Validated `model`, `output` | `artifacts` filename → path map | **Six JSON files** |

`roslyn_model` and `openapi_model` are internal intermediate values, **not** agent handoff
artifacts. The DiscoveryModel preserves structural IDs, evidence, lineage, diagnostics, and
conflicts. The five other JSON files are readable operator views derived from it.

## Final Discovery files

| File | What it contains | Who uses it next? |
| --- | --- | --- |
| `discovery-model.json` | Full validated structural model: operations, contract entities and attributes, enums, validations, relationships, evidence, lineage, diagnostics | **API Analyzer's required agent-to-agent input**; optionally RAG subject binding |
| `api-catalog.json` | Readable endpoint catalog, request/response details and model trees | Operator preview/download; **not** Analyzer input |
| `data-model.json` | Readable endpoint-reachable contract models and fields | Operator preview/download; **not** Analyzer input |
| `relationship-graph.json` | Readable subject relationships and locations | Operator preview/download; **not** Analyzer input |
| `validation-enums.json` | Readable validations and enum definitions | Operator preview/download; **not** Analyzer input |
| `lineage.json` | Readable source provenance | Operator preview/download; **not** Analyzer input |

The CLI writes all six files to `--output`. The Streamlit Discovery tab displays/downloads the
five operator views, while retaining serialized `discovery-model.json` bytes privately in
`st.session_state["discovery_model"]` for the next agent. It does **not** send the Discovery
graph's live state or a live `DiscoveryModel` object to the API Analyzer.

## Streamlit path is slightly different

For a repository ZIP, [streamlit_app.py](../streamlit_app.py) inspects the archive, selects
controller-owning projects, calls Roslyn for each, merges their models, optionally reconciles
OpenAPI, and then calls `generate_artifacts` directly. It does **not** invoke the sequential
`run_discovery` graph for that repository path. For OpenAPI-only upload it **does** call
`run_discovery`. Both paths end with the same six generated file types and the same serialized
DiscoveryModel handoff.

Next: [Repository RAG state and artifacts](REPOSITORY_RAG_STATE_AND_ARTIFACTS.md), then
[API Analyzer state and artifacts](API_ANALYZER_STATE_AND_ARTIFACTS.md).
