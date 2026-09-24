import json
from pathlib import Path

import yaml

from canonical_model_generator.openapi import discover_openapi
from canonical_model_generator.reconcile import reconcile
from canonical_model_generator.roslyn import extract_roslyn
from canonical_model_generator.semantic_openapi import (
    AttributeSemantic,
    CapabilitySemantic,
    DomainSemantic,
    EndpointSemantic,
    EntitySemantic,
    EnumSemantic,
    ResponseSemantic,
    _generate_openapi,
    run_api_analyzer_agent,
)


class FakeAPIAnalyzerProvider:
    model_name = "fake-api-analyzer"

    def validate_connection(self) -> None:
        pass

    def analyze_endpoint(self, context: dict) -> EndpointSemantic:
        operation = context["operation"]
        follow_up = context.get("investigationRound") == 2
        confidence = 0.95 if follow_up else 0.60
        return EndpointSemantic(
            operation_id=operation["id"],
            domain=DomainSemantic(name="Policy", confidence=confidence),
            capability=CapabilitySemantic(name="Quote Management", confidence=confidence),
            summary=f"{operation['name']} insurance quote",
            description=f"Performs the discovered {operation['name']} quote operation.",
            business_purpose="Supports insurance quotation before policy issuance.",
            request_description="Quote information defined by the discovered request contract.",
            responses=[
                ResponseSemantic(
                    status_code=item["statusCode"],
                    description=f"HTTP {item['statusCode']} response for the quote operation.",
                )
                for item in operation["responses"]
            ],
            tags=["Quote Management"],
            confidence=confidence,
            requested_symbols=[] if follow_up else ["IQuoteService"],
            context_gaps=[] if follow_up else ["Service behavior is not in the initial context."],
        )

    def analyze_entity(self, context: dict) -> EntitySemantic:
        entity = context["entity"]
        return EntitySemantic(
            entity_id=entity["id"],
            domain=DomainSemantic(name="Policy", confidence=0.95),
            business_concept=entity["name"],
            summary=f"{entity['name']} quote model",
            description=f"Represents {entity['name']} in the quote contract.",
            attributes=[
                AttributeSemantic(
                    attribute_id=item["id"],
                    summary=f"{item['name']} value",
                    description=f"Represents the {item['name']} value.",
                    business_concept=item["originalName"],
                    business_meaning=f"Business meaning of {item['name']} in quote processing.",
                    confidence=0.95,
                )
                for item in entity["attributes"]
            ],
            confidence=0.95,
        )

    def analyze_enum(self, context: dict) -> EnumSemantic:
        enum = context["enum"]
        return EnumSemantic(
            enum_id=enum["id"],
            domain=DomainSemantic(name="Policy", confidence=0.95),
            business_concept=enum["name"],
            summary=f"{enum['name']} values",
            description=f"Defines the supported {enum['name']} values.",
            confidence=0.95,
        )


def test_api_analyzer_embeds_semantics_and_retrieves_low_confidence_context() -> None:
    repository = Path("fixtures/RegionalQuoteApi").resolve()
    roslyn = extract_roslyn(
        repository / "src/RegionalQuoteApi/RegionalQuoteApi.csproj",
        repository,
        "IN",
        "regional-quote-api-fixture",
    )
    openapi = discover_openapi(
        repository / "openapi/quote-api.yaml",
        "IN",
        "regional-quote-api-fixture",
        repository,
    )
    model = reconcile(roslyn, openapi)

    artifacts = run_api_analyzer_agent(model, repository, FakeAPIAnalyzerProvider())
    document = yaml.safe_load(artifacts["enriched-openapi.yaml"])
    report = json.loads(artifacts["enrichment-report.json"])

    create_quote = document["paths"]["/api/v1/quotes"]["post"]
    assert create_quote["x-domain"]["name"] == "Policy"
    assert create_quote["x-capability"]["name"] == "Quote Management"
    assert create_quote["x-business-purpose"]
    assert create_quote["x-source"]
    assert create_quote["x-confidence"]["domain"] == 0.95
    assert create_quote["requestBody"]["description"]
    assert create_quote["requestBody"]["x-source"]

    get_quote = document["paths"]["/api/v1/quotes/{quoteId}"]["get"]
    quote_id = get_quote["parameters"][0]
    assert quote_id["name"] == "quoteId"
    assert quote_id["description"] == "Discovered route parameter quoteId."
    assert quote_id["x-source"]
    response_model = get_quote["responses"]["200"]["x-response-model"]
    assert response_model["name"] == "QuoteResponse"
    assert response_model["schemaRef"] == "#/components/schemas/QuoteResponse"
    assert {item["name"] for item in response_model["attributes"]} == {
        "premium",
        "quoteId",
        "status",
        "validUntil",
    }
    assert all(item["description"] for item in response_model["attributes"])
    assert get_quote["responses"]["200"]["x-source"]

    assert set(document["components"]["schemas"]) == {
        "CoverageType",
        "CreateQuoteRequest",
        "QuoteResponse",
        "QuoteStatus",
    }
    assert "x-acord" not in artifacts["enriched-openapi.yaml"].decode("utf-8")

    assert report["status"] == "complete"
    assert report["domainsClassified"] == len(model.operations)
    assert report["capabilitiesClassified"] == len(model.operations)
    assert report["enumsEnriched"] == len(model.enums)
    assert all(item["retrievedFragmentCount"] > 0 for item in report["investigations"])
    assert not report["needsMoreContextTargets"]
    assert report["retrieval"]["provider"] == "chroma"
    assert report["retrieval"]["chunksIndexed"] > 0


