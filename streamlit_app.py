from __future__ import annotations

import json
import os
import sys
from collections.abc import Callable
from io import BytesIO
from pathlib import Path, PurePosixPath
from tempfile import TemporaryDirectory
from uuid import uuid4
from zipfile import ZIP_DEFLATED, ZipFile

import streamlit as st
from dotenv import load_dotenv
from streamlit.typing import UploadedFile

sys.path.insert(0, str(Path(__file__).resolve().parent / "src"))
load_dotenv(Path(__file__).resolve().parent / ".env", override=True)

from canonical_model_generator.api_analyzer import (  # noqa: E402
    OpenAISemanticProvider,
    inspect_retrieved_code,
    inspect_retrieved_target,
    normalize_regional_entity,
    run_api_analyzer_agent,
)
from canonical_model_generator.application_history import (  # noqa: E402
    RUN_ID_PATTERN,
    load_application_records,
    save_application_record,
)
from canonical_model_generator.discovery_agent.artifacts import generate_artifacts  # noqa: E402
from canonical_model_generator.discovery_agent.model import DiscoveryModel  # noqa: E402
from canonical_model_generator.discovery_agent.openapi import discover_openapi  # noqa: E402
from canonical_model_generator.discovery_agent.reconcile import reconcile  # noqa: E402
from canonical_model_generator.discovery_agent.roslyn import (  # noqa: E402
    extract_roslyn,
    merge_roslyn_models,
)
from canonical_model_generator.discovery_agent.workflow import run_discovery  # noqa: E402
from canonical_model_generator.intake import (  # noqa: E402
    IntakeError,
    inspect_repository_zip,
    validate_openapi,
)
from canonical_model_generator.regional_catalog import (  # noqa: E402
    regional_catalog_rows,
    regional_domain_tree,
    regional_model_tree,
)
from canonical_model_generator.repository_rag.embeddings import (  # noqa: E402
    LOCAL_MODEL,
    OPENAI_MODELS,
    EmbeddingConfig,
    create_embedder,
)
from canonical_model_generator.repository_rag.index import ChromaRepositoryIndex  # noqa: E402

st.set_page_config(
    page_title="Insurance Canonical Model Platform",
    page_icon=":material/account_tree:",
    layout="wide",
)

APPLICATION_HISTORY_ROOT = Path(__file__).resolve().parent / ".applications"

DISCOVERY_ARTIFACTS = {
    "API Catalog": "api-catalog.json",
    "Data Model": "data-model.json",
    "Relationship Graph": "relationship-graph.json",
    "Validation and enums": "validation-enums.json",
    "Lineage": "lineage.json",
}

REGIONS = {
    "EU": "European Union",
    "IN": "India",
    "GB": "United Kingdom",
    "US": "United States",
    "CA": "Canada",
    "AU": "Australia",
    "SG": "Singapore",
}

st.session_state.setdefault("discovery_artifacts", {})
st.session_state.setdefault("discovery_projects", [])
st.session_state.setdefault("discovery_model", None)
st.session_state.setdefault("repository_archive", None)
st.session_state.setdefault("phase_2_unlocked", False)
st.session_state.setdefault("phase_2_artifacts", {})
st.session_state.setdefault("phase_2_error", None)
st.session_state.setdefault("rag_store_path", None)
st.session_state.setdefault("rag_manifest", None)
st.session_state.setdefault("rag_results", [])
st.session_state.setdefault("rag_semantics", None)
st.session_state.setdefault("application_runs", {})
st.session_state.setdefault("active_application_id", None)
st.session_state.setdefault("regional_normalizations", {})
if not st.session_state["application_runs"]:
    st.session_state["application_runs"] = load_application_records(APPLICATION_HISTORY_ROOT)


def build_artifact_bundle(artifacts: dict[str, bytes]) -> bytes:
    bundle = BytesIO()
    with ZipFile(bundle, "w", ZIP_DEFLATED) as archive:
        for label, content in artifacts.items():
            archive.writestr(DISCOVERY_ARTIFACTS[label], content)
    return bundle.getvalue()


def build_named_bundle(artifacts: dict[str, bytes]) -> bytes:
    bundle = BytesIO()
    with ZipFile(bundle, "w", ZIP_DEFLATED) as archive:
        for filename, content in artifacts.items():
            archive.writestr(filename, content)
    return bundle.getvalue()


def openai_api_key() -> str | None:
    try:
        configured = st.secrets.get("OPENAI_API_KEY")
    except (FileNotFoundError, KeyError):
        configured = None
    value = configured or os.getenv("OPENAI_API_KEY")
    return value.strip() if value else None


def activate_application(application_id: str) -> None:
    """Restore one completed Discovery/RAG run without carrying another run's artifacts."""
    run = st.session_state["application_runs"][application_id]
    st.session_state["active_application_id"] = application_id
    for key in (
        "discovery_artifacts",
        "discovery_projects",
        "discovery_model",
        "repository_archive",
        "rag_store_path",
        "rag_manifest",
        "phase_2_artifacts",
    ):
        st.session_state[key] = run[key]
    st.session_state["phase_2_unlocked"] = True
    st.session_state["phase_2_error"] = run.get("phase_2_error")
    st.session_state["rag_results"] = []
    st.session_state["rag_semantics"] = None
    st.session_state["phase_2_source_consent"] = False


def persist_application(application_id: str) -> None:
    # AppTest fixtures may use short readable IDs; production records use UUID hex IDs.
    if not RUN_ID_PATTERN.fullmatch(application_id):
        return
    save_application_record(
        APPLICATION_HISTORY_ROOT,
        application_id,
        st.session_state["application_runs"][application_id],
    )


