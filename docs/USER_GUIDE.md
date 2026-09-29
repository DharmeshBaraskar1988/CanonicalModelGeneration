# Canonical Model Generator User Guide

This guide explains how to install the prerequisites, restore the .NET and Python
dependencies, run the application, and verify a local setup.

For repository input, optional YAML reconciliation, and code retrieval, see [Repository RAG](REPOSITORY_RAG.md).
For the system boundary, LLM payload inventory, and credit controls, see
[Architecture and LLM data flow](ARCHITECTURE_AND_LLM_DATA_FLOW.md).

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
repositories. The UI requires explicit acknowledgement before specification details or bounded,
redacted code context is sent to OpenAI. The API Analyzer tab also accepts a password-masked,
session-only key override when the configured key is missing or rejected; it is not written to
an artifact.

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

Run the three tabs in order:

1. In **Discovery Agent**, choose the region and application name, then upload the required
   repository ZIP and, optionally, an OpenAPI document. A successful run records the application
   profile in this browser session.
2. Open **Repository RAG** and build the repository index. Each build creates a fresh, isolated
   index for the currently selected upload.
3. In **Phase 2 API Analyzer**, select the completed application by name, region, and repository
   ZIP. Check its RAG status, provide a valid OpenAI key (or session override), choose the model,
   and acknowledge source sharing. The page lists any missing requirements before enabling
   **Run API Analyzer Agent**. After a completed or failed run, the same selected application
   shows **Run API Analyzer again for selected application**; no new upload is required.

The application selector restores that run's Discovery artifact, repository ZIP, and RAG index;
it does not mix results from different repositories. Every Discovery submission starts a new
session run, even if the upload is identical to a previous one, and does not inherit an old index.
Completed application profiles, trusted ZIPs, artifacts, and RAG associations persist under ignored
`.applications/<run-id>/` local storage and can be reopened after a server restart. API keys and
source-sharing consent are never persisted. An available key is not proof it is valid: the Analyzer
checks provider access when the run starts.

### Independent ACORD ingestion

Open **ACORD ingestion** separately from the four-stage regional workflow:

1. Enter a stable reference label and the approved ACORD version.
2. Upload an OpenAPI 3 JSON, YAML, or YML document up to 10 MB.
3. Confirm that the document is authorized for local ingestion and indexing.
4. Select **Build ACORD RAG index**. The first local embedding run may need to obtain the pinned
   Sentence Transformer model if it is not already cached.
5. Inspect or download the API Catalog, Data Model, Relationship Graph, Validation and Enums, and
   Lineage views. Use **Inspect ACORD retrieval** to verify the endpoint/entity chunks and source
   pointers that a later alignment agent would receive.

Successful records persist under ignored `.acord/<run-id>/` storage and can be reopened after an app
restart. This directory contains the uploaded reference and must be protected according to the
reference's license and your data-handling policy. The pipeline does not call an LLM, compare the
reference with regional APIs, or produce canonical mappings.

## 7. Run deterministic discovery from the CLI

The CLI requires a repository and project, accepts an optional OpenAPI document, and requires an
output directory. This example analyzes the included Quote API fixture using both sources:

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

Use the API Analyzer's session-only key override or replace `.env` with an active, approved
`OPENAI_API_KEY`, then retry. Phase 1 Discovery and local Repository RAG remain usable without
an OpenAI key.

### ACORD ingestion cannot build the local index

Confirm that the upload is an OpenAPI 3.x document, not a standalone JSON Schema or Swagger 2 file.
Check network access for the first download of the pinned local Sentence Transformer model, then
retry. Existing complete records remain available under **Open a previous ACORD ingestion**.
