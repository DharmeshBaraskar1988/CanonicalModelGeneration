# Canonical Model Generator User Guide

This guide explains how to install the prerequisites, restore the .NET and Python
dependencies, run the application, and verify a local setup.

## 1. Prerequisites

Install the following tools:

- Git.
- Python 3.12 or newer.
- The .NET 8 SDK or a newer SDK that can build `net8.0` projects.

The project targets .NET 8. The repository sets `RollForward=Major`, so the installed
.NET 10 SDK/runtime can also build and run the current projects. The .NET SDK includes
the runtime, MSBuild, and the `dotnet` command; no separate Visual Studio installation
or .NET workload is required.

### Windows installation

Install the recommended versions from PowerShell:

```powershell
winget install --id Git.Git -e
winget install --id Python.Python.3.12 -e
winget install --id Microsoft.DotNet.SDK.8 -e
```

Close and reopen PowerShell after installation, then confirm the tools are available:

```powershell
git --version
python --version
dotnet --info
dotnet --list-sdks
```

If `winget` is unavailable, use the official installers:

- Git: <https://git-scm.com/downloads>
- Python: <https://www.python.org/downloads/>
- .NET 8 SDK: <https://dotnet.microsoft.com/download/dotnet/8.0>

On Linux or macOS, install Python 3.12+ and the .NET 8 SDK using the platform-specific
instructions linked from the same official download pages. Replace the Windows virtual
environment paths in the commands below with `.venv/bin/python`.

## 2. Clone the repository

```powershell
git clone https://github.com/DharmeshBaraskar1988/CanonicalModelGeneration.git
Set-Location CanonicalModelGeneration
```

## 3. Install Python dependencies

Create a project-local virtual environment and install the application plus development
dependencies:

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install --upgrade pip
.\.venv\Scripts\python.exe -m pip install -e ".[dev]"
```

The editable install provides Streamlit, LangGraph, Pydantic, OpenAI, ChromaDB, PyYAML,
pytest, Ruff, and the `canonical-discovery` command.

## 4. Restore and build the .NET dependencies

Restore all NuGet packages declared by the Roslyn analyzer and its tests:

```powershell
dotnet restore CanonicalModelGenerator.sln
dotnet build CanonicalModelGenerator.sln --no-restore
```

`dotnet restore` downloads the pinned Microsoft.Build, Roslyn workspace, test SDK, and
xUnit packages from the configured NuGet sources. No manual package installation is
needed. Internet access is required for the first restore unless those packages already
exist in the local NuGet cache.

To restore and build only the sample Quote API:

```powershell
dotnet restore fixtures/RegionalQuoteApi/RegionalQuoteApi.sln
dotnet build fixtures/RegionalQuoteApi/RegionalQuoteApi.sln --no-restore
```

## 5. Configure the API Analyzer Agent (optional)

Phase 1 deterministic discovery does not require an OpenAI API key. Phase 2 semantic
analysis does. Create a local `.env` file in the repository root:

```dotenv
OPENAI_API_KEY=your-approved-api-key
OPENAI_MODEL=your-approved-model
```

The `.env` file is ignored by Git. Do not commit API keys or place them in uploaded
repositories. The UI requires explicit acknowledgement before bounded, redacted source
context is sent to OpenAI.

## 6. Run the Streamlit application

```powershell
.\.venv\Scripts\python.exe -m streamlit run streamlit_app.py
```

Open the local address printed by Streamlit, normally <http://localhost:8501>. In the
Discovery Agent tab, upload a trusted repository ZIP and optionally an OpenAPI JSON or
YAML document. Loading an MSBuild project can execute its configured build tasks, so use
an isolated environment for code that you do not trust.

After successful discovery, the UI provides these operator-facing artifacts:

- API Catalog
- Data Model
- Relationship Graph
- Validation and Enums
- Lineage

The API Analyzer Agent tab becomes available after Phase 1 succeeds. It can generate an
enriched OpenAPI document and semantic metadata when a valid OpenAI configuration is
present.

## 7. Run deterministic discovery from the CLI

The current CLI requires a repository, a `.csproj`, an OpenAPI document, and an output
directory. This example analyzes the included Quote API fixture:

```powershell
.\.venv\Scripts\python.exe -m canonical_model_generator.cli `
  --region IN `
  --system regional-quote-api-fixture `
  --repository fixtures/RegionalQuoteApi `
  --project fixtures/RegionalQuoteApi/src/RegionalQuoteApi/RegionalQuoteApi.csproj `
  --openapi fixtures/RegionalQuoteApi/openapi/quote-api.yaml `
  --output output/discovery
```

Keep the output directory outside the repository being analyzed. The command writes the
internal Discovery Model plus the API catalog, data model, relationship graph,
validation/enum, and lineage artifacts.

## 8. Verify the installation

Run the complete local quality gate:

```powershell
.\.venv\Scripts\python.exe -m ruff check .
.\.venv\Scripts\python.exe -m ruff format --check .
.\.venv\Scripts\python.exe -m pytest
dotnet format CanonicalModelGenerator.sln --verify-no-changes --no-restore
dotnet build CanonicalModelGenerator.sln --no-restore
dotnet test dotnet/tests/CanonicalModel.Discovery.Tests/CanonicalModel.Discovery.Tests.csproj --no-build
```

If the solution has not been restored yet, run `dotnet restore
CanonicalModelGenerator.sln` before commands that use `--no-restore`.

## 9. Troubleshooting

### `git`, `python`, or `dotnet` is not recognized

Open a new terminal after installation. If the command is still unavailable, add its
installation directory to `PATH` or invoke the executable by its absolute path.

### A .NET 8 targeting pack or SDK cannot be found

Install the .NET 8 SDK and confirm that it appears in `dotnet --list-sdks`. A runtime-only
installation is not enough to compile the Roslyn analyzer.

### NuGet restore fails

Confirm network/proxy access to the configured NuGet sources and retry:

```powershell
dotnet nuget list source
dotnet restore CanonicalModelGenerator.sln
```

### Python installation fails

Confirm that the virtual environment is active or call its Python executable directly.
Then upgrade pip and retry the editable installation.

### Phase 2 reports an authentication error

Check that `.env` contains an active, approved `OPENAI_API_KEY`, restart Streamlit, and
retry the provider preflight. Phase 1 discovery remains usable without the key.
