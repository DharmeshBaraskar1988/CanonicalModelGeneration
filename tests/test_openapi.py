from pathlib import Path

from canonical_model_generator.discovery_agent.openapi import discover_openapi


def test_openapi_fixture_discovers_quote_contract() -> None:
    model = discover_openapi(
        Path("fixtures/RegionalQuoteApi/openapi/quote-api.yaml"),
        "IN",
        "regional-quote-api-fixture",
    )

    assert {(item.method, item.route) for item in model.operations} == {
        ("POST", "/api/v1/quotes"),
        ("GET", "/api/v1/quotes/{quoteId}"),
    }
    assert {item.name for item in model.entities} == {
        "Address",
        "CreateQuoteRequest",
        "QuoteResponse",
        "Vehicle",
    }
    assert {item.name for item in model.enums} == {"CoverageType"}
    assert not model.diagnostics
    assert model.model_validate(model.model_dump()) == model
