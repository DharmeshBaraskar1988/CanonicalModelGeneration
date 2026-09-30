"""The selected Discovery application controls the RAG and Analyzer handoff."""

from __future__ import annotations

import json
from io import BytesIO
from pathlib import Path
from zipfile import ZipFile

import pytest
from streamlit.testing.v1 import AppTest

import canonical_model_generator.acord_rag as acord_rag
import canonical_model_generator.api_analyzer as api_analyzer
import canonical_model_generator.openai_config as openai_config
from canonical_model_generator.acord_rag import (
    build_acord_chunks,
    generate_acord_artifacts,
    parse_acord_document,
)
from canonical_model_generator.acord_rag import history as acord_history
from canonical_model_generator.alignment_agent import save_alignment_artifact
from canonical_model_generator.discovery_agent.model import DiscoveryModel
from canonical_model_generator.repository_rag.embeddings import EmbeddingConfig


def test_acord_alignment_renders_entity_domain_and_approval_workspaces(
    tmp_path, monkeypatch
) -> None:
    monkeypatch.setenv("ALIGNMENT_AGENT_DATABASE", str(tmp_path / "alignment-agent.sqlite3"))
    discovery = Path("tests/fixtures/discovery-model.valid.json").read_bytes()
    specification = Path("fixtures/RegionalQuoteApi/openapi/quote-api.yaml").read_bytes()
    acord_model = parse_acord_document(
        specification,
        "acord-quote.yaml",
        reference_label="ACORD Quote",
        reference_version="2026.1",
    )
    acord_artifacts = generate_acord_artifacts(acord_model)
    chunks = build_acord_chunks(acord_model)
    app = AppTest.from_file(
        str(Path(__file__).resolve().parents[1] / "streamlit_app.py"), default_timeout=120
    )
    app.session_state["application_runs"] = {
        "regional": {
            "profile": {
                "region": "EU",
                "application": "Quote API",
                "repository": "quote.zip",
                "openapi": "quote-api.yaml",
            },
            "discovery_artifacts": {},
            "discovery_projects": [],
            "discovery_model": discovery,
            "repository_archive": None,
            "rag_store_path": None,
            "rag_manifest": None,
            "phase_2_artifacts": {},
        }
    }
    app.session_state["acord_runs"] = {
        "acord": {
            "profile": {
                "runId": "acord",
                "sourceFile": "acord-quote.yaml",
                "referenceLabel": "ACORD Quote",
                "referenceVersion": "2026.1",
                "sha256": acord_model["source"]["sha256"],
            },
            "model": acord_model,
            "artifacts": acord_artifacts,
            "manifest": {
                "snapshotId": "alignment-test-snapshot",
                "stats": {
                    "chunksIndexed": len(chunks),
                    "embedding": {"provider": "local", "model": "test"},
                },
            },
            "storagePath": ".acord/test/index",
            "stats": {},
        }
    }
    app.session_state["active_acord_id"] = "acord"
    app.session_state["workflow_tabs"] = ":material/compare_arrows: ACORD alignment"

    app.run()

    assert not app.exception
    assert any(item.label == "Regional catalog" for item in app.selectbox)
    tab_labels = [tab.label for tab in app.tabs]
    assert "Regional entities and attributes" in tab_labels
    assert "Domains and capabilities" in tab_labels
    assert any(item.label == "Entity review status" for item in app.radio)
    assert any(item.label == "Attribute review status" for item in app.radio)
    assert any(item.label == "Domain review status" for item in app.radio)
    assert any(item.label == "Capability review status" for item in app.radio)
    assert any(item.label == "Approve this entity match" for item in app.checkbox)
    assert any(item.label == "Approve this attribute match" for item in app.checkbox)
    assert any(item.label == "Approve this domain match" for item in app.checkbox)
    assert any(item.label == "Approve this capability match" for item in app.checkbox)
    assert not any(item.label == "Attribute to review" for item in app.selectbox)
    assert any("**applicantName**" in item.value for item in app.markdown)
    assert any(item.label == "Entity description" for item in app.text_area)
    assert any(item.label == "Entity reviewer reason" for item in app.text_area)
    assert any(item.label == "Filter entity tree nodes by proposed status" for item in app.pills)
    assert any(item.label == "Filter domain tree nodes by proposed status" for item in app.pills)
    assert any(item.label.startswith("Bulk entity reviewer reason") for item in app.text_area)
    assert any(item.label.startswith("Bulk domain reviewer reason") for item in app.text_area)
    assert any(button.label == "Approve all filtered entity nodes" for button in app.button)
    assert any(button.label == "Approve all filtered domain nodes" for button in app.button)
    assert any("entity/attribute nodes" in item.label for item in app.checkbox)
    assert any("domain/capability nodes" in item.label for item in app.checkbox)
    unresolved_message = next(
        item.value for item in app.error if "review decision(s) remain unresolved" in item.value
    )
    unresolved_count = int(unresolved_message.split()[0])
    assert any(
        item.value == f"Showing all {unresolved_count} unresolved decisions below."
        for item in app.caption
    )
    assert any("Awaiting explicit approval" in item.value for item in app.markdown)
    assert any(
        ("item(s) to fix" in item.value or "Other missing or invalid details" in item.value)
        for item in app.markdown
    )

    bulk_reason = next(
        item for item in app.text_area if item.label.startswith("Bulk entity reviewer reason")
    )
    bulk_confirmation = next(
        item for item in app.checkbox if "entity/attribute nodes" in item.label
    )
    bulk_reason.set_value("Reviewed together against the accepted ACORD reference.")
    bulk_confirmation.set_value(True)
    app.run()
    next(
        button for button in app.button if button.label == "Approve all filtered entity nodes"
    ).click().run()
    assert not app.exception
    assert all(item.value for item in app.checkbox if item.label == "Approve this entity match")
    assert all(item.value for item in app.checkbox if item.label == "Approve this attribute match")

    domain_reason = next(
        item for item in app.text_area if item.label.startswith("Bulk domain reviewer reason")
    )
    domain_confirmation = next(
        item for item in app.checkbox if "domain/capability nodes" in item.label
    )
    domain_reason.set_value("Reviewed domain and capability matches together.")
    domain_confirmation.set_value(True)
    app.run()
    next(
        button for button in app.button if button.label == "Approve all filtered domain nodes"
    ).click().run()
    assert not app.exception
    assert any("Approved" in item.value for item in app.success)
    assert all(item.value for item in app.checkbox if item.label == "Approve this domain match")
    assert all(item.value for item in app.checkbox if item.label == "Approve this capability match")
    assert any(button.label == "Submit and save canonical v1" for button in app.button)


