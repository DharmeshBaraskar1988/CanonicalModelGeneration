import json
from pathlib import Path

import pytest
import yaml

from canonical_model_generator.api_analyzer.contracts import CodeClaim, CodeSemantic
from canonical_model_generator.api_analyzer.inspect import inspect_retrieved_target
from canonical_model_generator.api_analyzer.token_budget import TokenBudgetExceeded
from canonical_model_generator.api_analyzer.workflow import (
    AttributeSemantic,
    CapabilitySemantic,
    DomainSemantic,
    EndpointSemantic,
    EntitySemantic,
    EnumSemantic,
    ResponseSemantic,
    _generate_openapi,
    _reconcile_endpoint_responses,
    load_discovery_artifact,
    run_api_analyzer_agent,
)
from canonical_model_generator.discovery_agent.openapi import discover_openapi
from canonical_model_generator.discovery_agent.reconcile import reconcile
from canonical_model_generator.discovery_agent.roslyn import extract_roslyn
from canonical_model_generator.repository_rag.index import ChromaRepositoryIndex


def test_api_analyzer_boundary_requires_a_discovery_artifact() -> None:
    with pytest.raises(TypeError, match="serialized Discovery Agent artifact"):
        load_discovery_artifact(object())  # type: ignore[arg-type]


def test_api_analyzer_requires_repository_rag():
    model = discover_openapi(
        Path("fixtures/RegionalQuoteApi/openapi/quote-api.yaml"), "IN", "quote"
    )
    with pytest.raises(ValueError, match="RAG is mandatory"):
        run_api_analyzer_agent(
            model.model_dump_json(by_alias=True), None, FakeAPIAnalyzerProvider()
        )


def test_endpoint_response_reconciliation_retains_discovery_inventory_and_gap() -> None:
    context = {"operation": {"responses": [{"statusCode": 200}]}}
    result = EndpointSemantic(
        operation_id="operation-delete",
        domain=DomainSemantic(name="Assets", confidence=0.9),
        capability=CapabilitySemantic(name="Delete", confidence=0.9),
        summary="Delete asset",
        description="Deletes an asset.",
        business_purpose="Removes an asset record.",
        request_description="Identifies the asset.",
        responses=[
            ResponseSemantic(status_code=204, description="Asset deleted."),
            ResponseSemantic(status_code=404, description="Asset not found."),
        ],
        confidence=0.9,
    )

    reconciled = _reconcile_endpoint_responses(context, result)

    assert [item.status_code for item in reconciled.responses] == [200]
    assert reconciled.responses[0].description == "HTTP 200 response discovered by Phase 1."
    assert "missing [200]" in reconciled.context_gaps[0]
    assert "additional [204, 404]" in reconciled.context_gaps[0]


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

    def analyze_code(self, context: dict) -> CodeSemantic:
        usage = next(
            (
                item
                for item in context["sourceSnippets"]
                if "InMemoryQuoteService.Create" in item["symbol"]
                and "Premium = decimal.Round" in item["text"]
            ),
            context["sourceSnippets"][0],
        )
        return CodeSemantic(
            summary="Retrieved code for the selected target",
            role="Source-backed code explanation",
            claims=[
                CodeClaim(
                    text="The method assigns a rounded premium from request coverage amount.",
                    classification="observed",
                    confidence=0.95,
                    evidence_chunk_ids=[usage["chunkId"]],
                )
            ],
        )


