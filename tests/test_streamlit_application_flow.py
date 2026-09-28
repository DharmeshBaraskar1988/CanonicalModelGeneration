"""The selected Discovery application controls the RAG and Analyzer handoff."""

from __future__ import annotations

import json
from io import BytesIO
from pathlib import Path
from zipfile import ZipFile

import pytest
from streamlit.testing.v1 import AppTest

import canonical_model_generator.api_analyzer as api_analyzer
from canonical_model_generator.discovery_agent.model import DiscoveryModel
from canonical_model_generator.repository_rag.embeddings import EmbeddingConfig


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
        def __init__(self, *, api_key, model):
            self.model_name = model

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
    app.text_input(key="phase_2_key_override").set_value("session-test-key").run()
    app.checkbox(key="phase_2_source_consent").check().run()
    assert not app.exception
    assert not app.button(key="run_phase_2_semantic_openapi").disabled
    app.button(key="run_phase_2_semantic_openapi").click().run(timeout=120)
    assert not app.exception
    assert captured == [{"region": "US", "system": "second-quote", "repo": True, "rag": index_path}]
    assert app.session_state["phase_2_artifacts"]["enriched-openapi.yaml"]
    assert app.button(key="run_phase_2_semantic_openapi").label == (
        "Run API Analyzer again for selected application"
    )