def test_phase_two_selects_the_matching_region_repository_and_discovery_artifact(
    tmp_path, monkeypatch
):
    model = DiscoveryModel.model_validate_json(
        Path("tests/fixtures/discovery-model.valid.json").read_bytes()
    )
    first = model.model_copy(update={"region": "IN", "system": "first-quote"})
    second = model.model_copy(update={"region": "US", "system": "second-quote"})
    archive = BytesIO()
    repository = Path("fixtures/RegionalQuoteApi")
    with ZipFile(archive, "w") as bundle:
        for path in sorted(repository.rglob("*")):
            if path.is_file() and not {"bin", "obj"}.intersection(
                path.relative_to(repository).parts
            ):
                bundle.writestr(path.relative_to(repository).as_posix(), path.read_bytes())
    repository_bytes = archive.getvalue()
    index_path = tmp_path / "saved-rag"
    index_path.mkdir()
    (index_path / "rag-manifest.json").write_text("{}", encoding="utf-8")
    profile = EmbeddingConfig().model_dump()

    def run_record(region, name, filename, discovery, rag=None):
        return {
            "profile": {
                "region": region,
                "application": name,
                "repository": filename,
                "openapi": "quote-api.yaml",
            },
            "discovery_artifacts": {},
            "discovery_projects": ["src/RegionalQuoteApi/RegionalQuoteApi.csproj"],
            "discovery_model": discovery,
            "repository_archive": repository_bytes,
            "rag_store_path": str(rag) if rag else None,
            "rag_manifest": (
                {
                    "embedding": profile,
                    "targets": [],
                    "stats": {
                        "filesIndexed": 1,
                        "chunksIndexed": 1,
                        "relationshipsIndexed": 0,
                        "gaps": [],
                    },
                }
                if rag
                else None
            ),
            "phase_2_artifacts": {},
        }

    runs = {
        "first": run_record(
            "IN", "first-quote", "india.zip", first.model_dump_json(by_alias=True).encode()
        ),
        "second": run_record(
            "US",
            "second-quote",
            "us-quote.zip",
            second.model_dump_json(by_alias=True).encode(),
            index_path,
        ),
    }
    captured = []

    class FakeProvider:
        def __init__(self, *, api_key, model, token_budget=None):
            self.model_name = model
            self.token_budget = token_budget

    def fake_agent(discovery_artifact, repository_root, provider, progress=None, **kwargs):
        parsed = DiscoveryModel.model_validate_json(discovery_artifact)
        captured.append(
            {
                "region": parsed.region,
                "system": parsed.system,
                "repo": (
                    Path(repository_root) / "src/RegionalQuoteApi/RegionalQuoteApi.csproj"
                ).is_file(),
                "rag": kwargs["rag_store_path"],
            }
        )
        report = {
            "providerStatus": "ready",
            "status": "complete",
            "endpointsDiscovered": 0,
            "endpointsEnriched": 0,
            "domainsClassified": 0,
            "capabilitiesClassified": 0,
            "entitiesDiscovered": 0,
            "entitiesEnriched": 0,
            "attributesEnriched": 0,
            "enumsEnriched": 0,
            "needsMoreContextTargets": [],
            "validationErrors": [],
            "retrieval": {},
        }
        return {
            "enriched-openapi.yaml": b"openapi: 3.0.3\n",
            "semantic-metadata.json": b"{}",
            "evidence-map.json": b"{}",
            "enrichment-report.json": json.dumps(report).encode(),
        }

    monkeypatch.setattr(api_analyzer, "OpenAISemanticProvider", FakeProvider)
    monkeypatch.setattr(api_analyzer, "run_api_analyzer_agent", fake_agent)
    monkeypatch.setattr(openai_config, "resolve_openai_api_key", lambda **_: None)
    monkeypatch.setattr(openai_config, "resolve_openai_model", lambda **_: "env-model")
    app = AppTest.from_file(
        str(Path(__file__).resolve().parents[1] / "streamlit_app.py"), default_timeout=120
    )
    app.session_state["application_runs"] = runs
    app.session_state["active_application_id"] = "first"
    app.session_state["discovery_model"] = runs["first"]["discovery_model"]
    app.session_state["repository_archive"] = repository_bytes
    app.session_state["phase_2_unlocked"] = True
    app.run()
    assert not app.exception
    expected_crawler_tabs = [
        ":material/account_tree: 1 Discovery",
        ":material/search: 2 Repository RAG",
        ":material/manage_search: 3 API analyzer",
        ":material/public: 4 Regional view",
    ]
    removed_acord_tabs = {
        ":material/library_books: ACORD ingestion",
        ":material/compare_arrows: ACORD alignment",
        ":material/hub: Canonical model",
    }
    assert [tab.label for tab in app.tabs[:4]] == expected_crawler_tabs
    assert not removed_acord_tabs.intersection(tab.label for tab in app.tabs)
    crawler_menu = next(pills for pills in app.pills if pills.key == "crawler_sidebar_menu")
    assert crawler_menu.options == [
        "1 Discovery",
        "2 Repository RAG",
        "3 API analyzer",
        "4 Regional view",
    ]
    acord_menu = next(pills for pills in app.pills if pills.key == "acord_sidebar_menu")
    assert acord_menu.options == [
        "ACORD ingestion",
        "ACORD alignment",
        "Canonical model",
    ]
    with pytest.raises(KeyError):
        app.text_input(key="openai_api_key_override")
    with pytest.raises(KeyError):
        app.text_input(key="phase_2_openai_model")
    with pytest.raises(KeyError):
        app.text_input(key="phase_2_key_override")
    with pytest.raises(KeyError):
        app.text_input(key="regional_review_key")
    assert app.file_uploader(key="acord_document").label == "ACORD OpenAPI documents"
    assert app.checkbox(key="acord_usage_authorized").label.startswith("I confirm")
    assert any(button.label == "Build ACORD RAG index" for button in app.button)
    acord_menu.set_value(":material/compare_arrows: ACORD alignment").run()
    assert app.session_state["workflow_tabs"] == ":material/compare_arrows: ACORD alignment"
    acord_menu = next(pills for pills in app.pills if pills.key == "acord_sidebar_menu")
    acord_menu.set_value(":material/hub: Canonical model").run()
    assert app.session_state["workflow_tabs"] == ":material/hub: Canonical model"
    assert any("No canonical model is approved yet" in item.value for item in app.info)
    crawler_menu = next(pills for pills in app.pills if pills.key == "crawler_sidebar_menu")
    crawler_menu.set_value(":material/search: 2 Repository RAG").run()
    assert app.session_state["workflow_tabs"] == ":material/search: 2 Repository RAG"
    assert any("Agent workflow" in item.value for item in app.subheader)
    with pytest.raises(KeyError):
        app.selectbox(key="rag_saved_index")
    assert app.button(key="run_phase_2_semantic_openapi").disabled
    app.selectbox(key="phase2_application_first").set_value("second").run()
    assert not app.exception
    assert app.session_state["active_application_id"] == "second"
    assert app.session_state["rag_store_path"] == str(index_path)
    app.selectbox(key="phase2_application_second").set_value("first").run()
    assert not app.exception
    assert app.session_state["active_application_id"] == "first"
    assert app.session_state["rag_store_path"] is None
    app.selectbox(key="phase2_application_first").set_value("second").run()
    assert not app.exception
    assert app.session_state["active_application_id"] == "second"
    monkeypatch.setattr(openai_config, "resolve_openai_api_key", lambda **_: "env-test-key")
    app.checkbox(key="phase_2_source_consent").check().run()
    assert any("OpenAI model from .env: env-model" in item.value for item in app.caption)
    assert not app.exception
    assert not app.button(key="run_phase_2_semantic_openapi").disabled
    app.button(key="run_phase_2_semantic_openapi").click().run(timeout=120)
    assert not app.exception
    assert captured == [{"region": "US", "system": "second-quote", "repo": True, "rag": index_path}]
    assert app.session_state["phase_2_artifacts"]["enriched-openapi.yaml"]
    with pytest.raises(KeyError):
        app.text_input(key="regional_normalization_model")
    assert app.button(key="run_phase_2_semantic_openapi").label == (
        "Restart API Analyzer from beginning"
    )