def test_api_analyzer_embeds_semantics_and_retrieves_low_confidence_context(
    fake_embedder, tmp_path
) -> None:
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

    index = ChromaRepositoryIndex(tmp_path / "saved-rag", fake_embedder)
    try:
        index.ingest(repository, model)
    finally:
        index.close()

    artifacts = run_api_analyzer_agent(
        model.model_dump_json(by_alias=True).encode(),
        repository,
        FakeAPIAnalyzerProvider(),
        embedder=fake_embedder,
        rag_store_path=tmp_path / "saved-rag",
    )
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
        "AddressDto",
        "CoverageType",
        "CreateQuoteRequest",
        "QuoteResponse",
        "QuoteStatus",
        "VehicleDto",
    }
    assert "x-acord" not in artifacts["enriched-openapi.yaml"].decode("utf-8")

    assert report["status"] == "complete"
    assert report["domainsClassified"] == len(model.operations)
    assert report["capabilitiesClassified"] == len(model.operations)
    assert report["enumsEnriched"] == len(model.enums)
    assert all(item["retrievedFragmentCount"] > 0 for item in report["investigations"])
    assert not report["needsMoreContextTargets"]
    assert report["retrieval"]["provider"] == "chroma"
    assert report["retrieval"]["storage"] == "persistent-local"
    assert report["retrieval"]["chunksIndexed"] > 0
    assert set(artifacts) == {
        "enriched-openapi.yaml",
        "semantic-metadata.json",
        "evidence-map.json",
        "enrichment-report.json",
    }

    index = ChromaRepositoryIndex(tmp_path / "saved-rag", fake_embedder)
    try:
        entity = next(item for item in model.entities if item.original_name == "QuoteResponse")
        field = next(item for item in entity.attributes if item.original_name == "Premium")
        focused = inspect_retrieved_target(
            model.model_dump_json(by_alias=True), index, field.id, FakeAPIAnalyzerProvider()
        )
        assert focused["status"] == "inferred"
        assert focused["semantic"]["owningEntity"] == "QuoteResponse"
        assert focused["semantic"]["businessMeaning"]
        assert focused["citations"][0]["retrievalReason"] == "exact-lineage"
        assert focused["citations"][0]["path"].endswith("QuoteResponse.cs")
        assert focused["citations"][0]["startLine"] == 9
        assert focused["codeAnalysis"]["claims"][0]["classification"] == "observed"
        usage_id = focused["codeAnalysis"]["claims"][0]["evidenceChunkIds"][0]
        usage = next(item for item in focused["citations"] if item["chunkId"] == usage_id)
        assert "InMemoryQuoteService.Create" in usage["symbol"]
        assert usage["startLine"] == 10

        class InvalidCitationProvider(FakeAPIAnalyzerProvider):
            def analyze_code(self, context: dict) -> CodeSemantic:
                result = super().analyze_code(context)
                return result.model_copy(
                    update={
                        "claims": [
                            result.claims[0].model_copy(
                                update={"evidence_chunk_ids": ["not-retrieved"]}
                            )
                        ]
                    }
                )

        with pytest.raises(RuntimeError, match="citation validity|target structure"):
            inspect_retrieved_target(
                model.model_dump_json(by_alias=True), index, field.id, InvalidCitationProvider()
            )

        class NoCodeClaimsProvider(FakeAPIAnalyzerProvider):
            def analyze_code(self, context: dict) -> CodeSemantic:
                return CodeSemantic(
                    summary="Meaning unresolved", role="Unknown", gaps=["Usage unclear"]
                )

        partial = inspect_retrieved_target(
            model.model_dump_json(by_alias=True), index, field.id, NoCodeClaimsProvider()
        )
        assert partial["status"] == "partial"
        assert partial["codeEvidenceStatus"] == "insufficient"
        assert any("No source-grounded" in gap for gap in partial["gaps"])
        with pytest.raises(ValueError, match="does not match"):
            inspect_retrieved_target(
                model.model_copy(update={"system": "other"}).model_dump_json(by_alias=True),
                index,
                field.id,
                FakeAPIAnalyzerProvider(),
            )
    finally:
        index.close()


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
    request_model = create_quote["requestBody"]["x-request-model"]
    assert request_model["name"] == "CreateQuoteRequest"
    assert request_model["schemaRef"] == "#/components/schemas/CreateQuoteRequest"
    assert {item["name"] for item in request_model["attributes"]} == {
        "address",
        "applicantAge",
        "applicantName",
        "coverageAmount",
        "coverageType",
        "vehicles",
    }
    assert all(item["description"] for item in request_model["attributes"])
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


