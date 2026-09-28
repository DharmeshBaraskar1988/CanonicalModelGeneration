"""Opt-in acceptance: real local embeddings, Streamlit indexing, and attribute retrieval."""

from __future__ import annotations

import json
from io import BytesIO
from pathlib import Path
from zipfile import ZipFile

from streamlit.testing.v1 import AppTest

from canonical_model_generator.discovery_agent.roslyn import extract_roslyn
from canonical_model_generator.repository_rag.index import ChromaRepositoryIndex


def main() -> None:
    repository = Path("fixtures/RegionalQuoteApi").resolve()
    model = extract_roslyn(
        repository / "src/RegionalQuoteApi/RegionalQuoteApi.csproj",
        repository,
        "IN",
        "regional-quote-api-fixture",
    )
    buffer = BytesIO()
    with ZipFile(buffer, "w") as archive:
        for path in sorted(repository.rglob("*")):
            if path.is_file() and not {"bin", "obj"}.intersection(
                path.relative_to(repository).parts
            ):
                archive.writestr(path.relative_to(repository).as_posix(), path.read_bytes())
    app = AppTest.from_file(str(Path("streamlit_app.py").resolve()), default_timeout=120)
    app.session_state["repository_archive"] = buffer.getvalue()
    app.session_state["discovery_model"] = model.model_dump_json(by_alias=True).encode()
    app.session_state["phase_2_unlocked"] = True
    app.run()
    assert not app.exception, [item.value for item in app.exception]
    app.button(key="build_rag").click().run(timeout=180)
    assert not app.exception, [item.value for item in app.exception]
    manifest = app.session_state["rag_manifest"]
    assert manifest is not None, [item.value for item in app.error]
    active_id = app.session_state["active_application_id"]
    active_run = app.session_state["application_runs"][active_id]
    assert active_run["profile"]["region"] == "IN"
    assert active_run["profile"]["application"] == "regional-quote-api-fixture"
    assert active_run["rag_store_path"] == app.session_state["rag_store_path"]
    assert app.button(key="run_phase_2_semantic_openapi").disabled
    app.text_input(key="phase_2_key_override").set_value("fixture-test-key").run()
    app.checkbox(key="phase_2_source_consent").check().run()
    assert not app.exception, [item.value for item in app.exception]
    assert not app.button(key="run_phase_2_semantic_openapi").disabled
    next(widget for widget in app.selectbox if widget.label == "Retrieve by").select(
        "attribute"
    ).run()
    premium = next(
        target
        for target in manifest["targets"]
        if target["kind"] == "attribute" and target["label"].endswith("QuoteResponse.Premium")
    )
    app.selectbox(key="rag_target_attribute").set_value(premium["id"]).run()
    app.button(key="retrieve_rag").click().run(timeout=120)
    assert not app.exception, [item.value for item in app.exception]
    hits = app.session_state["rag_results"]
    assert hits and hits[0]["kind"] == "PropertyDeclaration", [item.value for item in app.error]
    assert hits[0]["symbol"].endswith("QuoteResponse.Premium")
    assert hits[0]["retrievalReason"] == "exact-lineage"
    assert app.button(key="rag_explain_target") is not None
    next(widget for widget in app.selectbox if widget.label == "Retrieve by").select(
        "code query"
    ).run()
    next(widget for widget in app.text_input if widget.label == "Code query").set_value(
        "CalculatePremium"
    ).run()
    app.button(key="retrieve_rag").click().run(timeout=120)
    assert not app.exception, [item.value for item in app.exception]
    assert app.session_state["rag_results"]
    assert app.button(key="rag_explain_target") is not None
    location = Path(app.session_state["rag_store_path"])
    reopened = ChromaRepositoryIndex(location)
    try:
        reopened.validate_snapshot(repository, model)
        again = reopened.query(premium["label"], subject_id=premium["id"])
        assert [h["chunkId"] for h in hits] == [h["chunkId"] for h in again]
    finally:
        reopened.close()
    evidence = {
        "stats": manifest["stats"],
        "index": str(location),
        "embedding": manifest["embedding"],
        "selectedApplication": active_run["profile"],
        "analyzerReadyWithSessionKeyAndConsent": True,
        "target": premium,
        "firstHit": {
            key: hits[0][key]
            for key in ("symbol", "path", "startLine", "endLine", "retrievalReason")
        },
        "streamlitExceptions": 0,
        "reopenMatches": True,
    }
    output = Path(".tmp/rag-acceptance.json")
    output.parent.mkdir(exist_ok=True)
    output.write_text(json.dumps(evidence, indent=2), encoding="utf-8")
    print(json.dumps(evidence, indent=2))


if __name__ == "__main__":
    main()