def test_acord_yaml_upload_survives_input_reruns_and_reaches_ingestion(tmp_path, monkeypatch):
    class FakeAcordIndex:
        def __init__(self, storage_path):
            self.storage_path = Path(storage_path)
            self.manifest = {}

        def ingest(self, model, chunks, *, progress=None):
            if progress:
                progress(f"Embedded {len(chunks)}/{len(chunks)} ACORD chunks")
            stats = {
                "provider": "chroma",
                "embedding": "test-embedding",
                "documentsIndexed": 1,
                "chunksIndexed": len(chunks),
                "endpointChunks": sum(item["kind"] == "endpoint" for item in chunks),
                "entityChunks": sum(item["kind"] == "entity" for item in chunks),
                "storage": "persistent-local",
                "dimensions": 3,
            }
            self.manifest = {
                "schemaVersion": "acord-rag/1.0",
                "snapshotId": "test-snapshot",
                "source": model["source"],
                "chunks": chunks,
                "stats": stats,
            }
            return stats

        def close(self):
            pass

    def fake_save(root, run_id, **kwargs):
        run_path = tmp_path / run_id
        (run_path / "index").mkdir(parents=True)
        return run_path

    monkeypatch.setattr(acord_rag, "AcordDocumentIndex", FakeAcordIndex)
    monkeypatch.setattr(acord_history, "load_acord_records", lambda root: {})
    monkeypatch.setattr(acord_history, "save_acord_record", fake_save)

    spec = Path("fixtures/RegionalQuoteApi/openapi/quote-api.yaml").read_bytes()
    app = AppTest.from_file(
        str(Path(__file__).resolve().parents[1] / "streamlit_app.py"), default_timeout=120
    )
    app.run()
    app.file_uploader(key="acord_document").upload("quote-api.yaml", spec, "application/yaml").run()
    assert any("Specification selected: **quote-api.yaml**" in item.value for item in app.success)

    app.text_input(key="acord_reference_label").set_value("ACORD quote API").run()
    app.text_input(key="acord_reference_version").set_value("2026.1").run()
    app.checkbox(key="acord_usage_authorized").check().run()
    assert any("Specification selected: **quote-api.yaml**" in item.value for item in app.success)

    app.button(key="build_acord_rag_index").click().run(timeout=120)
    assert not app.exception
    assert not any("Required input missing" in item.value for item in app.error)
    assert app.session_state["active_acord_id"] in app.session_state["acord_runs"]
    assert any(item.value == "ACORD download gallery" for item in app.subheader)
    assert any(
        button.key and button.key.startswith("download_acord_")
        for button in app.download_button
        if button.label == "Download JSON"
    )


