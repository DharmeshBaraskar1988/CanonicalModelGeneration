from __future__ import annotations

import json
import os
import sys
from collections.abc import Callable
from io import BytesIO
from pathlib import Path, PurePosixPath
from tempfile import TemporaryDirectory
from zipfile import ZIP_DEFLATED, ZipFile

import streamlit as st
from dotenv import load_dotenv
from streamlit.typing import UploadedFile

sys.path.insert(0, str(Path(__file__).resolve().parent / "src"))
load_dotenv(Path(__file__).resolve().parent / ".env", override=True)

from canonical_model_generator.artifacts import generate_artifacts  # noqa: E402
from canonical_model_generator.intake import (  # noqa: E402
    IntakeError,
    inspect_repository_zip,
    validate_openapi,
)
from canonical_model_generator.model import DiscoveryModel  # noqa: E402
from canonical_model_generator.openapi import discover_openapi  # noqa: E402
from canonical_model_generator.reconcile import reconcile  # noqa: E402
from canonical_model_generator.roslyn import extract_roslyn, merge_roslyn_models  # noqa: E402
from canonical_model_generator.semantic_openapi import (  # noqa: E402
    OpenAISemanticProvider,
    run_api_analyzer_agent,
)

st.set_page_config(
    page_title="Insurance Canonical Model Platform",
    page_icon=":material/account_tree:",
    layout="wide",
)

DISCOVERY_ARTIFACTS = {
    "API Catalog": "api-catalog.json",
    "Data Model": "data-model.json",
    "Relationship Graph": "relationship-graph.json",
    "Validation and enums": "validation-enums.json",
    "Lineage": "lineage.json",
}

st.session_state.setdefault("discovery_artifacts", {})
st.session_state.setdefault("discovery_projects", [])
st.session_state.setdefault("discovery_model", None)
st.session_state.setdefault("repository_archive", None)
st.session_state.setdefault("phase_2_unlocked", False)
st.session_state.setdefault("phase_2_artifacts", {})


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


def run_uploaded_semantic_generation(
    *,
    repository_archive: bytes,
    discovery_model: DiscoveryModel,
    provider: OpenAISemanticProvider,
    progress: Callable[[str], None] | None = None,
) -> dict[str, bytes]:
    inspect_repository_zip(repository_archive)
    with TemporaryDirectory(prefix="canonical-semantic-openapi-") as temporary:
        repository = Path(temporary) / "repository"
        repository.mkdir()
        with ZipFile(BytesIO(repository_archive)) as zip_file:
            zip_file.extractall(repository)
        return run_api_analyzer_agent(discovery_model, repository, provider, progress)


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
    repository_file: UploadedFile,
    openapi_file: UploadedFile | None,
) -> tuple[dict[str, bytes], list[str], bytes]:
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


st.title("Insurance Canonical Model platform")

discovery_tab, phase_two_tab = st.tabs(
    [
        ":material/account_tree: Discovery Agent",
        ":material/manage_search: Phase 2 API Analyzer",
    ]
)

