from __future__ import annotations

from pathlib import Path

from canonical_model_generator.application_history import (
    load_application_records,
    save_application_record,
)


def test_application_history_round_trip_preserves_repository_and_artifacts(tmp_path) -> None:
    discovery = Path("tests/fixtures/discovery-model.valid.json").read_bytes()
    application_id = "a" * 32
    run = {
        "profile": {
            "region": "EU",
            "application": "quote-api",
            "repository": "quote.zip",
            "openapi": "quote.yaml",
        },
        "discovery_artifacts": {"API Catalog": b'{"operations": []}'},
        "discovery_projects": ["src/Quote/Quote.csproj"],
        "discovery_model": discovery,
        "repository_archive": b"repository-bytes",
        "rag_store_path": "C:/indexes/quote",
        "rag_manifest": {"version": "1"},
        "phase_2_artifacts": {"semantic-metadata.json": b'{"entities": []}'},
        "phase_2_error": None,
    }

    save_application_record(tmp_path, application_id, run)
    loaded = load_application_records(tmp_path)

    assert loaded[application_id]["profile"] == run["profile"]
    assert loaded[application_id]["repository_archive"] == b"repository-bytes"
    assert loaded[application_id]["discovery_model"] == discovery
    assert loaded[application_id]["discovery_artifacts"] == run["discovery_artifacts"]
    assert loaded[application_id]["phase_2_artifacts"] == run["phase_2_artifacts"]
    assert loaded[application_id]["rag_store_path"] == "C:/indexes/quote"


def test_application_history_ignores_incomplete_record(tmp_path) -> None:
    incomplete = tmp_path / ("b" * 32)
    incomplete.mkdir()
    (incomplete / "record.json").write_text("{}", encoding="utf-8")

    assert load_application_records(tmp_path) == {}
