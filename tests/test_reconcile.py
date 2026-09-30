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
    assert [item.name for item in first.entities] == [
        "AddressDto",
        "CreateQuoteRequest",
        "QuoteResponse",
        "VehicleDto",
    ]
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

    assert [item.name for item in result.entities] == [
        "AddressDto",
        "CreateQuoteRequest",
        "QuoteResponse",
        "VehicleDto",
    ]
    assert any("CreateQuoteRequest.applicantName" in item.message for item in result.diagnostics)


def test_openapi_guides_code_search_and_reconciles_relative_routes_and_renamed_models() -> None:
    from canonical_model_generator.discovery_agent.openapi import spec_schema_names

    repository = Path("fixtures/AzureFunctionsMediatorClaimsApi").resolve()
    spec = repository / "openapi/claims-api-fixture.yaml"
    project = repository / "AzureFunctionsMediatorClaimsApi.csproj"
    args = (repository, "EU", "azure-functions-mediator-claims-api")

    unguided = extract_roslyn(project, *args)
    guided = extract_roslyn(project, *args, hint_types=spec_schema_names(spec))
    # The spec names SearchModel_v3; no endpoint trace reaches it, but the spec makes it in scope.
    assert "SearchModel_v3" not in {item.name for item in unguided.entities}
    assert "SearchModel_v3" in {item.name for item in guided.entities}

    model = reconcile(guided, discover_openapi(spec, "EU", "azure-functions-mediator-claims-api"))

    routes = {(item.method, item.route) for item in model.operations}
    # Relative spec path merged into the code route; spec-only operations stay visible.
    assert ("POST", "/eu/cor01sh01/svc/claim/v3/service/claims") in routes
    assert ("POST", "/service/claims") not in routes
    assert ("GET", "/ping") in routes
    codes = {item.code for item in model.diagnostics}
    assert {"RECONCILE_ROUTE_PREFIX", "RECONCILE_SPEC_ONLY", "OPENAPI_EXTERNAL_REF"} <= codes
    spec_only = [item.message for item in model.diagnostics if item.code == "RECONCILE_SPEC_ONLY"]
    assert any("/ping" in message for message in spec_only)
    assert any("/service/claims/search" in message for message in spec_only)

    names = {item.name for item in model.entities}
    # The differently named spec request model was recognised as the code's ClaimModel.
    assert "COR01SH01_Claim_v3_RequestModel" not in names
    assert "ClaimModel" in names
    create = next(
        item for item in model.operations if item.method == "POST" and "claims" in item.route
    )
    assert not [item for item in model.diagnostics if item.code == "RECONCILE_REQUEST"]
    assert "RECONCILE_ENVELOPE" in codes
    assert create.request_entity_id is not None
