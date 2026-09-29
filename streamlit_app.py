from __future__ import annotations

import json
import os
import sys
from collections.abc import Callable
from hashlib import sha256
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

from canonical_model_generator.acord_alignment import (  # noqa: E402
    MANUAL,
    MATCH_STATUSES,
    NOT_MATCHED,
    PARTIAL_MATCH,
    USE_ACORD,
    approve_acord_alignment,
    build_regional_alignment_source,
    default_alignment_decisions,
    load_alignment_artifacts,
    propose_acord_alignment,
    save_alignment_artifact,
    validate_alignment_decisions,
)
from canonical_model_generator.acord_rag import (  # noqa: E402
    ACORD_ARTIFACTS,
    AcordDocumentIndex,
    build_acord_chunks,
    generate_acord_artifacts,
    parse_acord_document,
)
from canonical_model_generator.acord_rag.history import (  # noqa: E402
    load_acord_records,
    save_acord_record,
)
from canonical_model_generator.api_analyzer import (  # noqa: E402
    OpenAISemanticProvider,
    TokenBudgetConfig,
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
from canonical_model_generator.regional_review import (  # noqa: E402
    build_regional_review,
    render_regional_review_excel,
    render_regional_review_mermaid,
)
from canonical_model_generator.repository_rag.embeddings import (  # noqa: E402
    LOCAL_MODEL,
    OPENAI_MODELS,
    EmbeddingConfig,
    create_embedder,
)
from canonical_model_generator.repository_rag.index import ChromaRepositoryIndex  # noqa: E402
from canonical_model_generator.workflow_progress import reached_stage_count  # noqa: E402

st.set_page_config(
    page_title="Insurance Canonical Model Platform",
    page_icon=":material/account_tree:",
    layout="wide",
)

APPLICATION_HISTORY_ROOT = Path(__file__).resolve().parent / ".applications"
ACORD_HISTORY_ROOT = Path(__file__).resolve().parent / ".acord"
ALIGNMENT_HISTORY_ROOT = Path(__file__).resolve().parent / ".alignments"

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
st.session_state.setdefault("approved_regional_reviews", {})
st.session_state.setdefault("acord_runs", {})
st.session_state.setdefault("active_acord_id", None)
st.session_state.setdefault("acord_results", [])
st.session_state.setdefault("alignment_reviews", {})
st.session_state.setdefault("active_alignment_id", None)
st.session_state.setdefault("acord_alignment_drafts", {})
if not st.session_state["application_runs"]:
    st.session_state["application_runs"] = load_application_records(APPLICATION_HISTORY_ROOT)
if not st.session_state["acord_runs"]:
    st.session_state["acord_runs"] = load_acord_records(ACORD_HISTORY_ROOT)
if (
    st.session_state["acord_runs"]
    and st.session_state["active_acord_id"] not in st.session_state["acord_runs"]
):
    st.session_state["active_acord_id"] = next(iter(st.session_state["acord_runs"]))
if not st.session_state["alignment_reviews"]:
    st.session_state["alignment_reviews"] = load_alignment_artifacts(ALIGNMENT_HISTORY_ROOT)
if (
    st.session_state["alignment_reviews"]
    and st.session_state["active_alignment_id"] not in st.session_state["alignment_reviews"]
):
    st.session_state["active_alignment_id"] = next(reversed(st.session_state["alignment_reviews"]))


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


def build_acord_bundle(artifacts: dict[str, bytes]) -> bytes:
    bundle = BytesIO()
    with ZipFile(bundle, "w", ZIP_DEFLATED) as archive:
        for label, content in artifacts.items():
            archive.writestr(ACORD_ARTIFACTS[label], content)
    return bundle.getvalue()


def ingest_acord_reference(
    *,
    source_content: bytes,
    source_name: str,
    reference_label: str,
    reference_version: str,
    progress: Callable[[str], None] | None = None,
) -> str:
    model = parse_acord_document(
        source_content,
        source_name,
        reference_label=reference_label,
        reference_version=reference_version,
    )
    artifacts = generate_acord_artifacts(model)
    chunks = build_acord_chunks(model)
    run_id = uuid4().hex
    run_path = save_acord_record(
        ACORD_HISTORY_ROOT,
        run_id,
        model=model,
        artifacts=artifacts,
        source_content=source_content,
    )
    index = AcordDocumentIndex(run_path / "index")
    try:
        stats = index.ingest(model, chunks, progress=progress)
        manifest = index.manifest
    finally:
        index.close()
    st.session_state["acord_runs"][run_id] = {
        "profile": {
            "runId": run_id,
            "sourceFile": Path(source_name).name,
            "referenceLabel": reference_label.strip(),
            "referenceVersion": reference_version.strip(),
            "sha256": model["source"]["sha256"],
        },
        "model": model,
        "artifacts": artifacts,
        "manifest": manifest,
        "storagePath": str(run_path / "index"),
        "stats": stats,
    }
    st.session_state["active_acord_id"] = run_id
    st.session_state["acord_results"] = []
    return run_id


def openai_api_key() -> str | None:
    try:
        configured = st.secrets.get("OPENAI_API_KEY")
    except (FileNotFoundError, KeyError):
        configured = None
    value = configured or os.getenv("OPENAI_API_KEY")
    return value.strip() if value else None


def workflow_stages() -> list[dict[str, str]]:
    """Describe the four-stage regional application journey."""
    active_id = st.session_state.get("active_application_id")
    run = st.session_state.get("application_runs", {}).get(active_id, {})
    discovery_ready = bool(run.get("discovery_model"))
    rag_path = run.get("rag_store_path")
    rag_ready = bool(rag_path and Path(rag_path, "rag-manifest.json").is_file())
    report_content = run.get("phase_2_artifacts", {}).get("enrichment-report.json")
    report: dict[str, object] = {}
    if report_content:
        try:
            report = json.loads(report_content)
        except (json.JSONDecodeError, TypeError, UnicodeDecodeError):
            report = {}
    analyzer_status = str(report.get("status", ""))
    current_workspace = str(st.session_state.get("workflow_tabs", ""))
    regional_selected = "Regional view" in current_workspace
    analyzer_complete = analyzer_status == "complete"
    return [
        {
            "name": "Discovery agent",
            "state": "Complete" if discovery_ready else "Current",
            "detail": "Repository structure and endpoint contracts"
            if discovery_ready
            else "Upload and analyze a trusted repository",
        },
        {
            "name": "Repository RAG",
            "state": "Complete" if rag_ready else "Ready" if discovery_ready else "Locked",
            "detail": "Saved index for the selected repository"
            if rag_ready
            else "Build an index from the same Discovery repository",
        },
        {
            "name": "API analyzer",
            "state": (
                "Complete"
                if analyzer_status == "complete"
                else "Partial"
                if analyzer_status
                else "Ready"
                if rag_ready
                else "Locked"
            ),
            "detail": (
                f"{report.get('endpointsEnriched', 0)}/"
                f"{report.get('endpointsDiscovered', 0)} endpoints, "
                f"{report.get('entitiesEnriched', 0)}/"
                f"{report.get('entitiesDiscovered', 0)} entities enriched"
                if analyzer_status
                else "Requires the selected repository's RAG index"
            ),
        },
        {
            "name": "Regional view",
            "state": "Current"
            if discovery_ready and (analyzer_complete or regional_selected)
            else "Ready"
            if discovery_ready
            else "Locked",
            "detail": "Inspect models, mappings, domains, and regional review",
        },
    ]


def render_workflow_progress() -> None:
    stages = workflow_stages()
    reached = reached_stage_count([item["state"] for item in stages])
    active_id = st.session_state.get("active_application_id")
    active_run = st.session_state.get("application_runs", {}).get(active_id, {})
    profile = active_run.get("profile", {})
    with st.container(border=True):
        st.subheader("Agent workflow", anchor=False)
        if profile:
            st.caption(
                f"Selected pipeline: {profile.get('region')} · "
                f"{profile.get('application')} · {profile.get('repository')} [{active_id[:6]}]"
            )
        else:
            st.caption("Start with Discovery to create a selected application pipeline.")
        partial = next((item for item in stages if item["state"] == "Partial"), None)
        progress_text = f"{reached} of {len(stages)} stages reached"
        if partial:
            progress_text += f" · {partial['name']} partial: {partial['detail']}"
        st.progress(reached / len(stages), text=progress_text)


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
    resume_artifacts: dict[str, bytes] | None = None,
) -> dict[str, bytes]:
    if repository_archive is None:
        raise ValueError("API Analyzer requires the source repository and its saved RAG index.")
    if rag_store_path is None:
        raise ValueError("API Analyzer requires a saved RAG index for the selected repository.")
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
            resume_artifacts=resume_artifacts,
        )


