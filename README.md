# Canonical Model Generator

This project will discover the structure and behavior of regional insurance APIs and produce a normalized, traceable Discovery Model. Later releases may use that foundation for semantic alignment and canonical-model generation.

## Project tracking

- [Implementation plan](docs/IMPLEMENTATION_PLAN.md)
- [Current status](docs/STATUS.md)
- [Next steps](docs/NEXT_STEPS.md)
- [Architecture decisions](docs/DECISIONS.md)
- [Installation and user guide](docs/USER_GUIDE.md)

Phase 1 deterministic discovery is complete and Phase 2 API analysis is in progress. A
synthetic regional Quote API and OpenAPI input are available under
[`fixtures/RegionalQuoteApi`](fixtures/RegionalQuoteApi). See the
[user guide](docs/USER_GUIDE.md) for complete installation, .NET dependency, UI, CLI,
configuration, verification, and troubleshooting instructions.

## Quick start

The Streamlit application runs deterministic repository discovery and exposes the Phase 2
API Analyzer Agent after a successful Phase 1 run.

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

## Discovery MVP limitations

- The Roslyn slice supports ASP.NET Core controllers used by the selected fixture; minimal APIs and classic ASP.NET Web API are not yet supported.
- OpenAPI discovery supports local references and `allOf`; external references, `oneOf`, and `anyOf` are reported or rejected.
- Service call-path extraction (`CALLS`) remains optional and is not implemented.
- OpenAPI inline enums are preserved as field constraints rather than promoted to named enums, which can produce a visible reconciliation warning.
- The Streamlit page remains intake-only; run discovery through the CLI.
