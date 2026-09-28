import json
from pathlib import Path

from canonical_model_generator.discovery_agent.workflow import run_discovery


def test_graph_runs_complete_fixture_and_generates_valid_artifacts(tmp_path: Path) -> None:
    repository = Path("fixtures/RegionalQuoteApi").resolve()
    output = tmp_path / "artifacts"
    state = run_discovery(
        region="IN",
        system="regional-quote-api-fixture",
        repository=repository,
        project=repository / "src/RegionalQuoteApi/RegionalQuoteApi.csproj",
        openapi=repository / "openapi/quote-api.yaml",
        output=output,
    )

    assert not state["errors"]
    assert [item["status"] for item in state["events"]] == ["ok"] * 6
    assert set(path.name for path in output.iterdir()) == {
        "discovery-model.json",
        "api-catalog.json",
        "data-model.json",
        "relationship-graph.json",
        "validation-enums.json",
        "lineage.json",
    }
    discovery = json.loads((output / "discovery-model.json").read_text(encoding="utf-8"))
    assert discovery["summary"]["operationCount"] == 2
    assert discovery["summary"]["entityCount"] == 2
    catalog = json.loads((output / "api-catalog.json").read_text(encoding="utf-8"))
    create_quote = next(
        item for item in catalog["operations"] if item["operation"] == "CreateQuote"
    )
    assert create_quote["requestModel"] == "CreateQuoteRequest"
    assert create_quote["requestModelTree"]["rootModel"] == "CreateQuoteRequest"
    assert create_quote["responses"][0]["responseModel"] == "QuoteResponse"


def test_graph_stops_safely_for_invalid_input(tmp_path: Path) -> None:
    state = run_discovery(
        region="IN",
        system="missing",
        repository=tmp_path,
        project=tmp_path / "missing.csproj",
        openapi=tmp_path / "missing.yaml",
        output=tmp_path / "output",
    )

    assert state["errors"]
    assert not (tmp_path / "output").exists()
    assert state["events"][1]["status"] == "skipped"
