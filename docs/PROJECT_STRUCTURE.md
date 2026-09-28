# Project Structure

The repository uses a Python `src` layout, keeps deterministic discovery separate from semantic
analysis, and treats the .NET Roslyn extractor as an independent sidecar.

```text
.
|-- src/canonical_model_generator/
|   |-- discovery_agent/           # Phase 1 deterministic agent boundary
|   |   |-- model.py               # DiscoveryModel and stable identifiers
|   |   |-- roslyn.py              # Roslyn sidecar adapter
|   |   |-- openapi.py             # Deterministic OpenAPI extraction
|   |   |-- reconcile.py           # Evidence reconciliation and scoping
|   |   |-- artifacts.py           # Discovery artifact rendering
|   |   `-- workflow.py            # Phase 1 LangGraph orchestration
|   |-- api_analyzer/              # Phase 2 semantic-analysis boundary
|   |   |-- contracts.py           # Provider-neutral structured-output contracts
|   |   |-- prompts.py             # Reviewable, versioned system prompts
|   |   |-- providers/             # External model SDK adapters
|   |   |-- tools/                 # Bounded repository-search implementation
|   |   `-- workflow.py            # Phase 2 LangGraph and artifact rendering
|   |-- repository_rag/            # Reusable repository evidence service
|   |   |-- chunking.py            # Bounded sources, Roslyn hierarchy, relationship candidates
|   |   |-- embeddings.py          # Local Sentence Transformer / OpenAI adapters
|   |   |-- index.py               # Persistent Chroma + exact/hybrid retrieval
|   |   `-- cli.py                 # Independent index/query commands
|   |-- model.py, graph.py, ...    # Temporary compatibility imports only
|   `-- intake.py                  # Safe upload inspection
|-- dotnet/src/                    # Production Roslyn extractor
|-- dotnet/tests/                  # .NET tests
|-- tests/                         # Python unit/integration tests
|-- fixtures/                      # Synthetic acceptance fixture only
|-- schemas/                       # Versioned generated public schemas
|-- scripts/                       # Maintenance commands, not runtime code
|-- docs/                          # Architecture, status, decisions, and operations
|-- streamlit_app.py               # Deployment-compatible UI entry point
`-- pyproject.toml                 # Python build, dependencies, and tool configuration
```

## Dependency direction

Deterministic discovery must not depend on the API Analyzer. The only runtime handoff from the
Discovery Agent to the API Analyzer Agent is the serialized and validated `discovery-model.json`
artifact. The API Analyzer validates that artifact on entry; callers do not pass Phase 1 graph state
or an in-memory model across the boundary. Providers depend on contracts and prompts; workflows
depend on provider interfaces and bounded tools. Prompt text must not be embedded in provider SDK
calls.

The repository RAG service builds a separate `rag-manifest.json` plus Chroma directory. It consumes
the repository and optionally the serialized discovery contract to bind stable endpoint/entity/field
IDs to code chunks. API Analyzer can reopen this saved artifact, checks its source hashes and
discovery digest before provider calls, and retrieves evidence without receiving another agent's
graph state. The manifest contains redacted code, citations, parent IDs, typed edges, embedding
configuration and coverage gaps. Keep it with its adjacent `chroma/` directory to reopen vectors.

## Runtime and generated files

`.rag`, `.venv`, `.tmp`, `.pytest_cache`, `.ruff_cache`, `__pycache__`, `.env`, `bin`, and `obj` are local or
generated state. They are intentionally excluded by `.gitignore` and are not part of the production
source tree. The inactive `normalization.py` and its schema are retained because ADR-013 explicitly
records them as deferred work; removing them requires a separate decision and migration.