with discovery_tab:
    st.header("Discovery Agent")
    with st.form("discovery_agent", border=True):
        region = st.text_input("Region", placeholder="IN", key="region")
        system = st.text_input("Source system", placeholder="regional-quote-api", key="system")
        repository_file: UploadedFile | None = st.file_uploader(
            "Trusted .NET repository ZIP",
            type="zip",
            max_upload_size=100,
            help="The repository is extracted and analyzed with Roslyn/MSBuild as trusted code.",
            key="repository_zip",
        )
        openapi_file: UploadedFile | None = st.file_uploader(
            "OpenAPI document (optional)",
            type=["json", "yaml", "yml"],
            max_upload_size=10,
            help=(
                "Without OpenAPI, the agent generates the five artifacts from Roslyn "
                "source analysis."
            ),
            key="openapi_document",
        )
        submitted = st.form_submit_button(
            "Run Discovery Agent", type="primary", icon=":material/play_arrow:"
        )

    if submitted:
        st.session_state["discovery_artifacts"] = {}
        st.session_state["discovery_projects"] = []
        st.session_state["discovery_model"] = None
        st.session_state["repository_archive"] = None
        st.session_state["phase_2_unlocked"] = False
        st.session_state["phase_2_artifacts"] = {}
        if not region.strip() or not system.strip() or repository_file is None:
            st.error("Region, source system, and repository ZIP are required.")
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
                    st.session_state["discovery_artifacts"] = artifacts
                    st.session_state["discovery_projects"] = selected_projects
                    st.session_state["discovery_model"] = discovery_model
                    st.session_state["repository_archive"] = repository_file.getvalue()
                    st.session_state["phase_2_unlocked"] = True
                    status.update(label="Discovery complete", state="complete", expanded=False)
            except (IntakeError, OSError, RuntimeError, ValueError) as exc:
                st.error(str(exc))

    artifacts: dict[str, bytes] = st.session_state["discovery_artifacts"]
    if artifacts:
        st.caption("Analyzed projects: " + ", ".join(st.session_state["discovery_projects"]))
        st.warning(
            "Current entity coverage is limited to user-authored ViewModels and concrete request/"
            "response models reachable from API endpoints. Base infrastructure classes, DTOs, "
            "domain types, generated types, and unrelated models are excluded. "
            "Deep call paths, persistence, mappings, integrations, security, and Razor Pages "
            "remain open gaps.",
            icon=":material/radar:",
        )
        st.subheader("Discovery artifact tree")
        st.mermaid_chart(
            """
flowchart TD
    REPO[Uploaded .NET repository] --> AGENT[Discovery Agent]
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

with phase_two_tab:
    if not st.session_state["phase_2_unlocked"]:
        st.info(
            "Run the Discovery Agent successfully to unlock Phase 2.",
            icon=":material/lock:",
        )
    else:
        st.success(
            "Phase 1 is complete for this repository. Its validated result is ready "
            "for evidence-grounded semantic OpenAPI generation.",
            icon=":material/lock_open:",
        )
        st.header("API Analyzer Agent")
        st.caption(
            "The agent ingests the redacted repository into a local Chroma vector index, retrieves "
            "bounded code evidence, classifies domain and capability, and explains endpoints, "
            "endpoint contract models, attributes, and enums before generating a self-contained "
            "enriched OpenAPI 3.0 specification. Structural facts continue to come only from "
            "Phase 1."
        )
        model_available = (
            st.session_state["discovery_model"] is not None
            and st.session_state["repository_archive"] is not None
        )
        if not model_available:
            st.info(
                "Run the Discovery Agent once after this update to provide the validated "
                "Phase 1 model and repository snapshot to Phase 2.",
                icon=":material/info:",
            )
        api_key = openai_api_key()
        if api_key:
            st.badge("OpenAI configured", color="green", icon=":material/check:")
        else:
            st.warning(
                "Set OPENAI_API_KEY in the environment or Streamlit secrets before running "
                "semantic generation. The key is never written to an artifact.",
                icon=":material/key:",
            )
        openai_model = st.text_input(
            "OpenAI model",
            value=os.getenv("OPENAI_MODEL", "gpt-4o-mini"),
            help="The model must support Structured Outputs in the Responses API.",
            key="phase_2_openai_model",
        )
        source_consent = st.checkbox(
            "I understand that selected, redacted source-code fragments will be sent to OpenAI.",
            key="phase_2_source_consent",
        )
        if st.button(
            "Run API Analyzer Agent",
            type="primary",
            icon=":material/auto_awesome:",
            key="run_phase_2_semantic_openapi",
            disabled=not model_available
            or not api_key
            or not source_consent
            or not openai_model.strip(),
        ):
            try:
                discovery_model = DiscoveryModel.model_validate_json(
                    st.session_state["discovery_model"]
                )
                provider = OpenAISemanticProvider(api_key=api_key or "", model=openai_model.strip())
                with st.status("Running API Analyzer Agent...", expanded=True) as status:
                    generated = run_uploaded_semantic_generation(
                        repository_archive=st.session_state["repository_archive"],
                        discovery_model=discovery_model,
                        provider=provider,
                        progress=st.write,
                    )
                    st.session_state["phase_2_artifacts"] = generated
                    generated_report = json.loads(generated["enrichment-report.json"])
                    if generated_report["providerStatus"] == "failed":
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
            except Exception as exc:
                st.error(f"Semantic OpenAPI generation failed: {exc}")

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
