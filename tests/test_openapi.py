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


def test_error_responses_sharing_one_model_do_not_duplicate_relationship_ids(tmp_path) -> None:
    spec = tmp_path / "shared-errors.yaml"
    spec.write_text(
        """
openapi: 3.0.1
info: {title: t, version: '1'}
paths:
  /claims:
    post:
      operationId: post-claims
      responses:
        '200': {$ref: '#/components/responses/Ok'}
        '400': {$ref: '#/components/responses/Error400'}
        '500': {$ref: '#/components/responses/Error500'}
components:
  responses:
    Ok:
      description: ok
      content:
        application/json: {schema: {$ref: '#/components/schemas/ClaimResponse'}}
    Error400:
      description: bad request
      content:
        application/json: {schema: {$ref: '#/components/schemas/ErrorResponse'}}
    Error500:
      description: server error
      content:
        application/json: {schema: {$ref: '#/components/schemas/ErrorResponse'}}
  schemas:
    ClaimResponse: {type: object, properties: {id: {type: string}}}
    ErrorResponse: {type: object, properties: {message: {type: string}}}
""",
        encoding="utf-8",
    )

    model = discover_openapi(spec, "EU", "shared-errors")

    (operation,) = model.operations
    assert [item.status_code for item in operation.responses] == [200, 400, 500]
    returns = [item for item in model.relationships if item.kind.value == "RETURNS"]
    assert len(returns) == 2  # one per distinct response model