def save_application(
    *,
    discovery_model: bytes,
    discovery_artifacts: dict[str, bytes],
    projects: list[str],
    repository_archive: bytes | None,
    repository_name: str,
    openapi_name: str,
) -> str:
    model = DiscoveryModel.model_validate_json(discovery_model)
    # A submission is a new analysis run even when its files match a prior upload.
    # It must never inherit another run's RAG index or Phase 2 artifacts.
    application_id = uuid4().hex
    st.session_state["application_runs"][application_id] = {
        "profile": {
            "region": model.region,
            "application": model.system,
            "repository": repository_name,
            "openapi": openapi_name,
        },
        "discovery_artifacts": discovery_artifacts,
        "discovery_projects": projects,
        "discovery_model": discovery_model,
        "repository_archive": repository_archive,
        "rag_store_path": None,
        "rag_manifest": None,
        "phase_2_artifacts": {},
        "phase_2_error": None,
    }
    persist_application(application_id)
    activate_application(application_id)
    return application_id


def run_uploaded_semantic_generation(
    *,
    repository_archive: bytes | None,
    discovery_artifact: bytes,
    provider: OpenAISemanticProvider,
    progress: Callable[[str], None] | None = None,
    rag_store_path: Path | None = None,
    embedder=None,
) -> dict[str, bytes]:
    if repository_archive is None:
        return run_api_analyzer_agent(discovery_artifact, None, provider, progress)
    inspect_repository_zip(repository_archive)
    with TemporaryDirectory(prefix="canonical-semantic-openapi-") as temporary:
        repository = Path(temporary) / "repository"
        repository.mkdir()
        with ZipFile(BytesIO(repository_archive)) as zip_file:
            zip_file.extractall(repository)
        return run_api_analyzer_agent(
            discovery_artifact,
            repository,
            provider,
            progress,
            rag_store_path=rag_store_path,
            embedder=embedder,
        )


def select_web_projects(projects: tuple[str, ...], controllers: tuple[str, ...]) -> list[str]:
    ownership = {project: 0 for project in projects}
    project_parents = {project: PurePosixPath(project).parent for project in projects}
    for controller in controllers:
        controller_path = PurePosixPath(controller)
        candidates = [
            project
            for project, parent in project_parents.items()
            if controller_path.is_relative_to(parent)
        ]
        if candidates:
            owner = max(candidates, key=lambda item: len(project_parents[item].parts))
            ownership[owner] += 1

    selected = [
        project
        for project, count in ownership.items()
        if (
            count > 0
            or "api" in PurePosixPath(project).stem.lower()
            or PurePosixPath(project).stem.lower() == "web"
        )
        and "test" not in project.lower()
    ]
    return sorted(selected)


def run_uploaded_discovery(
    *,
    region: str,
    system: str,
    repository_file: UploadedFile | None,
    openapi_file: UploadedFile | None,
) -> tuple[dict[str, bytes], list[str], bytes]:
    if repository_file is None:
        if openapi_file is None:
            raise IntakeError("Provide a repository ZIP or an OpenAPI document")
        validate_openapi(openapi_file.getvalue(), openapi_file.name)
        with TemporaryDirectory(prefix="canonical-openapi-") as temporary:
            workspace = Path(temporary)
            specification = workspace / Path(openapi_file.name).name
            specification.write_bytes(openapi_file.getvalue())
            output = workspace / "output"
            state = run_discovery(
                region=region, system=system, openapi=specification, output=output
            )
            if state.get("errors"):
                raise IntakeError("; ".join(state["errors"]))
            return (
                {
                    label: (output / name).read_bytes()
                    for label, name in DISCOVERY_ARTIFACTS.items()
                },
                [],
                (output / "discovery-model.json").read_bytes(),
            )
    archive = repository_file.getvalue()
    inventory = inspect_repository_zip(archive)
    if not inventory.projects:
        raise IntakeError("The repository ZIP must contain a .csproj file.")
    if not inventory.controllers:
        raise IntakeError("The repository ZIP must contain at least one controller.")
    with TemporaryDirectory(prefix="canonical-discovery-") as temporary:
        workspace = Path(temporary)
        repository = workspace / "repository"
        output = workspace / "output"
        repository.mkdir()
        with ZipFile(BytesIO(archive)) as zip_file:
            zip_file.extractall(repository)

        selected_projects = select_web_projects(inventory.projects, inventory.controllers)
        if not selected_projects:
            raise IntakeError("No non-test project owns the discovered controller files.")
        roslyn_models = [
            extract_roslyn(repository / project, repository, region.strip(), system.strip())
            for project in selected_projects
        ]
        model = merge_roslyn_models(roslyn_models)
        openapi = None
        if openapi_file is not None:
            validate_openapi(openapi_file.getvalue(), openapi_file.name)
            openapi = repository / "uploaded-openapi" / Path(openapi_file.name).name
            openapi.parent.mkdir()
            openapi.write_bytes(openapi_file.getvalue())
        elif inventory.openapi_candidates:
            openapi = repository / inventory.openapi_candidates[0]

        if openapi is None:
            if not model.operations and not model.entities:
                raise IntakeError(
                    "No supported controllers or endpoint contract models were discovered in the "
                    "controller projects. "
                    "The current analyzer supports ASP.NET Core MVC controller projects."
                )
            generate_artifacts(model, output)
        else:
            openapi_model = discover_openapi(openapi, region.strip(), system.strip(), repository)
            model = reconcile(model, openapi_model)
            if not model.operations and not model.entities:
                raise IntakeError(
                    "No supported operations or endpoint contract models were discovered in the "
                    "repository."
                )
            generate_artifacts(model, output)

        artifacts = {
            label: (output / filename).read_bytes()
            for label, filename in DISCOVERY_ARTIFACTS.items()
        }
        discovery_model = (output / "discovery-model.json").read_bytes()
        return artifacts, selected_projects, discovery_model


