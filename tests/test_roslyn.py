from pathlib import Path

from canonical_model_generator.discovery_agent.roslyn import extract_roslyn


def test_roslyn_fixture_discovers_quote_contract() -> None:
    repository = Path("fixtures/RegionalQuoteApi").resolve()
    model = extract_roslyn(
        repository / "src/RegionalQuoteApi/RegionalQuoteApi.csproj",
        repository,
        "IN",
        "regional-quote-api-fixture",
    )

    assert {(item.method, item.route) for item in model.operations} == {
        ("POST", "/api/v1/quotes"),
        ("GET", "/api/v1/quotes/{quoteId:guid}"),
    }
    assert [item.name for item in model.entities] == ["CreateQuoteRequest", "QuoteResponse"]
    assert [item.name for item in model.enums] == ["CoverageType", "QuoteStatus"]
    assert len(model.relationships) == 13
    create = next(item for item in model.operations if item.name == "CreateQuote")
    get = next(item for item in model.operations if item.name == "GetQuote")
    assert create.request_entity_id is not None
    assert create.responses[0].entity_id is not None
    assert get.request_entity_id is None
    assert get.responses[0].entity_id == create.responses[0].entity_id
    assert model.model_validate(model.model_dump()) == model
