# Project Status

Last updated: 2026-09-24  
Current milestone: Phase 2 API Analyzer Agent  
Overall state: Phase 1 complete; Phase 2 in progress

## Completed

- Reviewed the original canonical-model architecture conversation.
- Agreed to implement deterministic discovery before classification or canonical generation.
- Defined the milestone-based Discovery MVP implementation plan.
- Added project-memory and status-update instructions in `AGENTS.md`.
- Added the synthetic `IN` regional Quote API fixture and its OpenAPI 3.0.3 document.
- Recorded the fixture's solution/project paths, region, system, target framework, endpoints, exclusions, and data classification.
- Completed M0.1-M0.3 / NS-01.
- Added an intake-only Streamlit page for repository ZIP and OpenAPI uploads.
- Added bounded, in-memory ZIP inspection, path-traversal protection, input hashes, readiness checks, and deterministic manifest download.
- Created the project-local `.venv` and installed the pinned application and test dependencies.
- Completed M0.4-M0.5 with the Python package, `net8.0` Roslyn-sidecar console scaffold, xUnit project, root solution, and pinned baseline tooling.
- Completed and accepted M0 - Inputs and project baseline.
- Completed M1.1-M1.10: DiscoveryModel v1, stable IDs, fixtures, cross-reference validation, and JSON Schema.
- Completed M2.1-M2.9: Roslyn/MSBuild extraction, DTO/enum/validation discovery, lineage, and DiscoveryModel mapping.
- Completed M3.1-M3.8: OpenAPI 3 JSON/YAML parsing, local references, constraints, composition diagnostics, and pointer lineage.
- Completed M4.1-M4.8: deterministic normalization, evidence merge, conflict diagnostics, and stable ordering.
- Completed M5.1-M5.11 and M6.1-M6.7: sequential LangGraph orchestration, CLI, structured events, validation, and six atomic artifacts.
- Completed M7.1-M7.6 and accepted the Discovery MVP.
- Updated the Streamlit UI with the seven-phase platform roadmap, Phase 1 completion details, and Phase 2-7 status.
- Added gated Phase 1 results and Phase 2 normalization tabs; the accepted Phase 1 result unlocks Phase 2 planning while the unbuilt service remains explicitly identified.
- Converted the first tab into a Discovery Agent workspace with a visual extraction tree, real M7 artifact previews, six JSON downloads, and a combined ZIP download.
- Replaced fixture-backed UI results with repository-specific trusted execution. The Discovery Agent now displays only five derived artifacts after the uploaded repository completes successfully.
- Made the operator-facing relationship graph readable by resolving endpoint and evidence IDs into names, relationship sentences, source kinds, and source locations.
- Added repository-only Discovery Agent execution: Roslyn generates the five artifacts when OpenAPI is absent, while available OpenAPI evidence still enriches and reconciles the result.
- Added deterministic Roslyn de-duplication for repeated sources, model elements, evidence, lineage, relationships, validations, and diagnostics from larger repositories.
- Added controller-aware Web API project selection for multi-project ZIPs and prevented empty discovery results from being presented as successful artifacts.
- Extended Roslyn discovery to conventional ASP.NET Core MVC actions, inferred conventional routes, source-defined request models, and project-local nested DTOs without fixture namespace assumptions.
- Replaced single-project upload analysis with repository exploration across every non-test project that owns controllers, followed by deterministic repository-model aggregation and optional OpenAPI reconciliation.
- Independently inspected the provided eShopOnWeb repository and added Minimal API, attributed endpoint-base, and syntax-degraded endpoint discovery for projects with unresolved dependencies.
- Replaced operation, evidence, parameter, request, and response IDs in the operator-facing API Catalog with readable names, HTTP status labels, and source locations; stable IDs remain in the internal DiscoveryModel.
- Added MVC `View(model)` response discovery and response-model trees so the API Catalog shows ViewModels, nested model fields, collection relations, inheritance, and supporting source locations.
- Converted all five operator-facing artifacts to readable presentation models with names and source locations instead of internal entity, attribute, validation, evidence, lineage, source, subject, or reference IDs.
- Started Phase 2 with a versioned multi-source normalization contract, deterministic identifier/route/type rules, preserved constraints and lineage, an exported JSON Schema, and a Streamlit normalize/preview/download path for the current Phase 1 result.
- Replaced the unsupported Phase 2 `normalize` Material icon with the valid `sync_alt` icon in both the tab and normalization button.
- Superseded the Phase 2 normalization direction with an evidence-grounded Semantic OpenAPI Agent; the earlier normalization module remains inactive and available for a future release if needed.
- Added bounded source-context retrieval with repository-boundary enforcement, likely-secret redaction, explicit truncation reporting, and untrusted-source prompting.
- Added an OpenAI Responses API adapter with Pydantic Structured Outputs for endpoint analysis and entity-level attribute batching.
- Added a Phase 2 LangGraph that builds contexts, enriches endpoints, enriches entities and attributes, renders OpenAPI, validates coverage, and preserves partial-run gaps.
- Added four Phase 2 outputs: `enriched-openapi.yaml`, `semantic-metadata.json`, `evidence-map.json`, and `enrichment-report.json`.
- Replaced the normalization UI with a gated Semantic OpenAPI Agent that requires explicit source-sharing acknowledgement and provides individual previews/downloads plus a ZIP bundle.
- Renamed Phase 2 to the API Analyzer Agent and added mandatory, controlled insurance domain/capability classification for every enriched endpoint.
- Added entity, attribute, and enum business concepts and descriptions to the self-contained enriched OpenAPI contract.
- Standardized Phase 2 semantic OpenAPI extensions as `x-domain`, `x-capability`, `x-business-concept`, `x-business-purpose`, `x-source`, and `x-confidence`; Phase 2 emits no ACORD conclusions.
- Added repository-wide structural signals and one bounded low-confidence investigation round that retrieves matching service/handler/repository/client code and re-analyzes the endpoint.
- Added confidence bands: at least 0.90 is an auto-accept candidate, 0.70-0.89 requires review, and below 0.70 remains a needs-more-context gap after bounded investigation.
- Added strict checks that LLM output preserves operation/entity/attribute/enum IDs, uses the controlled taxonomy, describes exactly the discovered response codes, and retains Phase 1 lineage.
- Added an ignored local `.env` configuration for `OPENAI_API_KEY` and `OPENAI_MODEL`; Streamlit loads it automatically without copying the key into generated artifacts.
- Added a single OpenAI credential/model preflight before semantic item loops, fail-fast handling for permanent provider errors, secret-safe error text, and bounded SDK retries for transient failures.
- Added live Phase 2 progress in Streamlit for context construction, provider validation, every endpoint/entity/enum analysis, bounded code retrieval, and artifact validation; the result now separates discovered coverage from enriched coverage and surfaces the first actionable provider error.
- Added a local, ephemeral Chroma repository index that ingests bounded redacted code/configuration chunks and retrieves relevant evidence for each endpoint, entity, and enum before semantic analysis.
- Changed Phase 2 classification so the controlled insurance taxonomy is preferred when supported, while technical APIs can use repository-derived controller/module domains and action capabilities (for example `ManageController` → `Management`); `UNCLASSIFIED` is now a last resort.
- Limited each OpenAPI operation to one domain tag and added deterministic Phase 1 name-based CLR-type resolution before emitting `x-unresolved-clr-type`.
- Added Chroma file/chunk metrics and live ingestion/retrieval progress to the Phase 2 Streamlit UI.
- Amended Phase 1 entity scope so only user-authored `*ViewModel` types reachable from API endpoints are retained; DTOs, domain models, generated types under `bin`/`obj` or generated-file suffixes, and unrelated ViewModels are removed deterministically.
- Preserved direct endpoint `ACCEPTS`/`RETURNS` relationships plus nested ViewModel `CONTAINS` and inheritance relationships, and pruned dangling types, enums, validations, evidence, lineage, sources, and references from the final DiscoveryModel.
- Updated Discovery and Phase 2 UI wording to identify entities as endpoint ViewModels and regenerated `.tmp/discovery-output` under the amended scope.
- Expanded the accepted entity boundary to endpoint-reachable concrete `*ViewModel`, `*Request`, and `*Response` classes while excluding `Base*` infrastructure models, DTO entities, generated types, domain types, and unrelated models.
- Added bounded request-model trees to the API Catalog so request and response structures are both visible there and in the Data Model.
- Completed P2.4a: enriched OpenAPI now retains deterministic details and source lineage for route/query/header parameters and request bodies, explicitly names response contract models, and supplies structural fallback descriptions for response ViewModels and their fields when semantic enrichment is partial or unavailable.
- Completed P2.4b: each response `x-response-model` now includes its component reference, model description, and direct attributes with requiredness, descriptions, and schemas; corrected the partial-run entity-description fallback so every discovered response ViewModel is described in `components.schemas`.

