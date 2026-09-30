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


def test_azure_function_mediator_flow_resolves_constants_models_and_handler_trail() -> None:
    repository = Path("fixtures/AzureFunctionsMediatorClaimsApi").resolve()
    model = extract_roslyn(
        repository / "AzureFunctionsMediatorClaimsApi.csproj",
        repository,
        "EU",
        "azure-functions-mediator-claims-api",
    )

    (operation,) = model.operations
    # Function name comes from a const chain; the HttpRequest trigger parameter is not a model.
    assert operation.name == "CreateClaim"
    assert (operation.method, operation.route) == (
        "POST",
        "/eu/cor01sh01/svc/claim/v3/service/claims",
    )
    assert operation.parameters == []

    names_by_id = {item.id: item.name for item in model.entities}
    # Request model comes from the command record; response from the handler's OkObjectResult.
    assert names_by_id[operation.request_entity_id] == "ClaimModel"
    assert names_by_id[operation.responses[0].entity_id] == "ClaimModel"
    # Nested models plus every model the handler flow touches (mapper endpoints included).
    assert set(names_by_id.values()) == {
        "ClaimModel",
        "ClaimIBO",
        "ItemIdInfoModel_v3",
        "LossEventModel_v3",
        "RestResponse",
        "SoapEnvelope",
    }
    ids = {name: entity_id for entity_id, name in names_by_id.items()}
    relations = {
        (item.kind.value, names_by_id.get(item.source_id, "op"), names_by_id[item.target_id])
        for item in model.relationships
        if item.kind.value in {"MAPS_TO", "REFERENCES"}
    }
    assert relations == {
        ("MAPS_TO", "ClaimModel", "SoapEnvelope"),
        ("MAPS_TO", "RestResponse", "ClaimModel"),
        ("MAPS_TO", "LossEventModel_v3", "ClaimIBO"),
        ("REFERENCES", "op", "ClaimIBO"),
        ("REFERENCES", "op", "LossEventModel_v3"),
        ("REFERENCES", "op", "RestResponse"),
        ("REFERENCES", "op", "SoapEnvelope"),
    }
    assert ids["ClaimIBO"] in {item.target_id for item in model.relationships}

    flow = next(
        item.observed_value
        for item in model.evidence
        if item.subject_id == operation.id and "flow" in (item.observed_value or {})
    )
    assert flow["command"].endswith("CreateClaimRequestv1")
    assert flow["handler"].endswith("CreateClaimRequestHandlerv1")
    assert {
        (m["from"].split(".")[-1], m["to"].split(".")[-1], m["via"]) for m in flow["mappings"]
    } == {
        ("ClaimModel", "SoapEnvelope", "GetMapper"),
        ("RestResponse", "ClaimModel", "GetMapper"),
        ("LossEventModel_v3", "ClaimIBO", "ClaimMapToIDIT"),
    }
    assert flow["backends"] == ["IAgoraClientv1", "ICMSClientv1", "IVLookupClient"]
    assert not [item for item in model.diagnostics if item.code == "FLOW001"]
    assert model.model_validate(model.model_dump()) == model