def test_reconciliation_restores_openapi_request_and_failure_responses() -> None:
    repository = Path("fixtures/RegionalQuoteApi").resolve()
    roslyn = extract_roslyn(
        repository / "src/RegionalQuoteApi/RegionalQuoteApi.csproj",
        repository,
        "IN",
        "regional-quote-api-fixture",
    )
    # Simulate a repository extractor that found routes but did not establish contract details.
    for operation in roslyn.operations:
        operation.parameters = []
        operation.request_entity_id = None
        operation.responses = []
    model = reconcile(
        roslyn,
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
    assert create_quote["requestBody"]["content"]["application/json"]["schema"] == {
        "$ref": "#/components/schemas/CreateQuoteRequest"
    }
    assert create_quote["responses"]["400"]["description"] == "Invalid request"
    assert get_quote["parameters"][0]["name"] == "quoteId"
    assert get_quote["responses"]["404"]["description"] == "Quote not found"


def test_enriched_openapi_keeps_empty_request_and_response_body_structure() -> None:
    repository = Path("fixtures/RegionalQuoteApi").resolve()
    model = extract_roslyn(
        repository / "src/RegionalQuoteApi/RegionalQuoteApi.csproj",
        repository,
        "IN",
        "regional-quote-api-fixture",
    )
    operation = model.operations[0]
    operation.parameters = []
    operation.request_entity_id = None
    operation.responses = []

    document = yaml.safe_load(
        yaml.safe_dump(
            _generate_openapi(model, [], [], [], "unavailable-provider"), sort_keys=False
        )
    )
    rendered = document["paths"][operation.route][operation.method.lower()]

    assert list(rendered).index("requestBody") < list(rendered).index("responses")
    assert rendered["requestBody"] == {
        "required": False,
        "description": "No request body model was discovered.",
        "content": {"application/json": {"schema": {}}},
        "x-source": rendered["requestBody"]["x-source"],
    }
    assert rendered["responses"]["default"] == {
        "description": "No response body model was discovered.",
        "content": {"application/json": {"schema": {}}},
        "x-source": rendered["responses"]["default"]["x-source"],
    }


def test_enriched_openapi_keeps_empty_body_for_response_without_model() -> None:
    repository = Path("fixtures/RegionalQuoteApi").resolve()
    model = extract_roslyn(
        repository / "src/RegionalQuoteApi/RegionalQuoteApi.csproj",
        repository,
        "IN",
        "regional-quote-api-fixture",
    )
    operation = model.operations[0]
    operation.responses[0].entity_id = None
    operation.responses[0].type = None

    document = _generate_openapi(model, [], [], [], "unavailable-provider")
    rendered_response = document["paths"][operation.route][operation.method.lower()]["responses"][
        str(operation.responses[0].status_code)
    ]

    assert rendered_response["content"] == {"application/json": {"schema": {}}}


def test_enriched_openapi_always_has_server_and_components() -> None:
    repository = Path("fixtures/RegionalQuoteApi").resolve()
    model = extract_roslyn(
        repository / "src/RegionalQuoteApi/RegionalQuoteApi.csproj",
        repository,
        "IN",
        "regional-quote-api-fixture",
    )
    model.entities = []
    model.enums = []

    document = _generate_openapi(model, [], [], [], "unavailable-provider")

    assert document["servers"] == [
        {
            "url": "/",
            "description": "Relative API root; no deployment server was discovered.",
        }
    ]
    assert document["components"] == {"schemas": {}}


def test_api_analyzer_stops_before_item_loops_when_provider_validation_fails(
    fake_embedder, tmp_path
) -> None:
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

    index = ChromaRepositoryIndex(tmp_path / "saved-rag", fake_embedder)
    try:
        index.ingest(repository, model)
    finally:
        index.close()

    artifacts = run_api_analyzer_agent(
        model.model_dump_json(by_alias=True).encode(),
        repository,
        provider,
        rag_store_path=tmp_path / "saved-rag",
        embedder=fake_embedder,
    )
    report = json.loads(artifacts["enrichment-report.json"])

    assert provider.endpoint_calls == 0
    assert provider.entity_calls == 0
    assert provider.enum_calls == 0
    assert report["providerStatus"] == "failed"
    assert report["endpointsEnriched"] == 0
    assert len(report["validationErrors"]) == 1
    assert "authentication failed" in report["validationErrors"][0].lower()
    assert "sk-secret-value" not in artifacts["enrichment-report.json"].decode("utf-8")


def test_api_analyzer_continuation_reuses_completed_results(fake_embedder, tmp_path) -> None:
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

    class TrackingProvider(FakeAPIAnalyzerProvider):
        def __init__(self, endpoint_limit: int | None = None) -> None:
            self.endpoint_limit = endpoint_limit
            self.endpoint_ids: list[str] = []

        def analyze_endpoint(self, context: dict) -> EndpointSemantic:
            if self.endpoint_limit is not None and len(self.endpoint_ids) >= self.endpoint_limit:
                raise TokenBudgetExceeded(
                    "Projected run usage exceeds the run limit; no further paid calls will be made."
                )
            self.endpoint_ids.append(context["operation"]["id"])
            result = super().analyze_endpoint(context)
            return result.model_copy(
                update={
                    "domain": result.domain.model_copy(update={"confidence": 0.95}),
                    "capability": result.capability.model_copy(update={"confidence": 0.95}),
                    "confidence": 0.95,
                    "requested_symbols": [],
                }
            )

    index = ChromaRepositoryIndex(tmp_path / "saved-rag", fake_embedder)
    try:
        index.ingest(repository, model)
    finally:
        index.close()

    first_provider = TrackingProvider(endpoint_limit=1)
    partial = run_api_analyzer_agent(
        model.model_dump_json(by_alias=True),
        repository,
        first_provider,
        rag_store_path=tmp_path / "saved-rag",
        embedder=fake_embedder,
    )
    partial_report = json.loads(partial["enrichment-report.json"])
    assert partial_report["stop_reason"] == "budget_exhausted"
    assert partial_report["endpointsEnriched"] == 1

    continuation_provider = TrackingProvider()
    completed = run_api_analyzer_agent(
        model.model_dump_json(by_alias=True),
        repository,
        continuation_provider,
        rag_store_path=tmp_path / "saved-rag",
        embedder=fake_embedder,
        resume_artifacts=partial,
    )
    completed_report = json.loads(completed["enrichment-report.json"])

    assert completed_report["endpointsEnriched"] == len(model.operations)
    assert first_provider.endpoint_ids[0] not in continuation_provider.endpoint_ids
    assert set(continuation_provider.endpoint_ids) == {item.id for item in model.operations[1:]}
    metadata = json.loads(completed["semantic-metadata.json"])
    assert len(metadata["endpoints"]) == len(model.operations)


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