# Persist UUID-backed runs that were already in the live session when history was introduced.
for existing_application_id in st.session_state["application_runs"]:
    if (
        RUN_ID_PATTERN.fullmatch(existing_application_id)
        and not (APPLICATION_HISTORY_ROOT / existing_application_id / "record.json").is_file()
    ):
        persist_application(existing_application_id)


if st.session_state["discovery_model"] is not None and not st.session_state["application_runs"]:
    uploaded_repository = st.session_state.get("repository_zip")
    uploaded_openapi = st.session_state.get("openapi_document")
    save_application(
        discovery_model=st.session_state["discovery_model"],
        discovery_artifacts=st.session_state["discovery_artifacts"],
        projects=st.session_state["discovery_projects"],
        repository_archive=st.session_state["repository_archive"],
        repository_name=(
            uploaded_repository.name if uploaded_repository else "Current repository ZIP"
        ),
        openapi_name=uploaded_openapi.name if uploaded_openapi else "Not uploaded",
    )
elif (
    st.session_state["application_runs"]
    and st.session_state["active_application_id"] not in st.session_state["application_runs"]
):
    activate_application(next(iter(st.session_state["application_runs"])))

st.title("Insurance Canonical Model platform")

discovery_tab, rag_tab, phase_two_tab, regional_tab = st.tabs(
    [
        ":material/account_tree: Discovery Agent",
        ":material/search: Repository RAG",
        ":material/manage_search: Phase 2 API Analyzer",
        ":material/public: Regional catalog",
    ]
)

with discovery_tab:
    st.header("Discovery Agent")
    st.caption(
        "Create a regional application profile, then provide the trusted source inputs to "
        "build its discovery artifacts."
    )
    if st.session_state["application_runs"]:
        with st.expander("Open a previous application", expanded=False):
            historical_runs = st.session_state["application_runs"]
            historical_ids = list(historical_runs)
            historical_id = st.selectbox(
                "Saved application",
                historical_ids,
                format_func=lambda item: (
                    f"{historical_runs[item]['profile']['application']} · "
                    f"{historical_runs[item]['profile']['region']} · "
                    f"{historical_runs[item]['profile']['repository']} [{item[:6]}]"
                ),
                key="historical_application",
            )
            if st.button(
                "Open saved application",
                icon=":material/history:",
                key="open_historical_application",
            ):
                activate_application(historical_id)
                st.rerun()
    with st.form("discovery_agent", border=True):
        st.subheader("Application details", anchor=False)
        st.caption(
            "These values identify the source application in every generated artifact. "
            "Use a stable name that your teams will recognize."
        )
        region_column, application_column = st.columns(2, gap="large")
        with region_column:
            region = st.selectbox(
                "Region",
                options=list(REGIONS),
                index=None,
                format_func=lambda code: f"{code} — {REGIONS.get(code, code)}",
                placeholder="Select or enter a region code",
                accept_new_options=True,
                help=(
                    "Choose a common ISO country code or enter the regional code used by your "
                    "organization, such as EU or LATAM."
                ),
                key="region",
            )
        with application_column:
            system = st.text_input(
                "Application name",
                placeholder="regional-quote-api",
                help=(
                    "A stable source-system name used to identify this application in generated "
                    "models and lineage."
                ),
                key="system",
            )

        st.subheader("Source inputs", anchor=False)
        st.caption("Upload a repository ZIP, an OpenAPI YAML/JSON document, or both.")
        repository_column, contract_column = st.columns(2, gap="large")
        with repository_column:
            repository_file: UploadedFile | None = st.file_uploader(
                "Trusted .NET repository ZIP",
                type="zip",
                max_upload_size=100,
                help=(
                    "Optional when providing OpenAPI. Roslyn/MSBuild analyzes the repository "
                    "as trusted code."
                ),
                key="repository_zip",
            )
            st.caption("Repository input · ZIP · Up to 100 MB")
        with contract_column:
            openapi_file: UploadedFile | None = st.file_uploader(
                "OpenAPI document",
                type=["json", "yaml", "yml"],
                max_upload_size=10,
                help=(
                    "Can be used alone. Without a repository, results describe the specification "
                    "and implementation code retrieval is unavailable."
                ),
                key="openapi_document",
            )
            st.caption("Specification input · JSON or YAML · Up to 10 MB")

        submitted = st.form_submit_button(
            "Analyze application", type="primary", icon=":material/play_arrow:"
        )

    if submitted:
        if (
            not region
            or not region.strip()
            or not system.strip()
            or not (repository_file or openapi_file)
        ):
            st.error(
                "Region, application name, and either a repository ZIP or OpenAPI are required."
            )
        else:
            try:
                with st.status("Running deterministic discovery...", expanded=True) as status:
                    st.write("Inspecting and extracting the trusted repository")
                    st.write("Running Roslyn and optional OpenAPI discovery")
                    artifacts, selected_projects, discovery_model = run_uploaded_discovery(
                        region=region,
                        system=system,
                        repository_file=repository_file,
                        openapi_file=openapi_file,
                    )
                    st.write("Validating and generating five artifacts")
                    save_application(
                        discovery_model=discovery_model,
                        discovery_artifacts=artifacts,
                        projects=selected_projects,
                        repository_archive=(
                            repository_file.getvalue() if repository_file else None
                        ),
                        repository_name=repository_file.name if repository_file else "OpenAPI only",
                        openapi_name=openapi_file.name if openapi_file else "Not uploaded",
                    )
                    status.update(label="Discovery complete", state="complete", expanded=False)
            except (IntakeError, OSError, RuntimeError, ValueError) as exc:
                st.error(str(exc))

    artifacts: dict[str, bytes] = st.session_state["discovery_artifacts"]
    if artifacts:
        active_run = st.session_state["application_runs"][st.session_state["active_application_id"]]
        profile = active_run["profile"]
        with st.container(border=True):
            st.badge("Discovery complete", color="green", icon=":material/check:")
            profile_columns = st.columns(3)
            profile_columns[0].metric("Region", profile["region"])
            profile_columns[1].metric("Application", profile["application"])
            profile_columns[2].metric(
                "Projects analyzed", len(st.session_state["discovery_projects"])
            )
            st.caption(f"Repository: {profile['repository']}")
            st.caption("Projects: " + ", ".join(st.session_state["discovery_projects"]))
        if st.session_state["repository_archive"] is None:
            st.info(
                "These artifacts describe the uploaded specification. "
                "Repository code was not supplied."
            )
        st.warning(
            "Current entity coverage is limited to user-authored ViewModels and concrete request/"
            "response models reachable from API endpoints. Base infrastructure classes, DTOs, "
            "domain types, generated types, and unrelated models are excluded. "
            "Deep call paths, persistence, mappings, integrations, security, and Razor Pages "
            "remain open gaps. For YAML-only input, the document's schemas are retained.",
            icon=":material/radar:",
        )
        st.subheader("Discovery artifact tree")
        st.mermaid_chart(
            """
flowchart TD
    REPO[Repository or OpenAPI document] --> AGENT[Discovery Agent]
    AGENT --> CATALOG[API Catalog]
    AGENT --> DATA[Data Model]
    AGENT --> GRAPH[Relationship Graph]
    AGENT --> RULES[Validation and Enums]
    AGENT --> LINEAGE[Lineage]
"""
        )

        for start in range(0, len(DISCOVERY_ARTIFACTS), 3):
            with st.container(horizontal=True):
                for label in list(DISCOVERY_ARTIFACTS)[start : start + 3]:
                    filename = DISCOVERY_ARTIFACTS[label]
                    with st.container(border=True):
                        st.badge("Generated", color="green", icon=":material/check:")
                        st.markdown(f"**{label}**")
                        st.download_button(
                            "Download JSON",
                            data=artifacts[label],
                            file_name=filename,
                            mime="application/json",
                            icon=":material/download:",
                            key=f"download_{filename}",
                        )

        st.download_button(
            "Download all five artifacts",
            data=build_artifact_bundle(artifacts),
            file_name="discovery-artifacts.zip",
            mime="application/zip",
            type="primary",
            icon=":material/folder_zip:",
            key="download_all_discovery_artifacts",
        )
        preview_label = st.selectbox("Preview artifact", list(artifacts), key="artifact_preview")
        st.json(json.loads(artifacts[preview_label]), expanded=2)

