# Canonical Model Generator

This project will discover the structure and behavior of regional insurance APIs and produce a normalized, traceable Discovery Model. Later releases may use that foundation for semantic alignment and canonical-model generation.

## Project tracking

- [Implementation plan](docs/IMPLEMENTATION_PLAN.md)
- [Current status](docs/STATUS.md)
- [Next steps](docs/NEXT_STEPS.md)
- [Architecture decisions](docs/DECISIONS.md)
- [Production project structure](docs/PROJECT_STRUCTURE.md)
- [Installation and user guide](docs/USER_GUIDE.md)
- [Repository RAG and chunking example](docs/REPOSITORY_RAG.md)
- [Detailed code-chunking guide](docs/CODE_CHUNKING.md)
- [Artifact flow overview](docs/ARTIFACT_FLOW.md)
- [Discovery Agent state and artifacts](docs/DISCOVERY_AGENT_STATE_AND_ARTIFACTS.md)
- [Repository RAG saved index and handoff](docs/REPOSITORY_RAG_STATE_AND_ARTIFACTS.md)
- [API Analyzer state and artifacts](docs/API_ANALYZER_STATE_AND_ARTIFACTS.md)
- [ACORD RAG state and artifacts](docs/ACORD_RAG_STATE_AND_ARTIFACTS.md)

Phase 1 deterministic discovery is complete and Phase 2 API analysis is in progress. A
synthetic regional Quote API and OpenAPI input are available under
[`fixtures/RegionalQuoteApi`](fixtures/RegionalQuoteApi). See the
[user guide](docs/USER_GUIDE.md) for complete installation, .NET dependency, UI, CLI,
configuration, verification, and troubleshooting instructions.

## Quick start

The Streamlit application supports repository plus optional OpenAPI discovery; a separate
Repository RAG tab indexes code for source-linked retrieval. The API Analyzer Agent can reuse
that saved index to interpret selected code or enrich a discovered API. The independent ACORD
workspace accepts an authorized OpenAPI 3 YAML/JSON reference, generates Discovery-equivalent
artifact views, and builds its own local retrieval index without performing alignment.

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e ".[dev]"
.\.venv\Scripts\python.exe -m pytest
.\.venv\Scripts\python.exe -m streamlit run streamlit_app.py
```

## Baseline verification

Run these commands at milestone completion:

```powershell
.\.venv\Scripts\python.exe -m ruff check .
.\.venv\Scripts\python.exe -m ruff format --check .
.\.venv\Scripts\python.exe -m pytest
dotnet restore CanonicalModelGenerator.sln
dotnet format CanonicalModelGenerator.sln --verify-no-changes --no-restore
dotnet build CanonicalModelGenerator.sln --no-restore
dotnet test dotnet/tests/CanonicalModel.Discovery.Tests/CanonicalModel.Discovery.Tests.csproj --no-build
```

The .NET projects target `net8.0`. `RollForward=Major` permits local execution on the installed .NET 10 runtime; CI and production should use the .NET 8 runtime baseline.

## Run deterministic discovery

Use an output directory outside the analyzed repository. Loading an MSBuild project may execute its configured build tasks, so only analyze repositories you trust or run the command in an isolated environment.

```powershell
.\.venv\Scripts\python.exe -m canonical_model_generator.cli `
  --region IN `
  --system regional-quote-api-fixture `
  --repository fixtures/RegionalQuoteApi `
  --project fixtures/RegionalQuoteApi/src/RegionalQuoteApi/RegionalQuoteApi.csproj `
  --openapi fixtures/RegionalQuoteApi/openapi/quote-api.yaml `
  --output output/discovery
```

The command generates `discovery-model.json`, `api-catalog.json`, `data-model.json`, `relationship-graph.json`, `validation-enums.json`, and `lineage.json`.

## Current limits

- RAG call/reference links are syntax-derived candidates, not verified execution paths.
- Code-to-business-meaning interpretation requires a working OpenAI key and source-sharing acknowledgement; generated claims require human review.
- Deep persistence, integration, security, and call-path discovery are not yet accepted capabilities.
- ACORD ingestion is implemented, but ACORD-to-regional alignment and canonical generation are not.
- See [repository RAG](docs/REPOSITORY_RAG.md) for indexing limits, retrieval behavior, and the code-chunking example.
