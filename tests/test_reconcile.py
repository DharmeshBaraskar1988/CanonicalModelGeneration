from pathlib import Path

from canonical_model_generator.discovery_agent.openapi import discover_openapi
from canonical_model_generator.discovery_agent.reconcile import reconcile
from canonical_model_generator.discovery_agent.roslyn import extract_roslyn


def source_models():
    repository = Path("fixtures/RegionalQuoteApi").resolve()
    return (
        extract_roslyn(
            repository / "src/RegionalQuoteApi/RegionalQuoteApi.csproj",
            repository,
            "IN",
            "regional-quote-api-fixture",
        ),
        discover_openapi(repository / "openapi/quote-api.yaml", "IN", "regional-quote-api-fixture"),
    )


def test_reconciliation_merges_evidence_and_is_stable() -> None:
    roslyn, openapi = source_models()
    first = reconcile(roslyn, openapi)
    second = reconcile(roslyn, openapi)

    assert len(first.operations) == 2
    assert [item.name for item in first.entities] == ["CreateQuoteRequest", "QuoteResponse"]
    assert [item.name for item in first.enums] == ["CoverageType", "QuoteStatus"]
    assert len(first.sources) == 4
    create = next(item for item in first.operations if item.method == "POST")
    assert len(create.evidence_ids) == 2
    assert first.model_dump_json(by_alias=True) == second.model_dump_json(by_alias=True)


def test_reconciliation_preserves_in_scope_request_conflicts() -> None:
    roslyn, openapi = source_models()
    request = next(item for item in openapi.entities if item.name == "CreateQuoteRequest")
    name = next(item for item in request.attributes if item.name == "applicantName")
    name.required = not name.required

    result = reconcile(roslyn, openapi)

    assert [item.name for item in result.entities] == ["CreateQuoteRequest", "QuoteResponse"]
    assert any("CreateQuoteRequest.applicantName" in item.message for item in result.diagnostics)