with rag_tab:
    st.header("Repository RAG")
    st.caption(
        "Build reusable code context, then inspect what an endpoint, model or field retrieves. "
        "Code is grouped by file, type and member, with parent and relationship links."
    )
    active_id = st.session_state["active_application_id"]
    if active_id:
        profile = st.session_state["application_runs"][active_id]["profile"]
        st.info(
            f"Selected application: {profile['application']} · {profile['region']} · "
            f"{profile['repository']}"
        )
    embedding_provider = st.selectbox(
        "Embedding provider", ["Sentence Transformer (local)", "OpenAI"], key="rag_provider"
    )
    embedding_name = st.selectbox(
        "Embedding model",
        [LOCAL_MODEL] if embedding_provider.startswith("Sentence") else list(OPENAI_MODELS),
        key="rag_embedding_model",
    )
    cloud_embedding_consent = (
        st.checkbox(
            "Allow redacted repository chunks to be sent to OpenAI for embedding.",
            key="rag_cloud_consent",
        )
        if embedding_provider == "OpenAI"
        else False
    )
    if embedding_provider.startswith("Sentence"):
        st.caption("Runs on this computer. The first run downloads the embedding model.")
    else:
        st.caption("Indexing sends all included redacted chunks to OpenAI and incurs API usage.")
    repository_bytes = st.session_state["repository_archive"]
    if repository_bytes is None:
        st.info("Upload a repository here to build code retrieval independently of discovery.")
        rag_upload = st.file_uploader("Repository for code retrieval", type="zip", key="rag_upload")
        repository_bytes = rag_upload.getvalue() if rag_upload else None
    st.caption(
        "Each build creates a fresh index for the currently selected upload. "
        "The API Analyzer uses only that application's index."
    )
    if st.button("Build repository index", key="build_rag", disabled=repository_bytes is None):
        rag_index = None
        try:
            profile = EmbeddingConfig(
                provider="openai" if embedding_provider == "OpenAI" else "sentence_transformer",
                model=embedding_name,
            )
            adapter = create_embedder(
                profile, api_key=openai_api_key(), allow_source_sharing=cloud_embedding_consent
            )
            inspect_repository_zip(repository_bytes)
            with st.status("Building repository index...", expanded=True) as status:
                with TemporaryDirectory(prefix="canonical-rag-") as temporary:
                    repository_root = Path(temporary)
                    with ZipFile(BytesIO(repository_bytes)) as archive:
                        archive.extractall(repository_root)
                    run_directory = active_id or "standalone"
                    storage = Path(__file__).resolve().parent / ".rag" / run_directory / uuid4().hex
                    rag_index = ChromaRepositoryIndex(storage, adapter)
                    model = (
                        DiscoveryModel.model_validate_json(st.session_state["discovery_model"])
                        if st.session_state["repository_archive"] is not None
                        else None
                    )
                    rag_index.ingest(repository_root, model, st.write)
                    st.session_state["rag_store_path"] = str(storage)
                    st.session_state["rag_manifest"] = rag_index.manifest
                    if st.session_state["repository_archive"] is not None and active_id:
                        run = st.session_state["application_runs"][active_id]
                        run["rag_store_path"] = str(storage)
                        run["rag_manifest"] = rag_index.manifest
                        run["phase_2_artifacts"] = {}
                        run["phase_2_error"] = None
                        st.session_state["phase_2_artifacts"] = {}
                        st.session_state["phase_2_error"] = None
                        persist_application(active_id)
                    st.session_state["rag_results"] = []
                    st.session_state["rag_semantics"] = None
                status.update(label="Repository index ready", state="complete", expanded=False)
        except Exception as exc:
            st.error(f"Repository indexing failed: {exc}")
        finally:
            if rag_index is not None:
                rag_index.close()

    rag_manifest = st.session_state["rag_manifest"]
    if rag_manifest:
        stats = rag_manifest["stats"]
        with st.container(horizontal=True):
            st.metric("Files indexed", stats["filesIndexed"])
            st.metric("Code chunks", stats["chunksIndexed"])
            st.metric("Relationships", stats["relationshipsIndexed"])
        st.caption(f"Saved locally: {st.session_state['rag_store_path']}")
        st.caption(f"Embedding model: {rag_manifest['embedding']['model']}")
        st.download_button(
            "Download RAG manifest",
            json.dumps(rag_manifest, indent=2),
            file_name="rag-manifest.json",
            mime="application/json",
        )
        if stats["gaps"]:
            with st.expander("Index coverage gaps"):
                st.json(stats["gaps"])
        target_kind = st.selectbox(
            "Retrieve by", ["endpoint", "entity", "attribute", "enum", "code query"]
        )
        candidates = [t for t in rag_manifest["targets"] if t["kind"] == target_kind]
        target_map = {t["id"]: t for t in candidates}
        target_id = (
            st.selectbox(
                "Discovered target",
                list(target_map),
                format_func=lambda key: target_map[key]["label"],
                key=f"rag_target_{target_kind}",
            )
            if candidates
            else None
        )
        query_text = st.text_input(
            "Code query", placeholder="QuoteService.Create or QuoteResponse.Premium"
        )
        if st.button("Retrieve code context", key="retrieve_rag"):
            rag_index = None
            try:
                profile = EmbeddingConfig.model_validate(rag_manifest["embedding"])
                adapter = create_embedder(
                    profile, api_key=openai_api_key(), allow_source_sharing=cloud_embedding_consent
                )
                rag_index = ChromaRepositoryIndex(Path(st.session_state["rag_store_path"]), adapter)
                query = query_text.strip() or (target_map[target_id]["label"] if target_id else "")
                st.session_state["rag_results"] = rag_index.query(query, subject_id=target_id)
                st.session_state["rag_semantics"] = None
            except Exception as exc:
                st.error(f"Code retrieval failed: {exc}")
            finally:
                if rag_index is not None:
                    rag_index.close()
        for snippet in st.session_state["rag_results"]:
            with st.expander(f"{snippet['symbol']} — {snippet['path']}:{snippet['startLine']}"):
                st.caption(f"Retrieved via {snippet['retrievalReason']}; {snippet['kind']}")
                st.code(snippet["text"], language="csharp")
                if snippet["truncated"]:
                    st.caption("Bounded preview; additional content is stored in child chunks.")
        if st.session_state["rag_results"]:
            st.subheader("Interpret the retrieved code")
            st.caption(
                "The API Analyzer reads the selected code context and returns inferred meaning "
                "with source locations and uncertainty."
            )
            semantic_consent = st.checkbox(
                "Allow these selected, redacted code snippets to be sent to OpenAI.",
                key="rag_semantic_consent",
            )
            semantic_model = st.text_input(
                "Interpretation model",
                value=os.getenv("OPENAI_MODEL", "gpt-4o-mini"),
                key="rag_semantic_model",
            )
            if st.button(
                "Explain selected target" if target_id else "Explain retrieved code",
                key="rag_explain_target",
                disabled=not semantic_consent or not openai_api_key() or not semantic_model.strip(),
            ):
                focused_index = None
                try:
                    profile = EmbeddingConfig.model_validate(rag_manifest["embedding"])
                    adapter = create_embedder(
                        profile,
                        api_key=openai_api_key(),
                        allow_source_sharing=cloud_embedding_consent,
                    )
                    focused_index = ChromaRepositoryIndex(
                        Path(st.session_state["rag_store_path"]), adapter
                    )
                    semantic_provider = OpenAISemanticProvider(
                        api_key=openai_api_key() or "", model=semantic_model.strip()
                    )
                    if target_id and st.session_state["discovery_model"]:
                        st.session_state["rag_semantics"] = inspect_retrieved_target(
                            st.session_state["discovery_model"],
                            focused_index,
                            target_id,
                            semantic_provider,
                        )
                    else:
                        st.session_state["rag_semantics"] = inspect_retrieved_code(
                            focused_index, query_text.strip(), semantic_provider
                        )
                except Exception as exc:
                    st.error(
                        f"Code interpretation failed: {type(exc).__name__}. "
                        "Check provider access and target evidence."
                    )
                finally:
                    if focused_index is not None:
                        focused_index.close()
            interpretation = st.session_state["rag_semantics"]
            if (
                interpretation
                and interpretation.get("targetId") == target_id
                and (target_id or interpretation.get("query") == query_text.strip())
            ):
                if interpretation["status"] == "unknown":
                    st.warning(interpretation["reason"])
                else:
                    if "confidence" in interpretation:
                        st.caption(
                            f"{interpretation['status'].capitalize()} interpretation with "
                            f"provider confidence {interpretation['confidence']:.2f} "
                            f"by {interpretation['model']}"
                        )
                    else:
                        st.caption(
                            f"Code interpretation by {interpretation['model']}; "
                            "see confidence on each claim."
                        )
                    st.json(interpretation["semantic"], expanded=2)
                    if interpretation.get("codeAnalysis"):
                        st.caption(
                            "Code observations and inferred meaning (each claim cites chunks)"
                        )
                        st.json(interpretation["codeAnalysis"], expanded=2)
                    st.caption("Source context considered")
                    st.json(interpretation["citations"], expanded=1)
                    if interpretation["gaps"]:
                        st.warning("Open context: " + "; ".join(interpretation["gaps"]))