def test_discovery_artifacts_render_in_right_side_download_gallery() -> None:
    labels = [
        "API Catalog",
        "Data Model",
        "Relationship Graph",
        "Validation and enums",
        "Lineage",
    ]
    artifacts = {label: b"{}" for label in labels}
    app = AppTest.from_file(
        str(Path(__file__).resolve().parents[1] / "streamlit_app.py"), default_timeout=120
    )
    app.session_state["application_runs"] = {
        "discovery": {
            "profile": {
                "region": "EU",
                "application": "Quote API",
                "repository": "quote.zip",
                "openapi": "quote-api.yaml",
            },
            "discovery_artifacts": artifacts,
            "discovery_projects": ["src/QuoteApi/QuoteApi.csproj"],
            "discovery_model": Path("tests/fixtures/discovery-model.valid.json").read_bytes(),
            "repository_archive": None,
            "rag_store_path": None,
            "rag_manifest": None,
            "phase_2_artifacts": {},
        }
    }
    app.session_state["active_application_id"] = "discovery"
    app.session_state["discovery_artifacts"] = artifacts
    app.session_state["discovery_projects"] = ["src/QuoteApi/QuoteApi.csproj"]

    app.run()

    assert not app.exception
    assert any(item.value == "Discovery download gallery" for item in app.subheader)
    assert (
        len(
            [
                button
                for button in app.download_button
                if button.key and button.key.startswith("download_discovery_")
            ]
        )
        == 6
    )


