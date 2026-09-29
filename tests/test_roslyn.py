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
    assert [item.name for item in model.entities] == [
        "AddressDto",
        "CreateQuoteRequest",
        "QuoteResponse",
        "VehicleDto",
    ]
    assert [item.name for item in model.enums] == ["CoverageType", "QuoteStatus"]
    assert len(model.relationships) == 19
    create = next(item for item in model.operations if item.name == "CreateQuote")
    get = next(item for item in model.operations if item.name == "GetQuote")
    assert create.request_entity_id is not None
    assert create.responses[0].entity_id is not None
    assert get.request_entity_id is None
    assert get.responses[0].entity_id == create.responses[0].entity_id
    assert model.model_validate(model.model_dump()) == model


def test_syntax_degraded_controller_keeps_request_response_and_nested_models() -> None:
    repository = Path("fixtures/SyntaxDegradedClaimsApi").resolve()
    model = extract_roslyn(
        repository / "SyntaxDegradedClaimsApi.csproj",
        repository,
        "EU",
        "syntax-degraded-claims-api",
    )

    assert [item.name for item in model.entities] == [
        "ClaimAddress",
        "ClaimDto",
        "InsuranceClaim",
    ]
    submit = next(item for item in model.operations if item.name == "SubmitClaim")
    get_all = next(item for item in model.operations if item.name == "GetAllClaims")
    names_by_id = {item.id: item.name for item in model.entities}
    assert names_by_id[submit.request_entity_id] == "ClaimDto"
    assert names_by_id[submit.responses[0].entity_id] == "InsuranceClaim"
    assert names_by_id[get_all.responses[0].entity_id] == "InsuranceClaim"
    assert any(
        item.kind.value == "CONTAINS"
        and names_by_id.get(item.source_id) == "ClaimDto"
        and names_by_id.get(item.target_id) == "ClaimAddress"
        for item in model.relationships
    )