def test_partial_openapi_keeps_parameter_and_response_model_details() -> None:
    repository = Path("fixtures/RegionalQuoteApi").resolve()
    model = reconcile(
        extract_roslyn(
            repository / "src/RegionalQuoteApi/RegionalQuoteApi.csproj",
            repository,
            "IN",
            "regional-quote-api-fixture",
        ),
        discover_openapi(
            repository / "openapi/quote-api.yaml",
            "IN",
            "regional-quote-api-fixture",
            repository,
        ),
    )

    document = _generate_openapi(model, [], [], [], "unavailable-provider")
    create_quote = document["paths"]["/api/v1/quotes"]["post"]
    get_quote = document["paths"]["/api/v1/quotes/{quoteId}"]["get"]

    assert create_quote["requestBody"]["description"] == (
        "Request body using the discovered CreateQuoteRequest contract."
    )
    assert create_quote["requestBody"]["x-source"]
    assert get_quote["parameters"][0]["description"]
    assert get_quote["parameters"][0]["x-source"]
    assert get_quote["responses"]["200"]["description"] == (
        "HTTP 200 response using the discovered QuoteResponse contract."
    )
    response_model = get_quote["responses"]["200"]["x-response-model"]
    assert response_model["name"] == "QuoteResponse"
    assert {item["name"] for item in response_model["attributes"]} == {
        "premium",
        "quoteId",
        "status",
        "validUntil",
    }
    assert all(item["description"] for item in response_model["attributes"])
    assert document["components"]["schemas"]["QuoteResponse"]["description"] == (
        "Discovered API contract model QuoteResponse."
    )
    assert document["components"]["schemas"]["QuoteResponse"]["properties"]["quoteId"][
        "description"
    ]


def test_api_analyzer_stops_before_item_loops_when_provider_validation_fails() -> None:
    class AuthenticationError(Exception):
        pass

    class FailingProvider(FakeAPIAnalyzerProvider):
        endpoint_calls = 0
        entity_calls = 0
        enum_calls = 0

        def validate_connection(self) -> None:
            raise AuthenticationError("bad credential sk-secret-value")

        def analyze_endpoint(self, context: dict) -> EndpointSemantic:
            self.endpoint_calls += 1
            return super().analyze_endpoint(context)

        def analyze_entity(self, context: dict) -> EntitySemantic:
            self.entity_calls += 1
            return super().analyze_entity(context)

        def analyze_enum(self, context: dict) -> EnumSemantic:
            self.enum_calls += 1
            return super().analyze_enum(context)

    repository = Path("fixtures/RegionalQuoteApi").resolve()
    roslyn = extract_roslyn(
        repository / "src/RegionalQuoteApi/RegionalQuoteApi.csproj",
        repository,
        "IN",
        "regional-quote-api-fixture",
    )
    model = reconcile(
        roslyn,
        discover_openapi(
            repository / "openapi/quote-api.yaml",
            "IN",
            "regional-quote-api-fixture",
            repository,
        ),
    )
    provider = FailingProvider()

    artifacts = run_api_analyzer_agent(model, repository, provider)
    report = json.loads(artifacts["enrichment-report.json"])

    assert provider.endpoint_calls == 0
    assert provider.entity_calls == 0
    assert provider.enum_calls == 0
    assert report["providerStatus"] == "failed"
    assert report["endpointsEnriched"] == 0
    assert len(report["validationErrors"]) == 1
    assert "authentication failed" in report["validationErrors"][0].lower()
    assert "sk-secret-value" not in artifacts["enrichment-report.json"].decode("utf-8")


def test_repository_domain_and_single_operation_tag() -> None:
    repository = Path("fixtures/RegionalQuoteApi").resolve()
    model = reconcile(
        extract_roslyn(
            repository / "src/RegionalQuoteApi/RegionalQuoteApi.csproj",
            repository,
            "IN",
            "regional-quote-api-fixture",
        ),
        discover_openapi(
            repository / "openapi/quote-api.yaml",
            "IN",
            "regional-quote-api-fixture",
            repository,
        ),
    )
    operation = model.operations[0]
    semantic = EndpointSemantic(
        operation_id=operation.id,
        domain=DomainSemantic(name="Management", confidence=0.96),
        capability=CapabilitySemantic(name="Create", confidence=0.96),
        summary="Create managed resource",
        description="Creates the managed resource represented by the discovered contract.",
        business_purpose="Supports the repository's management workflow.",
        request_description="Uses the discovered request model.",
        responses=[
            ResponseSemantic(status_code=item.status_code, description="Discovered response.")
            for item in operation.responses
        ],
        tags=["Management", "Ignored extra tag"],
        confidence=0.96,
    )

    document = _generate_openapi(model, [semantic], [], [], "fake-api-analyzer")
    operation_document = document["paths"][operation.route][operation.method.lower()]

    assert operation_document["tags"] == ["Management"]
    assert document["tags"] == [
        {
            "name": "Management",
            "description": "Repository-derived Management domain endpoints.",
        }
    ]