def test_saved_acord_alignment_can_be_deleted_without_canonical_versions(
    tmp_path, monkeypatch
) -> None:
    alignment_id = "d" * 32
    artifact = {
        "status": "Approved",
        "region": "EU",
        "acordReference": {"referenceLabel": "ACORD Quote", "referenceVersion": "2026.1"},
        "summary": {
            "canonicalEntities": 0,
            "canonicalAttributes": 0,
            "canonicalDomains": 0,
            "canonicalCapabilities": 0,
            "canonicalEndpoints": 0,
        },
        "canonicalModel": {"entities": []},
        "canonicalEndpoints": [],
        "alignmentMappings": [],
    }
    history_root = tmp_path / "alignments"
    save_alignment_artifact(history_root, alignment_id, artifact)
    monkeypatch.setenv("ALIGNMENT_HISTORY_ROOT", str(history_root))
    monkeypatch.setenv("ALIGNMENT_AGENT_DATABASE", str(tmp_path / "alignment-agent.sqlite3"))
    app = AppTest.from_file(
        str(Path(__file__).resolve().parents[1] / "streamlit_app.py"), default_timeout=120
    )
    app.session_state["alignment_reviews"] = {alignment_id: artifact}
    app.session_state["active_alignment_id"] = alignment_id
    app.session_state["workflow_tabs"] = ":material/hub: Canonical model"

    app.run()
    app.button(key=f"request_delete_alignment_{alignment_id}").click().run()

    assert any("Submitted canonical versions" in item.value for item in app.warning)
    confirmation = app.checkbox(key=f"confirm_delete_alignment_{alignment_id}")
    confirmation.check().run()
    app.button(key=f"delete_alignment_{alignment_id}").click().run()

    assert not app.exception
    assert not (history_root / alignment_id).exists()
    assert app.session_state["alignment_reviews"] == {}
    assert any("Submitted canonical versions were retained" in item.value for item in app.success)