def has_unfinished_semantic_targets(artifacts: dict[str, bytes]) -> bool:
    report_content = artifacts.get("enrichment-report.json")
    if not report_content:
        return False
    try:
        report = json.loads(report_content)
    except (TypeError, json.JSONDecodeError):
        return False
    return report.get("status") == "partial" and any(
        report.get(key) for key in ("missingEndpointIds", "missingEntityIds", "missingEnumIds")
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
        raise IntakeError("A trusted .NET repository ZIP is required; OpenAPI is optional.")
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

CRAWLER_TAB_LABELS = [
    ":material/account_tree: 1 Discovery",
    ":material/search: 2 Repository RAG",
    ":material/manage_search: 3 API analyzer",
    ":material/public: 4 Regional view",
]
ACORD_TAB_LABELS = [
    ":material/library_books: ACORD ingestion",
    ":material/compare_arrows: ACORD alignment",
    ":material/hub: Canonical view",
]
WORKFLOW_TAB_LABELS = CRAWLER_TAB_LABELS + ACORD_TAB_LABELS


def open_crawler_workspace() -> None:
    """Open a selected crawler-code workspace."""
    selected = st.session_state.get("crawler_sidebar_menu")
    if selected:
        st.session_state["workflow_tabs"] = selected
        st.session_state["crawler_tabs"] = selected
        st.session_state["acord_sidebar_menu"] = None


def open_acord_workspace() -> None:
    """Open a selected ACORD workspace."""
    selected = st.session_state.get("acord_sidebar_menu")
    if selected:
        st.session_state["workflow_tabs"] = selected
        st.session_state["crawler_sidebar_menu"] = None


def open_crawler_tab() -> None:
    """Synchronize a visible crawler tab with the sidebar workspace state."""
    selected = st.session_state.get("crawler_tabs")
    if selected:
        st.session_state["workflow_tabs"] = selected
        st.session_state["crawler_sidebar_menu"] = selected
        st.session_state["acord_sidebar_menu"] = None


with st.sidebar:
    current_workspace = st.session_state.get("workflow_tabs", CRAWLER_TAB_LABELS[0])
    st.caption("Crawler code")
    st.pills(
        "Crawler workspace",
        CRAWLER_TAB_LABELS,
        default=current_workspace if current_workspace in CRAWLER_TAB_LABELS else None,
        key="crawler_sidebar_menu",
        on_change=open_crawler_workspace,
        label_visibility="collapsed",
    )
    st.caption("ACORD view")
    st.pills(
        "ACORD workspace",
        ACORD_TAB_LABELS,
        default=current_workspace if current_workspace in ACORD_TAB_LABELS else None,
        key="acord_sidebar_menu",
        on_change=open_acord_workspace,
        label_visibility="collapsed",
    )

if current_workspace in CRAWLER_TAB_LABELS:
    render_workflow_progress()

if "crawler_tabs" not in st.session_state:
    st.session_state["crawler_tabs"] = (
        current_workspace if current_workspace in CRAWLER_TAB_LABELS else CRAWLER_TAB_LABELS[0]
    )

discovery_tab, rag_tab, phase_two_tab, regional_tab = st.tabs(
    CRAWLER_TAB_LABELS,
    key="crawler_tabs",
    on_change=open_crawler_tab,
)
acord_ingestion_tab = st.container(key="acord_ingestion_page")
acord_alignment_tab = st.container(key="acord_alignment_page")
canonical_view_tab = st.container(key="canonical_view_page")

visible_page_key = {
    ACORD_TAB_LABELS[0]: "acord_ingestion_page",
    ACORD_TAB_LABELS[1]: "acord_alignment_page",
    ACORD_TAB_LABELS[2]: "canonical_view_page",
}.get(current_workspace)
hidden_page_keys = {
    "acord_ingestion_page",
    "acord_alignment_page",
    "canonical_view_page",
} - ({visible_page_key} if visible_page_key else set())
hidden_selectors = [f".st-key-{key}" for key in sorted(hidden_page_keys)]
if current_workspace not in CRAWLER_TAB_LABELS:
    hidden_selectors.append(".st-key-crawler_tabs")
st.html(f"<style>{', '.join(hidden_selectors)} {{ display: none; }}</style>")

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
        st.caption("Upload a repository ZIP and, optionally, an OpenAPI YAML/JSON document.")
        repository_column, contract_column = st.columns(2, gap="large")
        with repository_column:
            repository_file: UploadedFile | None = st.file_uploader(
                "Trusted .NET repository ZIP",
                type="zip",
                max_upload_size=100,
                help=("Required. Roslyn/MSBuild analyzes the repository as trusted code."),
                key="repository_zip",
            )
            st.caption("Repository input · ZIP · Up to 100 MB")
        with contract_column:
            openapi_file: UploadedFile | None = st.file_uploader(
                "OpenAPI document",
                type=["json", "yaml", "yml"],
                max_upload_size=10,
                help=(
                    "Optional. When supplied, the specification is reconciled with repository "
                    "evidence."
                ),
                key="openapi_document",
            )
            st.caption("Specification input · JSON or YAML · Up to 10 MB")

        submitted = st.form_submit_button(
            "Analyze application", type="primary", icon=":material/play_arrow:"
        )

    if submitted:
        if not region or not region.strip() or not system.strip() or repository_file is None:
            st.error("Region, application name, and a repository ZIP are required.")
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
                        repository_archive=repository_file.getvalue(),
                        repository_name=repository_file.name,
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
        st.warning(
            "Current entity coverage includes user-authored request, response, DTO, domain, "
            "ViewModel, nested property, collection-element, and inherited models reachable "
            "from API endpoints. Generated types and unrelated models are excluded. "
            "Deep call paths, persistence, mappings, integrations, security, and Razor Pages "
            "remain open gaps. When OpenAPI is supplied, its schemas are reconciled with the "
            "repository evidence.",
            icon=":material/radar:",
        )
        st.subheader("Discovery artifact tree")
        st.markdown(
            "Repository/OpenAPI → Discovery Agent → API Catalog, Data Model, "
            "Relationship Graph, Validation and Enums, and Lineage."
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
    application_runs = st.session_state["application_runs"]
    if application_runs:
        rag_choices = [
            *([active_id] if active_id in application_runs else []),
            *(item for item in application_runs if item != active_id),
        ]
        rag_selected_id = st.selectbox(
            "Select application index",
            rag_choices,
            index=rag_choices.index(active_id) if active_id in rag_choices else 0,
            format_func=lambda item: (
                f"{application_runs[item]['profile']['region']} · "
                f"{application_runs[item]['profile']['application']} · "
                f"{application_runs[item]['profile']['repository']} [{item[:6]}] · "
                + ("current discovery · " if item == active_id else "")
                + (
                    "RAG ready"
                    if application_runs[item].get("rag_store_path")
                    and Path(
                        application_runs[item]["rag_store_path"], "rag-manifest.json"
                    ).is_file()
                    else "no RAG index"
                )
            ),
            key=f"rag_application_{active_id}",
        )
        if rag_selected_id != active_id:
            activate_application(rag_selected_id)
            st.rerun()
        active_id = rag_selected_id
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
        st.success(
            "Existing repository index reopened for the selected application.",
            icon=":material/database:",
        )
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
                f"{runs[item]['profile']['repository']} [{item[:6]}] · "
                + (
                    "RAG ready"
                    if runs[item].get("rag_store_path")
                    and Path(runs[item]["rag_store_path"], "rag-manifest.json").is_file()
                    else "no RAG index"
                )
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
            st.error(
                "API Analyzer requires repository source; specification-only runs are disabled."
            )
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
        with st.expander("LLM usage guardrails"):
            max_run_tokens = st.number_input(
                "Maximum tokens for this run",
                min_value=5_000,
                max_value=1_000_000,
                value=120_000,
                step=5_000,
                help=(
                    "The analyzer estimates each request with tiktoken before sending it and "
                    "stops before the projected total exceeds this ceiling."
                ),
            )
            max_llm_requests = st.number_input(
                "Maximum paid LLM requests",
                min_value=1,
                max_value=500,
                value=100,
                step=1,
            )
            max_input_tokens = st.number_input(
                "Maximum input tokens per request",
                min_value=1_000,
                max_value=200_000,
                value=24_000,
                step=1_000,
                key="phase_2_max_input_tokens",
            )
            max_output_tokens = st.number_input(
                "Maximum output tokens per request",
                min_value=500,
                max_value=100_000,
                value=4_000,
                step=500,
                key="phase_2_max_output_tokens",
            )
            st.caption(
                "The provider-reported input and output count for every completed request is "
                "written to the enrichment report."
            )
        source_consent = st.checkbox(
            "Allow selected specification details and redacted code (when available) "
            "to be sent to OpenAI.",
            key="phase_2_source_consent",
        )
        missing = []
        if st.session_state["discovery_model"] is None:
            missing.append("Select an application with completed Discovery.")
        if st.session_state["repository_archive"] is None:
            missing.append("Select an application with its trusted repository archive.")
        if not (
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
        previous_artifacts = dict(st.session_state["phase_2_artifacts"])
        can_continue = has_unfinished_semantic_targets(previous_artifacts)
        continue_clicked = False
        if can_continue:
            st.caption(
                "This run is partial. Continue reuses completed semantic results and starts a "
                "fresh token budget only for unfinished targets."
            )
            continue_clicked = st.button(
                "Continue remaining analysis",
                type="primary",
                icon=":material/play_arrow:",
                key="continue_phase_2_semantic_openapi",
                disabled=bool(missing),
                help=(
                    "Reuse completed endpoint, entity, and enum results and call the LLM only "
                    "for unfinished targets with a fresh run budget."
                ),
            )
        rerun = bool(previous_artifacts or previous_error)
        restart_clicked = st.button(
            ("Restart API Analyzer from beginning" if rerun else "Run API Analyzer Agent"),
            type="secondary" if can_continue else "primary",
            icon=":material/auto_awesome:",
            key="run_phase_2_semantic_openapi",
            disabled=bool(missing),
        )
        if continue_clicked or restart_clicked:
            resume_artifacts = previous_artifacts if continue_clicked else None
            if restart_clicked:
                st.session_state["phase_2_artifacts"] = {}
                runs[active_id]["phase_2_artifacts"] = {}
            st.session_state["phase_2_error"] = None
            runs[active_id]["phase_2_error"] = None
            try:
                provider = OpenAISemanticProvider(
                    api_key=api_key or "",
                    model=openai_model.strip(),
                    token_budget=TokenBudgetConfig(
                        max_run_tokens=int(max_run_tokens),
                        max_requests=int(max_llm_requests),
                        max_input_tokens_per_request=int(max_input_tokens),
                        max_output_tokens_per_request=int(max_output_tokens),
                    ),
                )
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
                        resume_artifacts=resume_artifacts,
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

        phase_2_artifacts: dict[str, bytes] = {
            filename: content
            for filename, content in st.session_state["phase_2_artifacts"].items()
            if Path(filename).suffix.casefold() in {".json", ".yaml", ".yml"}
        }
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
        selected_run_ids = list(regional_runs) if selected_scope is None else [selected_scope]
        for run_id in selected_run_ids:
            report_content = runs[run_id].get("phase_2_artifacts", {}).get("enrichment-report.json")
            if not report_content:
                continue
            try:
                report = json.loads(report_content)
            except (json.JSONDecodeError, TypeError, UnicodeDecodeError):
                continue
            if report.get("status") == "complete":
                continue
            st.warning(
                f"{runs[run_id]['profile']['application']} has partial API Analyzer coverage: "
                f"{report.get('endpointsEnriched', 0)}/{report.get('endpointsDiscovered', 0)} "
                f"endpoints and {report.get('entitiesEnriched', 0)}/"
                f"{report.get('entitiesDiscovered', 0)} models were enriched. "
                f"Stop reason: {report.get('stop_reason', 'not reported')}. "
                "Pending rows remain marked Awaiting API Analyzer.",
                icon=":material/warning:",
            )
        api_count = len(model_tree) if selected_scope is None else 1
        with st.container(horizontal=True):
            st.metric("APIs", api_count)
            st.metric("Endpoints", len(endpoint_rows))
            st.metric("Contract models", len(model_rows))
            st.metric(
                "Analyzed endpoints",
                sum(row["Domain"] != "Awaiting API Analyzer" for row in endpoint_rows),
            )

        models_tab, domains_tab, review_tab = st.tabs(
            [
                ":material/schema: Models and mappings",
                ":material/hub: Domains and capabilities",
                ":material/fact_check: Regional normalization review",
            ]
        )
        with models_tab:
            st.caption(
                "Expand the regional hierarchy to trace each API contract model to its "
                "request or response endpoints and fields."
            )
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
                                st.caption(f"Domain source: {model_branch['domainSource']}")
                                st.markdown(
                                    f"**Business concept:** {model_branch['businessConcept']}"
                                )
                                st.markdown(f"**Summary:** {model_branch['summary']}")
                                st.markdown(f"**Description:** {model_branch['description']}")
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
                                    field_rows = [
                                        {key: value for key, value in field.items() if key != "id"}
                                        for field in model_branch["fields"]
                                    ]
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
        with review_tab:
            st.caption(
                "Review every entity and attribute across the entire selected region. "
                "Approved duplicates are merged only in the downloadable regional view; all "
                "source entities, fields, APIs, and endpoints remain in the truth mapping."
            )
            entire_region_tree = regional_model_tree(runs, region=selected_region)
            entity_count = sum(len(branch["models"]) for branch in entire_region_tree)
            field_count = sum(
                len(model["fields"]) for branch in entire_region_tree for model in branch["models"]
            )
            with st.container(horizontal=True):
                st.metric("Regional APIs", len(regional_runs))
                st.metric("Source entities", entity_count)
                st.metric("Source attributes", field_count)

            with st.expander("Region-wide normalization settings", expanded=not entity_count):
                regional_key_override = st.text_input(
                    "OpenAI API key (optional session override)",
                    type="password",
                    key="regional_review_key",
                )
                regional_model = st.text_input(
                    "Normalization model",
                    value=os.getenv("OPENAI_MODEL", "gpt-4o-mini"),
                    key="regional_review_model",
                )
                regional_consent = st.checkbox(
                    "Allow every entity, its attributes, and existing API Analyzer descriptions "
                    "in this region to be sent to OpenAI.",
                    key="regional_review_consent",
                )
                regional_api_key = regional_key_override.strip() or openai_api_key()
                if st.button(
                    "Normalize entire region",
                    icon=":material/auto_fix_high:",
                    type="primary",
                    key="normalize_entire_region",
                    disabled=(
                        not entity_count
                        or not regional_consent
                        or not regional_api_key
                        or not regional_model.strip()
                    ),
                ):
                    provider = OpenAISemanticProvider(
                        api_key=regional_api_key or "",
                        model=regional_model.strip(),
                    )
                    progress = st.progress(0, text="Checking provider access")
                    try:
                        provider.validate_connection()
                        regional_inventory = [
                            {
                                "api": branch["api"],
                                "entity": model_branch["name"],
                                "attributes": [
                                    {"name": field["Field"], "type": field["Type"]}
                                    for field in model_branch["fields"]
                                ],
                            }
                            for branch in entire_region_tree
                            for model_branch in branch["models"]
                        ]
                        processed = 0
                        for branch in entire_region_tree:
                            selected_run = runs[branch["runId"]]
                            for model_branch in branch["models"]:
                                normalization_id = f"{branch['runId']}:{model_branch['id']}"
                                progress.progress(
                                    processed / entity_count,
                                    text=(f"Normalizing {branch['api']} · {model_branch['name']}"),
                                )
                                st.session_state["regional_normalizations"][normalization_id] = (
                                    normalize_regional_entity(
                                        selected_run["discovery_model"],
                                        model_branch["id"],
                                        selected_run.get("phase_2_artifacts", {}).get(
                                            "semantic-metadata.json"
                                        ),
                                        provider,
                                        regional_inventory,
                                    )
                                )
                                processed += 1
                        progress.progress(1.0, text="Regional normalization complete")
                        st.rerun()
                    except Exception as exc:
                        progress.empty()
                        st.error(
                            "Regional normalization stopped. Existing completed proposals were "
                            f"kept. Check provider access or output validity. Error: "
                            f"{type(exc).__name__}."
                        )

            if not entity_count:
                st.info("No endpoint contract entities were discovered in this region.")
            else:
                decisions: dict[str, dict] = {}
                proposals = st.session_state["regional_normalizations"]
                for branch in entire_region_tree:
                    st.markdown(f"#### :material/api: {branch['api']}")
                    for model_branch in branch["models"]:
                        review_id = f"{branch['runId']}:{model_branch['id']}"
                        proposal = proposals.get(review_id, {})
                        suggested_attributes = {
                            item["attributeId"]: item for item in proposal.get("attributes", [])
                        }
                        with st.expander(
                            f":material/schema: {model_branch['name']} · "
                            f"{len(model_branch['fields'])} fields"
                        ):
                            st.markdown(
                                f"**AI entity suggestion:** "
                                f"{proposal.get('normalizedName', 'Not normalized')}"
                            )
                            entity_choice = st.segmented_control(
                                "Approved entity value",
                                ["Original", "AI suggestion"],
                                default="Original",
                                key=f"entity_choice_{review_id}",
                                disabled=not proposal,
                            )
                            entity_comment = st.text_input(
                                "Optional entity review comment",
                                key=f"entity_comment_{review_id}",
                            )
                            field_rows = []
                            for field in model_branch["fields"]:
                                suggested = suggested_attributes.get(field["id"], {})
                                field_rows.append(
                                    {
                                        "Attribute ID": field["id"],
                                        "Original": field["Field"],
                                        "AI suggestion": suggested.get(
                                            "normalizedName", "Not normalized"
                                        ),
                                        "Type": field["Type"],
                                        "Approved value": "Original",
                                        "Comment": "",
                                    }
                                )
                            edited_fields = st.data_editor(
                                field_rows,
                                hide_index=True,
                                width="stretch",
                                key=f"field_review_{review_id}",
                                disabled=[
                                    "Attribute ID",
                                    "Original",
                                    "AI suggestion",
                                    "Type",
                                ],
                                column_config={
                                    "Attribute ID": None,
                                    "Approved value": st.column_config.SelectboxColumn(
                                        "Approved value",
                                        options=["Original", "AI suggestion"],
                                        required=True,
                                    ),
                                    "Comment": st.column_config.TextColumn(
                                        "Optional reviewer comment"
                                    ),
                                },
                            )
                            decisions[review_id] = {
                                "selection": entity_choice or "Original",
                                "comment": entity_comment,
                                "attributes": {
                                    row["Attribute ID"]: {
                                        "selection": row["Approved value"],
                                        "comment": row["Comment"],
                                    }
                                    for row in edited_fields
                                },
                            }
                            if model_branch["mappings"]:
                                st.markdown("**Endpoints involved**")
                                st.dataframe(
                                    model_branch["mappings"],
                                    hide_index=True,
                                    width="stretch",
                                )

                st.divider()
                st.markdown("#### Approve and generate regional artifacts")
                st.caption(
                    "Entities merge by approved name. Attributes merge within an approved "
                    "entity only when approved name and source type match. Approval creates a "
                    "regional review artifact and never modifies source Discovery artifacts."
                )
                approval_confirmed = st.checkbox(
                    "I reviewed the selections and approve this regional deduplication view.",
                    key=f"regional_approval_confirmed_{selected_region}",
                )
                if st.button(
                    "Approve regional view",
                    icon=":material/verified:",
                    type="primary",
                    disabled=not approval_confirmed,
                    key=f"approve_regional_view_{selected_region}",
                ):
                    approved_review = build_regional_review(
                        selected_region,
                        entire_region_tree,
                        proposals,
                        decisions,
                    )
                    st.session_state["approved_regional_reviews"][selected_region] = {
                        "review": approved_review,
                        "excel": render_regional_review_excel(approved_review),
                        "mermaid": render_regional_review_mermaid(approved_review),
                    }
                    st.success("Regional view approved. Both artifacts are ready.")

                approved = st.session_state["approved_regional_reviews"].get(selected_region)
                if approved:
                    review = approved["review"]
                    with st.container(horizontal=True):
                        st.metric(
                            "Approved regional entities",
                            review["summary"]["regionalEntities"],
                        )
                        st.metric(
                            "Duplicate entities merged",
                            review["summary"]["mergedDuplicateEntities"],
                        )
                        st.metric(
                            "Approved regional attributes",
                            review["summary"]["regionalAttributes"],
                        )
                    duplicate_rows = [
                        {
                            "Action": item["action"],
                            "API": item["api"],
                            "Source entity": item["sourceEntity"],
                            "Source attribute": item["sourceAttribute"],
                            "Regional entity": item["regionalEntity"],
                            "Regional attribute": item["regionalAttribute"],
                            "Endpoints involved": "; ".join(item["endpoints"]),
                        }
                        for item in review["removedDuplicates"]
                    ]
                    st.markdown("**Removed duplicate truth map**")
                    if duplicate_rows:
                        st.dataframe(duplicate_rows, hide_index=True, width="stretch")
                    else:
                        st.info("No duplicates matched the approved names and field types.")
                    with st.container(horizontal=True):
                        st.download_button(
                            "Download approved regional Excel",
                            data=approved["excel"],
                            file_name=f"{selected_region.lower()}-regional-model.xlsx",
                            mime=(
                                "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
                            ),
                            icon=":material/download:",
                            key=f"download_regional_excel_{selected_region}",
                        )
                        st.download_button(
                            "Download Mermaid truth map",
                            data=approved["mermaid"],
                            file_name=f"{selected_region.lower()}-regional-truth-map.mmd",
                            mime="text/plain",
                            icon=":material/download:",
                            key=f"download_regional_mermaid_{selected_region}",
                        )

with acord_ingestion_tab:
    st.header("ACORD ingestion")
    st.info(
        "ACORD ingestion is a separate RAG pipeline. It is not step 5 of the regional API "
        "pipeline, and it does not perform regional alignment or canonical generation.",
        icon=":material/info:",
    )
    st.caption(
        "Upload an authorized ACORD OpenAPI 3 YAML/JSON document. The pipeline extracts API "
        "endpoints, recursively nested entities and attributes, descriptions, $comment/vendor "
        "notes, constraints, and source lineage into its own persistent retrieval index."
    )
    acord_runs = st.session_state["acord_runs"]
    if acord_runs:
        with st.expander("Open a previous ACORD ingestion", expanded=False):
            saved_acord_id = st.selectbox(
                "Saved ACORD reference",
                list(acord_runs),
                format_func=lambda item: (
                    f"{acord_runs[item]['profile']['referenceLabel']} · "
                    f"{acord_runs[item]['profile']['referenceVersion']} · "
                    f"{acord_runs[item]['profile']['sourceFile']} [{item[:6]}]"
                ),
                key="saved_acord_reference",
            )
            if st.button(
                "Open saved ACORD reference",
                icon=":material/history:",
                key="open_saved_acord_reference",
            ):
                st.session_state["active_acord_id"] = saved_acord_id
                st.session_state["acord_results"] = []
                st.rerun()

    with st.container(border=True):
        st.subheader("Reference details", anchor=False)
        reference_column, version_column = st.columns(2, gap="large")
        with reference_column:
            acord_label = st.text_input(
                "ACORD reference label",
                placeholder="ACORD policy API",
                help="A stable name for this independently ingested standards reference.",
                key="acord_reference_label",
            )
        with version_column:
            acord_version = st.text_input(
                "Approved reference version",
                placeholder="2026.1",
                help="The approved ACORD release or package version used for this ingestion.",
                key="acord_reference_version",
            )
        acord_file: UploadedFile | None = st.file_uploader(
            "ACORD OpenAPI document",
            type=["json", "yaml", "yml"],
            max_upload_size=10,
            help="OpenAPI 3.x JSON or YAML, up to 10 MB.",
            key="acord_document",
        )
        selected_acord_file = acord_file or st.session_state.get("acord_document")
        if selected_acord_file is not None:
            st.caption(
                f"Selected specification: {selected_acord_file.name} · "
                f"{len(selected_acord_file.getvalue()):,} bytes"
            )
        usage_authorized = st.checkbox(
            "I confirm that this ACORD document is approved for local ingestion and indexing.",
            key="acord_usage_authorized",
        )
        ingest_clicked = st.button(
            "Build ACORD RAG index",
            type="primary",
            icon=":material/library_add:",
            key="build_acord_rag_index",
        )

    if ingest_clicked:
        missing_inputs = []
        if not acord_label.strip():
            missing_inputs.append("reference label")
        if not acord_version.strip():
            missing_inputs.append("approved version")
        if selected_acord_file is None:
            missing_inputs.append("ACORD YAML/JSON file")
        if missing_inputs:
            st.error("Required input missing: " + ", ".join(missing_inputs) + ".")
        elif not usage_authorized:
            st.error("Confirm that the ACORD document is approved for local ingestion.")
        else:
            try:
                with st.status(
                    "Building the independent ACORD RAG pipeline...", expanded=True
                ) as status:
                    st.write("Parsing OpenAPI endpoints and recursive model structure")
                    st.write(
                        "Preserving descriptions, comments, constraints, and JSON-pointer lineage"
                    )
                    st.write("Creating endpoint/entity chunks and the local semantic index")
                    ingest_acord_reference(
                        source_content=selected_acord_file.getvalue(),
                        source_name=selected_acord_file.name,
                        reference_label=acord_label,
                        reference_version=acord_version,
                        progress=st.write,
                    )
                    status.update(
                        label="ACORD ingestion complete", state="complete", expanded=False
                    )
            except (OSError, RuntimeError, ValueError) as exc:
                st.error(str(exc))

    active_acord_id = st.session_state.get("active_acord_id")
    active_acord = acord_runs.get(active_acord_id)
    if active_acord:
        model = active_acord["model"]
        summary = model["summary"]
        stats = active_acord["manifest"]["stats"]
        with st.container(border=True):
            st.badge("ACORD RAG ready", color="green", icon=":material/check:")
            profile = active_acord["profile"]
            st.markdown(
                f"**{profile['referenceLabel']}** · {profile['referenceVersion']} · "
                f"{profile['sourceFile']}"
            )
            metric_columns = st.columns(4)
            metric_columns[0].metric("Endpoints", summary["endpointCount"])
            metric_columns[1].metric("Entities", summary["entityCount"])
            metric_columns[2].metric("Attributes", summary["attributeCount"])
            metric_columns[3].metric("RAG chunks", stats["chunksIndexed"])
            st.caption(
                "Index: persistent local Chroma · "
                f"Embedding: {stats['embedding']} · Snapshot: "
                f"{active_acord['manifest']['snapshotId'][:12]}"
            )

        st.subheader("ACORD artifact tree")
        st.markdown(
            "ACORD OpenAPI → ACORD ingestion → API Catalog, Data Model, Relationship Graph, "
            "Validation and Enums, and Lineage."
        )
        acord_artifacts: dict[str, bytes] = active_acord["artifacts"]
        for start in range(0, len(ACORD_ARTIFACTS), 3):
            with st.container(horizontal=True):
                for label in list(ACORD_ARTIFACTS)[start : start + 3]:
                    filename = ACORD_ARTIFACTS[label]
                    with st.container(border=True):
                        st.badge("Generated", color="green", icon=":material/check:")
                        st.markdown(f"**{label}**")
                        st.download_button(
                            "Download JSON",
                            data=acord_artifacts[label],
                            file_name=filename,
                            mime="application/json",
                            icon=":material/download:",
                            key=f"download_acord_{active_acord_id}_{filename}",
                        )
        with st.container(horizontal=True):
            st.download_button(
                "Download all five artifacts",
                data=build_acord_bundle(acord_artifacts),
                file_name="acord-ingestion-artifacts.zip",
                mime="application/zip",
                type="primary",
                icon=":material/folder_zip:",
                key=f"download_all_acord_{active_acord_id}",
            )
            st.download_button(
                "Download RAG manifest",
                data=(json.dumps(active_acord["manifest"], indent=2, sort_keys=True) + "\n").encode(
                    "utf-8"
                ),
                file_name="acord-rag-manifest.json",
                mime="application/json",
                icon=":material/download:",
                key=f"download_acord_manifest_{active_acord_id}",
            )
        acord_preview = st.selectbox(
            "Preview ACORD artifact",
            list(acord_artifacts),
            key="acord_artifact_preview",
        )
        st.json(json.loads(acord_artifacts[acord_preview]), expanded=2)

        st.subheader("Inspect ACORD retrieval")
        st.caption(
            "Search the independent index to inspect the exact endpoint/entity chunks that a "
            "later alignment agent would receive."
        )
        with st.form("acord_retrieval", border=False):
            acord_query = st.text_input(
                "Search endpoints, entities, attributes, descriptions, or constraints",
                placeholder="policy postal code constraint",
                key="acord_query",
            )
            acord_search = st.form_submit_button("Search ACORD index", icon=":material/search:")
        if acord_search:
            try:
                acord_index = AcordDocumentIndex(Path(active_acord["storagePath"]))
                try:
                    st.session_state["acord_results"] = acord_index.query(acord_query)
                finally:
                    acord_index.close()
            except (OSError, RuntimeError, ValueError) as exc:
                st.error(str(exc))
        for rank, result in enumerate(st.session_state["acord_results"], start=1):
            with st.expander(
                f"{rank}. {result['kind']} · {result['aliases'][0]} · {result['retrievalReason']}"
            ):
                st.caption(f"Source: {profile['sourceFile']}{result['sourcePointer']}")
                st.code(result["text"], language="text")


def _alignment_review_rows(
    matches: list[dict[str, object]],
    decisions: dict[str, dict[str, object]],
    *,
    child_key: str,
) -> tuple[list[dict[str, object]], list[dict[str, object]]]:
    parent_rows: list[dict[str, object]] = []
    child_rows: list[dict[str, object]] = []
    for match in matches:
        match_id = str(match["regionalId"])
        decision = decisions[match_id]
        candidate = match.get("acordCandidate") or {}
        gaps = match.get("unmatchedDetails") or {}
        parent_rows.append(
            {
                "ID": match_id,
                "Regional": match["regionalName"],
                "Regional description": match.get("regionalDescription") or "",
                "ACORD candidate": candidate.get("name", "No candidate"),
                "ACORD description": candidate.get("description", ""),
                "ACORD comments": json.dumps(candidate.get("comments", [])),
                "Status": match["status"],
                "Match %": match["matchPercent"],
                "Regional gaps": ", ".join(
                    gaps.get("regionalAttributes", gaps.get("regionalCapabilities", []))
                )
                or "—",
                "ACORD-only": ", ".join(
                    gaps.get("acordAttributes", gaps.get("acordCapabilities", []))
                )
                or "—",
                "Decision": decision["selection"],
                "Manual canonical name": decision["manualName"],
                "Reviewer reason": decision["reason"],
            }
        )
        for child in match.get(child_key, []):
            child_id = str(child["regionalId"])
            child_decision = decision[child_key][child_id]
            child_candidate = child.get("acordCandidate") or {}
            child_rows.append(
                {
                    "Parent ID": match_id,
                    "ID": child_id,
                    "Parent": match["regionalName"],
                    "Regional": child["regionalName"],
                    "Regional type": child.get("regionalType", ""),
                    "Regional description": child.get("regionalDescription") or "",
                    "ACORD candidate": child_candidate.get("name", "No candidate"),
                    "ACORD type": child_candidate.get("type", ""),
                    "ACORD description": child_candidate.get("description", ""),
                    "ACORD constraints": json.dumps(
                        child_candidate.get("constraints", {}), sort_keys=True
                    ),
                    "Status": child["status"],
                    "Match %": child["matchPercent"],
                    "Decision": child_decision["selection"],
                    "Manual canonical name": child_decision["manualName"],
                    "Reviewer reason": child_decision["reason"],
                }
            )
    return parent_rows, child_rows


def _render_alignment_editor(
    *,
    title: str,
    matches: list[dict[str, object]],
    decisions: dict[str, dict[str, object]],
    child_key: str,
    child_label: str,
    context: str,
) -> None:
    selected_statuses = st.pills(
        "Show match status",
        MATCH_STATUSES,
        default=[PARTIAL_MATCH, NOT_MATCHED],
        selection_mode="multi",
        key=f"{context}_status",
    )
    visible_statuses = set(selected_statuses or MATCH_STATUSES)
    visible_matches = [item for item in matches if item["status"] in visible_statuses]
    parent_rows, child_rows = _alignment_review_rows(
        visible_matches, decisions, child_key=child_key
    )
    st.markdown(f"#### {title}")
    if not parent_rows:
        st.info("No results match the selected status filter.")
        return
    st.caption(
        "Unmatched and partial rows are selected initially. Choose the ACORD standard or enter "
        "a manual canonical name. A reviewer reason is required for every non-full or manual "
        "decision."
    )
    common_config = {
        "ID": None,
        "Parent ID": None,
        "Decision": st.column_config.SelectboxColumn(options=[USE_ACORD, MANUAL], required=True),
        "Match %": st.column_config.NumberColumn(format="%.1f%%"),
    }
    edited_parents = st.data_editor(
        parent_rows,
        hide_index=True,
        width="stretch",
        key=f"{context}_parents",
        disabled=[
            "ID",
            "Regional",
            "Regional description",
            "ACORD candidate",
            "ACORD description",
            "ACORD comments",
            "Status",
            "Match %",
            "Regional gaps",
            "ACORD-only",
        ],
        column_config=common_config,
    )
    for row in edited_parents:
        decisions[row["ID"]].update(
            {
                "selection": row["Decision"],
                "manualName": row["Manual canonical name"],
                "reason": row["Reviewer reason"],
            }
        )
    st.markdown(f"**{child_label} details and decisions**")
    if not child_rows:
        st.info(f"No {child_label.lower()} are present for these rows.")
        return
    edited_children = st.data_editor(
        child_rows,
        hide_index=True,
        width="stretch",
        key=f"{context}_children",
        disabled=[
            "Parent ID",
            "ID",
            "Parent",
            "Regional",
            "Regional type",
            "Regional description",
            "ACORD candidate",
            "ACORD type",
            "ACORD description",
            "ACORD constraints",
            "Status",
            "Match %",
        ],
        column_config=common_config,
    )
    for row in edited_children:
        decisions[row["Parent ID"]][child_key][row["ID"]].update(
            {
                "selection": row["Decision"],
                "manualName": row["Manual canonical name"],
                "reason": row["Reviewer reason"],
            }
        )


def render_acord_alignment() -> None:
    st.header("ACORD alignment")
    st.caption(
        "Compare a regional catalog with an accepted ACORD reference, resolve each mapping, "
        "and approve a separate canonical artifact without changing either source."
    )
    regions = sorted(
        {
            run.get("profile", {}).get("region")
            for run in st.session_state["application_runs"].values()
            if run.get("discovery_model") and run.get("profile", {}).get("region")
        }
    )
    acord_runs = st.session_state["acord_runs"]
    if not regions or not acord_runs:
        st.info(
            "Alignment requires at least one regional Discovery catalog and one completed "
            "ACORD ingestion.",
            icon=":material/info:",
        )
        return

    selection_columns = st.columns(2, gap="large")
    with selection_columns[0]:
        region = st.selectbox(
            "Regional catalog",
            regions,
            format_func=lambda item: f"{item} · {REGIONS.get(item, item)}",
            key="alignment_region",
        )
    with selection_columns[1]:
        acord_run_id = st.selectbox(
            "ACORD reference",
            list(acord_runs),
            format_func=lambda item: (
                f"{acord_runs[item]['profile']['referenceLabel']} · "
                f"{acord_runs[item]['profile']['referenceVersion']} [{item[:6]}]"
            ),
            key="alignment_acord_reference",
        )

    model_tree = regional_model_tree(st.session_state["application_runs"], region=region)
    domain_tree = regional_domain_tree(st.session_state["application_runs"], region=region)
    _, endpoint_rows = regional_catalog_rows(st.session_state["application_runs"], region=region)
    approved_region = st.session_state["approved_regional_reviews"].get(region)
    regional_source = build_regional_alignment_source(
        region,
        model_tree,
        approved_region["review"] if approved_region else None,
    )
    if not approved_region:
        st.warning(
            "Regional View is not approved. This review uses a deterministic projection of "
            "the current catalog; approve Regional View first for governed regional names."
        )
    if any(item["name"] == "Awaiting API Analyzer" for item in domain_tree):
        st.warning(
            "Some domain/capability values still await API Analyzer and will require a manual "
            "alignment decision."
        )
    proposal = propose_acord_alignment(
        region=region,
        regional_source=regional_source,
        regional_domain_tree=domain_tree,
        regional_endpoints=endpoint_rows,
        acord_model=acord_runs[acord_run_id]["model"],
        acord_run_id=acord_run_id,
    )
    digest = sha256(json.dumps(proposal, sort_keys=True).encode()).hexdigest()[:12]
    context = f"{region}_{acord_run_id}_{digest}"
    decisions = st.session_state["acord_alignment_drafts"].setdefault(
        context, default_alignment_decisions(proposal)
    )
    summary = proposal["matchSummary"]
    metrics = st.columns(5)
    metrics[0].metric("Matched coverage", f"{summary['matchedPercent']:.1f}%")
    metrics[1].metric("Unmatched", f"{summary['unmatchedPercent']:.1f}%")
    metrics[2].metric("Full matches", summary["fullMatch"])
    metrics[3].metric("Partial matches", summary["partialMatch"])
    metrics[4].metric("Not matched", summary["notMatched"])
    st.caption(
        "Coverage weights full matches as 1 and partial matches as 0.5; approval requires an "
        "explicit decision for every item."
    )

    entity_tab, domain_tab = st.tabs(
        ["Regional entities and attributes", "Domains and capabilities"],
        key="alignment_review_tabs",
        on_change="rerun",
    )
    with entity_tab:
        _render_alignment_editor(
            title="Entity match results",
            matches=proposal["entities"],
            decisions=decisions["entities"],
            child_key="attributes",
            child_label="Attribute",
            context=f"entity_{context}",
        )
    with domain_tab:
        _render_alignment_editor(
            title="Domain match results",
            matches=proposal["domains"],
            decisions=decisions["domains"],
            child_key="capabilities",
            child_label="Capability",
            context=f"domain_{context}",
        )

    st.divider()
    st.markdown("#### Approve canonical alignment")
    errors = validate_alignment_decisions(proposal, decisions)
    if errors:
        st.error(f"{len(errors)} review decision(s) remain unresolved.")
        st.markdown("\n".join(f"- {error}" for error in errors[:10]))
    confirmed = st.checkbox(
        "I reviewed all entity, attribute, domain, and capability decisions and approve this "
        "canonical alignment.",
        key=f"alignment_confirmed_{context}",
    )
    if st.button(
        "Approve alignment and generate canonical model",
        type="primary",
        icon=":material/verified:",
        disabled=bool(errors) or not confirmed,
        key=f"approve_alignment_{context}",
    ):
        artifact = approve_acord_alignment(proposal, decisions)
        alignment_id = uuid4().hex
        save_alignment_artifact(ALIGNMENT_HISTORY_ROOT, alignment_id, artifact)
        st.session_state["alignment_reviews"][alignment_id] = artifact
        st.session_state["active_alignment_id"] = alignment_id
        st.success("Approved. Open Canonical view to inspect the model and endpoints.")


def render_canonical_view() -> None:
    st.header("Canonical view")
    st.caption(
        "Inspect canonical entities and endpoints generated only from approved ACORD alignment "
        "decisions."
    )
    alignments = st.session_state["alignment_reviews"]
    if not alignments:
        st.info(
            "No canonical model is approved yet. Resolve and approve an ACORD alignment first.",
            icon=":material/info:",
        )
        return
    alignment_ids = list(reversed(alignments))
    selected_id = st.selectbox(
        "Approved canonical alignment",
        alignment_ids,
        index=(
            alignment_ids.index(st.session_state["active_alignment_id"])
            if st.session_state["active_alignment_id"] in alignments
            else 0
        ),
        format_func=lambda item: (
            f"{alignments[item]['region']} · "
            f"{alignments[item]['acordReference'].get('referenceLabel', 'ACORD')} "
            f"{alignments[item]['acordReference'].get('referenceVersion', '')} [{item[:6]}]"
        ),
        key="approved_canonical_alignment",
    )
    st.session_state["active_alignment_id"] = selected_id
    artifact = alignments[selected_id]
    summary = artifact["summary"]
    metrics = st.columns(5)
    metrics[0].metric("Canonical entities", summary["canonicalEntities"])
    metrics[1].metric("Attributes", summary["canonicalAttributes"])
    metrics[2].metric("Domains", summary["canonicalDomains"])
    metrics[3].metric("Capabilities", summary["canonicalCapabilities"])
    metrics[4].metric("Endpoints", summary["canonicalEndpoints"])
    entity_tab, endpoint_tab, mapping_tab = st.tabs(
        ["Canonical model", "Canonical endpoints", "Approval mappings"],
        key="canonical_result_tabs",
        on_change="rerun",
    )
    with entity_tab:
        for entity in artifact["canonicalModel"]["entities"]:
            with st.expander(
                f"{entity['name']} · {len(entity['attributes'])} attributes · "
                f"{entity['matchStatus']}"
            ):
                st.write(entity.get("description") or "No description available.")
                st.dataframe(
                    [
                        {
                            "Attribute": field["name"],
                            "Type": field["type"],
                            "Required": field["required"],
                            "Description": field.get("description"),
                            "Constraints": json.dumps(field.get("constraints", {}), sort_keys=True),
                            "Standard": field["standard"],
                            "Match": field["matchStatus"],
                            "Reason": field["reviewerReason"],
                        }
                        for field in entity["attributes"]
                    ],
                    hide_index=True,
                    width="stretch",
                )
    with endpoint_tab:
        endpoint_rows = [
            {
                "API": endpoint["api"],
                "Operation": endpoint["operation"],
                "Method": endpoint["method"],
                "Route": endpoint["route"],
                "Domain": endpoint["domain"],
                "Capability": endpoint["capability"],
                "Approved entities": ", ".join(
                    f"{item['entity']} ({item['usage']})" for item in endpoint["entities"]
                )
                or "No mapped entity",
                "Description": endpoint.get("description"),
            }
            for endpoint in artifact["canonicalEndpoints"]
        ]
        st.dataframe(endpoint_rows, hide_index=True, width="stretch")
    with mapping_tab:
        st.dataframe(artifact["alignmentMappings"], hide_index=True, width="stretch")
    st.download_button(
        "Download approved canonical model",
        data=(json.dumps(artifact, indent=2, sort_keys=True) + "\n").encode(),
        file_name=f"{artifact['region'].lower()}-canonical-alignment.json",
        mime="application/json",
        type="primary",
        icon=":material/download:",
        key=f"download_canonical_alignment_{selected_id}",
    )


with acord_alignment_tab:
    render_acord_alignment()

with canonical_view_tab:
    render_canonical_view()

if False:  # Retained temporarily to keep the former placeholder outside the live UI.
    st.header("Canonical view")
    st.badge("Planned", color="gray", icon=":material/schedule:")
    st.caption(
        "Review the future ACORD-to-regional alignment without changing either source catalog."
    )
    entity_column, domain_column, gap_column = st.columns(3)
    with entity_column.container(border=True, height="stretch"):
        st.subheader("Entity alignment", anchor=False)
        st.markdown(
            "Compare ACORD entities and attributes with the approved regional entity catalog."
        )
        st.badge("Awaiting alignment", color="gray", icon=":material/hourglass_empty:")
    with domain_column.container(border=True, height="stretch"):
        st.subheader("Domain and capability alignment", anchor=False)
        st.markdown("Compare ACORD concepts with regional domains and API Analyzer capabilities.")
        st.badge("Awaiting alignment", color="gray", icon=":material/hourglass_empty:")
    with gap_column.container(border=True, height="stretch"):
        st.subheader("ACORD gap identification", anchor=False)
        st.markdown("Report aligned and unaligned regional coverage as counts and percentages.")
        st.metric("Aligned", "—")
        st.metric("Unaligned", "—")
    st.info(
        "Canonical alignment metrics will become available only after ACORD alignment is "
        "implemented and a reviewer accepts its mappings.",
        icon=":material/info:",
    )