with phase_two_tab:
    if not st.session_state["phase_2_unlocked"] or not st.session_state["application_runs"]:
        st.info(
            "Run the Discovery Agent to create an application for Phase 2.", icon=":material/lock:"
        )
    else:
        st.header("API Analyzer Agent")
        runs = st.session_state["application_runs"]
        active_id = st.session_state["active_application_id"]
        choices = list(runs)
        selected_id = st.selectbox(
            "Select discovered application",
            choices,
            index=choices.index(active_id),
            format_func=lambda item: (
                f"{runs[item]['profile']['application']} · {runs[item]['profile']['region']} · "
                f"{runs[item]['profile']['repository']} [{item[:6]}]"
            ),
            key=f"phase2_application_{active_id}",
        )
        if selected_id != active_id:
            activate_application(selected_id)
            st.rerun()
        profile = runs[active_id]["profile"]
        with st.container(border=True):
            st.subheader("Selected application", anchor=False)
            with st.container(horizontal=True):
                st.metric("Region", profile["region"])
                st.metric("Application", profile["application"])
            st.caption(f"Repository ZIP: {profile['repository']}")
            st.caption(f"OpenAPI upload: {profile['openapi']}")
            st.caption(
                "Repository RAG: "
                + (
                    "ready for this application"
                    if st.session_state["rag_store_path"]
                    else "not built for this application"
                )
            )
        st.caption(
            "The agent reuses the saved repository index when available, retrieves "
            "bounded code evidence, classifies domain and capability, and explains endpoints, "
            "endpoint contract models, attributes, and enums before generating a self-contained "
            "enriched OpenAPI 3.0 specification. Structural facts continue to come only from "
            "Phase 1."
        )
        previous_error = st.session_state.get("phase_2_error")
        if previous_error:
            st.error(f"Previous API Analyzer run failed: {previous_error}")
            st.caption("Correct the issue above, then run the selected application again.")
        if st.session_state["repository_archive"] is None:
            st.info("Specification-only enrichment: implementation code evidence is unavailable.")
        configured_key = openai_api_key()
        key_override = st.text_input(
            "OpenAI API key (optional session override)",
            type="password",
            key="phase_2_key_override",
            help=(
                "Use this if the configured key is missing or rejected. "
                "It stays in this browser session."
            ),
        )
        api_key = key_override.strip() or configured_key
        if api_key:
            st.badge(
                "API key available; checked when run starts", color="green", icon=":material/key:"
            )
        else:
            st.warning(
                "Enter an API key above or set OPENAI_API_KEY. "
                "The key is never written to an artifact.",
                icon=":material/key:",
            )
        openai_model = st.text_input(
            "OpenAI model",
            value=os.getenv("OPENAI_MODEL", "gpt-4o-mini"),
            help="The model must support Structured Outputs in the Responses API.",
            key="phase_2_openai_model",
        )
        source_consent = st.checkbox(
            "Allow selected specification details and redacted code (when available) "
            "to be sent to OpenAI.",
            key="phase_2_source_consent",
        )
        missing = []
        if st.session_state["discovery_model"] is None:
            missing.append("Select an application with completed Discovery.")
        if st.session_state["repository_archive"] is not None and not (
            st.session_state["rag_store_path"]
            and (Path(st.session_state["rag_store_path"]) / "rag-manifest.json").is_file()
        ):
            missing.append("Build or reopen this application's repository index in Repository RAG.")
        if not api_key:
            missing.append("Provide an OpenAI API key.")
        if not source_consent:
            missing.append("Acknowledge source sharing above.")
        if not openai_model.strip():
            missing.append("Choose an interpretation model.")
        if missing:
            st.info("Before running: " + " ".join(missing))
        else:
            st.success("Ready to analyze the selected application.")
        rerun = bool(st.session_state["phase_2_artifacts"] or previous_error)
        if st.button(
            (
                "Run API Analyzer again for selected application"
                if rerun
                else "Run API Analyzer Agent"
            ),
            type="primary",
            icon=":material/auto_awesome:",
            key="run_phase_2_semantic_openapi",
            disabled=bool(missing),
        ):
            st.session_state["phase_2_artifacts"] = {}
            runs[active_id]["phase_2_artifacts"] = {}
            st.session_state["phase_2_error"] = None
            runs[active_id]["phase_2_error"] = None
            try:
                provider = OpenAISemanticProvider(api_key=api_key or "", model=openai_model.strip())
                adapter = None
                if st.session_state["rag_manifest"]:
                    profile = EmbeddingConfig.model_validate(
                        st.session_state["rag_manifest"]["embedding"]
                    )
                    adapter = create_embedder(
                        profile, api_key=api_key, allow_source_sharing=source_consent
                    )
                with st.status("Running API Analyzer Agent...", expanded=True) as status:
                    generated = run_uploaded_semantic_generation(
                        repository_archive=st.session_state["repository_archive"],
                        discovery_artifact=st.session_state["discovery_model"],
                        provider=provider,
                        progress=st.write,
                        rag_store_path=Path(st.session_state["rag_store_path"])
                        if st.session_state["rag_store_path"]
                        else None,
                        embedder=adapter,
                    )
                    st.session_state["phase_2_artifacts"] = generated
                    runs[active_id]["phase_2_artifacts"] = generated
                    generated_report = json.loads(generated["enrichment-report.json"])
                    if generated_report["providerStatus"] == "failed":
                        failure = (
                            generated_report["validationErrors"][0]
                            if generated_report["validationErrors"]
                            else "Provider validation failed."
                        )
                        st.session_state["phase_2_error"] = failure
                        runs[active_id]["phase_2_error"] = failure
                        status.update(
                            label="API Analyzer stopped during provider validation",
                            state="error",
                            expanded=True,
                        )
                    else:
                        status.update(
                            label="API Analyzer Agent complete",
                            state="complete",
                            expanded=False,
                        )
                    persist_application(active_id)
                st.rerun()
            except Exception as exc:
                failure = str(exc)
                st.session_state["phase_2_error"] = failure
                runs[active_id]["phase_2_error"] = failure
                persist_application(active_id)
                st.error(f"Semantic OpenAPI generation failed: {failure}")
                st.rerun()

        phase_2_artifacts: dict[str, bytes] = st.session_state["phase_2_artifacts"]
        if phase_2_artifacts:
            report = json.loads(phase_2_artifacts["enrichment-report.json"])
            with st.container(horizontal=True):
                st.metric("Endpoints discovered", report["endpointsDiscovered"])
                st.metric("Endpoints enriched", report["endpointsEnriched"])
                st.metric("Domains classified", report["domainsClassified"])
                st.metric("Capabilities", report["capabilitiesClassified"])
            with st.container(horizontal=True):
                st.metric("Contract models discovered", report["entitiesDiscovered"])
                st.metric("Contract models enriched", report["entitiesEnriched"])
                st.metric("Attributes enriched", report["attributesEnriched"])
                st.metric("Enums enriched", report["enumsEnriched"])
            with st.container(horizontal=True):
                st.metric("Needs more context", len(report["needsMoreContextTargets"]))
                st.metric("Open issues", len(report["validationErrors"]))
                st.metric(
                    "Repository files indexed", report.get("retrieval", {}).get("filesIndexed", 0)
                )
                st.metric("Chroma chunks", report.get("retrieval", {}).get("chunksIndexed", 0))
            if report["validationErrors"]:
                st.error(report["validationErrors"][0])
            if report["status"] == "partial":
                st.warning(
                    "The structural discovery result is preserved, but semantic enrichment is "
                    "partial. Review enrichment-report.json for validation and coverage gaps.",
                    icon=":material/warning:",
                )
            with st.container(horizontal=True):
                for filename, content in phase_2_artifacts.items():
                    mime = "application/yaml" if filename.endswith(".yaml") else "application/json"
                    st.download_button(
                        f"Download {filename}",
                        data=content,
                        file_name=filename,
                        mime=mime,
                        icon=":material/download:",
                        key=f"download_phase_2_{filename}",
                    )
            st.download_button(
                "Download all Phase 2 artifacts",
                data=build_named_bundle(phase_2_artifacts),
                file_name="semantic-openapi-artifacts.zip",
                mime="application/zip",
                icon=":material/folder_zip:",
                key="download_all_phase_2_artifacts",
            )
            preview_name = st.selectbox(
                "Preview Phase 2 artifact", list(phase_2_artifacts), key="phase_2_preview"
            )
            if preview_name.endswith(".yaml"):
                st.code(phase_2_artifacts[preview_name].decode("utf-8"), language="yaml")
            else:
                st.json(json.loads(phase_2_artifacts[preview_name]), expanded=2)