## In progress

- Configure an approved OpenAI API key and complete a live API Analyzer accuracy review against an approved real repository.
- Keep service call paths, persistence, integrations, security, and other unavailable code context visible as Phase 1 gaps rather than LLM facts.

## Verification evidence

- Before the M7.7 scope amendment, a focused offline Phase 2 run enriched 2 fixture endpoints, 4 broad contract entities, and 14 attributes. Those DTO entity counts are historical and are no longer the accepted Phase 1 boundary.
- Ruff accepted `streamlit_app.py` and `semantic_openapi.py`; OpenAI Python 3.19.1 is installed in the project environment.
- A focused Streamlit AppTest validated all 12 Material icon shortcodes and loaded the updated UI with zero exceptions; the running app health endpoint returned `ok` on port 8501.
- A live provider preflight loaded the configured `.env` value and OpenAI returned HTTP 401 `invalid_api_key`; no repository semantics were sent or generated, and live semantic quality remains unverified until the key is replaced.
- The focused API Analyzer behavior test passed against the Quote API fixture, including one low-confidence service-code retrieval round, domain/capability classification, entity/attribute/enum enrichment, fixed extensions, source traceability, confidence, and generated OpenAPI validation.
- Ruff accepted the updated analyzer, Streamlit page, and focused Phase 2 test; Streamlit AppTest loaded the renamed API Analyzer UI with 13 valid icons and zero exceptions.
- The .NET API-agent minimum report validator accepted the generated `enrichment-report.json` with valid repository hashes, source-line citations, endpoint inventory accounting, semantic claims, and no unresolved fixture gaps.
- The ignored `.env` file loads successfully through `python-dotenv`; its API key is currently blank, the Streamlit UI still loads with zero exceptions, and the running app health endpoint returns `ok`.
- The installed Streamlit 1.62.0 validator accepted all 10 unique Material icon shortcodes in `streamlit_app.py`, including `sync_alt`; the running app health endpoint returned `ok` on port 8501.
- Planning files created and cross-referenced.
- `dotnet restore fixtures/RegionalQuoteApi/RegionalQuoteApi.sln` succeeded with SDK 10.0.401.
- `dotnet build fixtures/RegionalQuoteApi/RegionalQuoteApi.sln --no-restore` succeeded with 0 warnings and 0 errors.
- PyYAML parsed `fixtures/RegionalQuoteApi/openapi/quote-api.yaml` successfully; the document contains 2 paths and 5 component schemas.
- `python -m pytest` passed 5 intake tests in 0.15 seconds.
- Streamlit `AppTest` loaded `streamlit_app.py` without exceptions and confirmed the page title.
- `.venv` uses Python 3.14.7 with Streamlit 1.62.0; the isolated test run passed all 5 tests in 0.10 seconds.
- Streamlit started on port 8501 and `http://localhost:8501/_stcore/health` returned HTTP 200 with `ok`.
- M0 Python gate: Ruff lint and format checks passed; pytest passed 5 tests in 0.05 seconds.
- M0 .NET gate: restore and format checks passed; the solution built with 0 warnings and 0 errors; xUnit passed 1 test in 10 ms.
- The `net8.0` Quote API ran locally through the documented major-version roll-forward; POST returned 201 and the subsequent GET returned 200 with the created quote.
- M1 gate: Ruff lint/format passed and pytest passed 9 tests; the valid fixture and exported schema were inspected.
- M2 gate: .NET format/build/xUnit passed; Ruff passed; pytest passed 10 tests including the real Roslyn fixture extraction.
- M3 gate: Ruff lint/format passed and pytest passed 11 tests including the OpenAPI fixture.
- M4 gate: Ruff lint/format passed and pytest passed 13 tests including agreement, conflicts, and byte stability.
- M5-M6 gate: Ruff lint/format passed and pytest passed 15 tests; a real CLI run completed all six nodes and generated six validated artifacts.
- M7 final gate: Ruff lint/format and .NET format passed; .NET built with 0 warnings/errors; xUnit passed 1 test; pytest passed 16 tests.
- Two complete CLI runs produced byte-identical hashes for all six artifacts and the same deterministic run ID.
- The fixture CLI regenerated `.tmp/discovery-output` successfully with readable relationship names and Roslyn/OpenAPI source locations.
- The fixture CLI regenerated `.tmp/discovery-output/api-catalog.json` successfully with two named operations, resolved request/response models, HTTP status names, and Roslyn/OpenAPI source locations.
- The Roslyn sidecar build succeeded with 0 warnings/errors after adding ViewModel response discovery. A targeted run against eShopOnWeb resolved `MyOrders` to `OrderViewModel`, `Detail` to `OrderDetailViewModel`, the `OrderItemViewModel` collection, and `OrderViewModel` inheritance.
- The fixture CLI regenerated the API Catalog successfully with `responseModelTree` details for `QuoteResponse`.
- The fixture CLI regenerated `.tmp/discovery-output`, `.tmp/m7-run-1`, and `.tmp/m7-run-2`; a recursive scan of all 15 operator artifact files found no internal ID keys or stable-ID values.
- A focused Phase 2 run normalized the Quote fixture into 1 source, 2 operations, 4 entities, 2 enums, and 17 relationships; two runs produced byte-identical JSON.
- The updated Roslyn sidecar built successfully with 0 warnings and 0 errors after adding conventional MVC support.
- Before M7.7, the expanded sidecar's broad-type check found 8 PublicApi operations plus 25 Web controller operations. Its old entity/relationship counts are superseded by the endpoint-ViewModel boundary.
- The pre-M7.7 golden coverage of 4 entities, 2 enums, 17 relationships, and 26 validations is superseded. Current Quote golden coverage is 2 operations, 0 qualifying ViewModels, 0 enums, 0 relationships, and 0 validations.
- The earlier DTO-focused manual review is historical; accepted entity review now covers only endpoint-reachable ViewModels and their nested/base relationships.
- One expected reconciliation warning remains visible: Roslyn observes `QuoteStatus` as a named enum while OpenAPI defines the response status inline.
- The roadmap UI change has not been retested yet under the agreed milestone-only test policy.
- The phase-tab and continuation-gate UI change has not been retested under the agreed milestone-only test policy.
- The Discovery Agent tree, preview, and download UI has not been retested under the agreed milestone-only test policy.
- Trusted repository execution and the simplified five-artifact UI have not been retested under the agreed milestone-only test policy.
- Human-readable relationship artifact generation has not been retested under the agreed milestone-only test policy.
- Repository-only Roslyn fallback has not been retested under the agreed milestone-only test policy.
- Large-repository duplicate-ID handling has not been retested against the user's repository under the agreed milestone-only test policy.
- Multi-project Web API selection and empty-result detection have not been retested against the user's repository under the agreed milestone-only test policy.
- Conventional MVC discovery has not been retested against the user's eShopOnWeb upload under the agreed milestone-only test policy.
- Multi-project repository aggregation has not been retested against the user's eShopOnWeb upload under the agreed milestone-only test policy.
- The exact eShopOnWeb source inventory contains 8 PublicApi operations, 25 Web controller operations, and 12 Razor Page routes; deep mapping, persistence, integration, security, and Razor Page modules remain open.
- The exact eShopOnWeb checkout is not restored: semantic loading reports unresolved dependency errors, so endpoint coverage uses syntax fallback and deeper semantic coverage remains partial.
- The readable API Catalog change has not been run through the full test suite under the agreed milestone-only test policy.
- ViewModel response discovery and response-tree rendering have not been run through the full test suite under the agreed milestone-only test policy.
- The five-artifact readable presentation conversion has not been run through the full test suite under the agreed milestone-only test policy.
- The Phase 2 semantic OpenAPI workflow has not been run through the full milestone test suite under the agreed milestone-only test policy.
- Focused Phase 2 tests passed (3 tests), including Chroma-backed bounded enrichment, fail-fast authentication behavior with zero endpoint/entity/enum calls after preflight failure, repository-derived domain/capability tags, and Phase 1 CLR-type resolution.
- Ruff lint and format checks passed for the analyzer, Streamlit page, and focused tests; Streamlit AppTest loaded the updated page without exceptions.
- ChromaDB 1.5.9 installed successfully in the project environment; `pip check` reported no broken requirements. The Quote fixture indexed 9 chunks across 8 repository files and retrieved its controller and service sources locally.
- Fifteen focused model, Roslyn, reconciliation, graph/artifact, Phase 2, and end-to-end golden tests passed after the ViewModel-only scope amendment.
- A targeted run against the provided eShopOnWeb Web project retained 11 endpoint-reachable ViewModels across 25 operations, excluded DTO/domain/generated types, preserved direct endpoint response links, and linked `OrderDetailViewModel` to nested `OrderItemViewModel`.
- Under the intentional ViewModel-only scope, the Quote fixture retains 2 operations but 0 entities, enums, validations, or relationships because its contract models are DTO/request/response classes rather than `*ViewModel` classes; the deterministic golden output was updated accordingly.
- After M7.8, the regenerated Quote fixture contains 2 operations, 2 concrete endpoint contracts, 2 referenced enums, 13 relationships, and 13 validations; the Data Model contains `CreateQuoteRequest` and `QuoteResponse`, and the API Catalog includes request and response trees.
- The full 22-test Python suite passed after updating Roslyn, reconciliation, golden-artifact, and Phase 2 expectations for the expanded contract boundary. Ruff lint and format checks passed for the changed Python files; pytest reported only the existing Chroma `asyncio.iscoroutinefunction` deprecation warning.
- The full Python suite passed after the enriched-OpenAPI parameter/response-detail fix. Focused assertions verified a described and sourced request body, a described and sourced route parameter, an explicit `x-response-model`, and fallback descriptions for `QuoteResponse` and `QuoteResponse.quoteId`; Ruff lint and format checks passed for `src`, `tests`, and `streamlit_app.py`.
- The full 23-test Python suite passed after expanding response-model details. A targeted eShopOnWeb render verified that `ExternalLoginsViewModel` exposes `currentLogins`, `otherLogins`, `showRemoveButton`, and `statusMessage` with descriptions under `x-response-model.attributes`, while the standard response schema still references `components.schemas.ExternalLoginsViewModel`; Ruff lint and format checks passed.

## Blockers and required inputs

- No blocker remains for the accepted fixture-based Discovery MVP.
- Production-readiness still requires a run against an approved real regional repository.
- The currently configured OpenAI key is rejected with HTTP 401 `invalid_api_key`. Phase 2 acceptance requires replacing it with an active approved API key, source-sharing approval, and a live run against an approved real repository.

## Current scope

Platform Phase 1 is complete with an endpoint-reachable concrete ViewModel/request/response entity boundary. Phase 2 is the API Analyzer Agent: it uses that accepted DiscoveryModel as structural truth, retrieves bounded repository evidence, classifies domain/capability, and generates a self-contained enriched OpenAPI plus provenance and coverage artifacts with an OpenAI model.

## Deferred scope

Platform Phases 3-7 remain deferred: ACORD alignment, canonicalization, review/versioning, regional mapping, and change impact. Deep Phase 1 repository analysis and untrusted execution isolation also remain open.