with regional_tab:
    st.header("Regional API catalog")
    st.caption(
        "Compare endpoint contract models, domains and capabilities across every completed "
        "application in a region. Select all APIs or focus on one Claim, Quote or other API."
    )
    runs = st.session_state["application_runs"]
    if not runs:
        st.info(
            "Run the Discovery Agent for an EU, US or other regional application to populate "
            "this catalog.",
            icon=":material/info:",
        )
    else:
        available_regions = sorted(
            {run["profile"]["region"] for run in runs.values()},
            key=str.casefold,
        )
        selected_region = st.selectbox(
            "Region",
            available_regions,
            format_func=lambda code: f"{code} — {REGIONS.get(code, code)}",
            key="regional_catalog_region",
        )
        regional_runs = {
            run_id: run
            for run_id, run in runs.items()
            if run["profile"]["region"] == selected_region
        }
        scope_options = [None, *regional_runs]
        selected_scope = st.selectbox(
            "API view",
            scope_options,
            format_func=lambda run_id: (
                "All APIs in region"
                if run_id is None
                else (
                    f"{regional_runs[run_id]['profile']['application']} · "
                    f"{regional_runs[run_id]['profile']['repository']} [{run_id[:6]}]"
                )
            ),
            key="regional_catalog_api",
        )
        model_rows, endpoint_rows = regional_catalog_rows(
            runs, region=selected_region, application_id=selected_scope
        )
        model_tree = regional_model_tree(
            runs, region=selected_region, application_id=selected_scope
        )
        domain_tree = regional_domain_tree(
            runs, region=selected_region, application_id=selected_scope
        )
        api_count = len(regional_runs) if selected_scope is None else 1
        with st.container(horizontal=True):
            st.metric("APIs", api_count)
            st.metric("Endpoints", len(endpoint_rows))
            st.metric("Contract models", len(model_rows))
            st.metric(
                "Analyzed endpoints",
                sum(row["Domain"] != "Awaiting API Analyzer" for row in endpoint_rows),
            )

        models_tab, domains_tab = st.tabs(
            [
                ":material/schema: Models and mappings",
                ":material/hub: Domains and capabilities",
            ]
        )
        with models_tab:
            st.caption(
                "Expand the regional hierarchy to trace each API contract model to its "
                "request or response endpoints and fields."
            )
            with st.expander("Entity and attribute normalization settings"):
                st.caption(
                    "Generate review-only normalized names and descriptions inside one regional "
                    "API. This does not change Discovery or compare APIs."
                )
                normalization_key_override = st.text_input(
                    "OpenAI API key (optional session override)",
                    type="password",
                    key="regional_normalization_key",
                )
                normalization_model = st.text_input(
                    "Normalization model",
                    value=os.getenv("OPENAI_MODEL", "gpt-4o-mini"),
                    key="regional_normalization_model",
                )
                normalization_consent = st.checkbox(
                    "Allow this entity, its attributes, and existing API Analyzer descriptions "
                    "to be sent to OpenAI.",
                    key="regional_normalization_consent",
                )
            normalization_api_key = normalization_key_override.strip() or openai_api_key()
            if model_tree and model_rows:
                st.markdown(f"#### :material/public: {selected_region}")
                for branch in model_tree:
                    with st.container(border=True):
                        st.markdown(f"##### :material/api: {branch['api']}")
                        st.caption(
                            f"{branch['repository']} · {len(branch['models'])} contract models"
                        )
                        for model_branch in branch["models"]:
                            with st.expander(
                                f":material/schema: {model_branch['name']} · "
                                f"{len(model_branch['fields'])} fields"
                            ):
                                with st.container(horizontal=True):
                                    st.badge(f"Domain: {model_branch['domain']}")
                                    if model_branch["confidence"] is not None:
                                        st.badge(
                                            f"Confidence: {model_branch['confidence']:.2f}",
                                            color="blue",
                                        )
                                st.markdown(
                                    f"**Business concept:** {model_branch['businessConcept']}"
                                )
                                st.markdown(f"**Summary:** {model_branch['summary']}")
                                st.markdown(f"**Description:** {model_branch['description']}")
                                normalization_id = f"{branch['runId']}:{model_branch['id']}"
                                if st.button(
                                    "Normalize entity and attributes",
                                    icon=":material/auto_fix_high:",
                                    key=f"normalize_{branch['runId']}_{model_branch['id']}",
                                    disabled=(
                                        not normalization_consent
                                        or not normalization_api_key
                                        or not normalization_model.strip()
                                    ),
                                ):
                                    try:
                                        selected_run = runs[branch["runId"]]
                                        provider = OpenAISemanticProvider(
                                            api_key=normalization_api_key or "",
                                            model=normalization_model.strip(),
                                        )
                                        with st.spinner("Normalizing entity and attributes..."):
                                            proposal = normalize_regional_entity(
                                                selected_run["discovery_model"],
                                                model_branch["id"],
                                                selected_run.get("phase_2_artifacts", {}).get(
                                                    "semantic-metadata.json"
                                                ),
                                                provider,
                                            )
                                        st.session_state["regional_normalizations"][
                                            normalization_id
                                        ] = proposal
                                        st.rerun()
                                    except Exception as exc:
                                        st.error(
                                            "Normalization failed. Check provider access. "
                                            f"Error: {type(exc).__name__}."
                                        )
                                proposal = st.session_state["regional_normalizations"].get(
                                    normalization_id
                                )
                                if proposal:
                                    st.markdown(
                                        f"**Normalized entity name:** {proposal['normalizedName']}"
                                    )
                                    st.markdown(
                                        "**Normalized description:** "
                                        f"{proposal['normalizedDescription']}"
                                    )
                                    st.caption(
                                        f"Normalization confidence: {proposal['confidence']:.2f}"
                                    )
                                st.markdown("**Endpoint mappings**")
                                if model_branch["mappings"]:
                                    st.dataframe(
                                        model_branch["mappings"],
                                        hide_index=True,
                                        width="stretch",
                                    )
                                else:
                                    st.caption("No direct endpoint mapping was discovered.")
                                st.markdown("**Fields**")
                                if model_branch["fields"]:
                                    normalized_attributes = {
                                        item["attributeId"]: item
                                        for item in (proposal or {}).get("attributes", [])
                                    }
                                    field_rows = []
                                    for field in model_branch["fields"]:
                                        normalized = normalized_attributes.get(field["id"], {})
                                        field_rows.append(
                                            {
                                                key: value
                                                for key, value in {
                                                    **field,
                                                    "Normalized name": normalized.get(
                                                        "normalizedName", "Not normalized"
                                                    ),
                                                    "Normalized description": normalized.get(
                                                        "normalizedDescription", "Not normalized"
                                                    ),
                                                    "Normalization confidence": normalized.get(
                                                        "confidence"
                                                    ),
                                                }.items()
                                                if key != "id"
                                            }
                                        )
                                    st.dataframe(
                                        field_rows,
                                        hide_index=True,
                                        width="stretch",
                                        column_config={
                                            "Confidence": st.column_config.NumberColumn(
                                                "Confidence",
                                                min_value=0,
                                                max_value=1,
                                                format="%.2f",
                                            ),
                                            "Normalization confidence": (
                                                st.column_config.NumberColumn(
                                                    "Normalization confidence",
                                                    min_value=0,
                                                    max_value=1,
                                                    format="%.2f",
                                                )
                                            ),
                                        },
                                    )
                                else:
                                    st.caption("No fields were discovered for this model.")
            else:
                st.info("No endpoint contract models were discovered for this selection.")
        with domains_tab:
            st.caption(
                "Expand the hierarchy to trace domains and capabilities across APIs and "
                "endpoints. Classifications come from completed API Analyzer output."
            )
            if domain_tree and endpoint_rows:
                st.markdown(f"#### :material/public: {selected_region}")
                for domain_branch in domain_tree:
                    endpoint_count = sum(
                        len(api["endpoints"])
                        for capability in domain_branch["capabilities"]
                        for api in capability["apis"]
                    )
                    with st.expander(
                        f":material/domain: {domain_branch['name']} · {endpoint_count} endpoints"
                    ):
                        for capability_branch in domain_branch["capabilities"]:
                            with st.container(border=True):
                                st.markdown(f"##### :material/hub: {capability_branch['name']}")
                                for api_branch in capability_branch["apis"]:
                                    st.markdown(f"**:material/api: {api_branch['name']}**")
                                    st.dataframe(
                                        api_branch["endpoints"],
                                        hide_index=True,
                                        width="stretch",
                                        column_config={
                                            "Confidence": st.column_config.NumberColumn(
                                                "Confidence",
                                                min_value=0,
                                                max_value=1,
                                                format="%.2f",
                                            )
                                        },
                                    )
            else:
                st.info("No endpoints were discovered for this selection.")
