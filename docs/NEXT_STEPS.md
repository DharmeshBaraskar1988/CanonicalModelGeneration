# Next Steps

Last updated: 2026-09-28

The first unchecked item is the recommended next action.

## Immediate

- [x] **NS-P2-05 / P2.4e:** Always emit `servers` and `components.schemas` in enriched OpenAPI, with a deterministic relative server when no deployment URL is available.
- [x] **NS-P2-04 / P2.4d:** Keep request and response body structure present in enriched OpenAPI by emitting an empty JSON schema when no contract model is discovered.
- [x] **NS-UI-25 / P2.6j:** Persist trusted application profiles locally and add a previous-application selector that restores the repository, Discovery artifacts, RAG association, and Phase 2 output after restart.
- [x] **NS-UI-24 / P2.6i:** Add review-only, per-entity LLM normalization for entity and attribute names/descriptions on the Regional catalog page, with consent, schema validation, and side-by-side proposal columns.
- [x] **NS-UI-23 / P2.6h:** Add API Analyzer descriptions and business metadata to regional entity, field, and endpoint tree views, with explicit pending values before enrichment.
- [x] **NS-UI-22 / P2.6g:** Replace the regional domain/capability table with a Region → Domain → Capability → API → Endpoint tree, retaining pending classifications explicitly.
- [x] **NS-UI-21 / P2.6f:** Replace the regional model-mapping table with a Region → API → Model tree that expands into endpoint usages and model fields.
- [x] **NS-UI-20 / P2.6e:** Add a regional catalog page with region and API filters, an all-APIs view, contract-model-to-endpoint mappings, and domain/capability endpoint inventory across completed in-session applications.
- [x] **NS-P2-03 / P2.4c-P2.6d:** Preserve OpenAPI request, response, and failure-status details during reconciliation and provide a retry action for the selected API Analyzer application profile.
- [x] **NS-UI-19 / P2.6c:** Isolate each Discovery upload and its freshly built RAG index in the Streamlit session; remove cross-upload saved-index selection so API Analyzer uses only the selected application's index.
- [x] **NS-RAG-04 / R1.9:** Fix Roslyn syntax-node identity for top-level statements and nested local functions that share a source span; verify against the reported eShopOnWeb snapshot.
- [x] **NS-RAG-03 / R1.8:** Fix duplicate Chroma IDs for repeated long-line windows, retain both retrieval occurrences, and reject any remaining collision before upsert. The reported repository itself was not available for a live retry.
- [x] **NS-RAG-01 / R1.1-R1.6:** Implement repository-or-YAML intake and reusable repository RAG: Roslyn hierarchy, typed relationship candidates, selectable Sentence Transformer/OpenAI embeddings, persistent Chroma, endpoint/entity/attribute retrieval, and grounded API Analyzer interpretation.
- [x] **NS-RAG-02 / R1.7:** Require focused target interpretation to explain retrieved code usages with claim-level chunk citations and explicit partial status when code meaning cannot be grounded.
- [x] **NS-UI-18 / P2.6b:** Make the Discovery → RAG → API Analyzer path selectable by in-session region/application/repository profile, preserve the matching RAG index, and show actionable Phase 2 readiness requirements.
- [x] **NS-01 / M0.1-M0.3:** Add or identify one representative regional Quote API and record its solution path, .NET SDK version, region name, system name, and OpenAPI path.
- [x] **NS-UI-01 / M0.6:** Add a safe intake-only Streamlit page for repository and OpenAPI upload, inventory preview, and manifest download.
- [x] **NS-02 / M0.4-M0.5:** Scaffold the Python and .NET projects with empty passing test suites.
- [x] **NS-03 / M1.1-M1.10:** Implement and fixture-test DiscoveryModel v1 before building either parser.
- [x] **NS-DOC-01 / M0.7:** Publish the installation and user guide, including .NET SDK and NuGet dependency setup.

## After the contract is accepted

- [x] **NS-04 / M2:** Build the Roslyn analyzer vertical slice for the selected Quote API.
- [x] **NS-05 / M3:** Build OpenAPI discovery against the same API.
- [x] **NS-06 / M4:** Normalize and reconcile the two evidence sources.
- [x] **NS-07 / M5-M6:** Add LangGraph orchestration, CLI, validation, and artifacts.
- [x] **NS-08 / M7:** Run end-to-end verification and complete MVP acceptance.

## Post-MVP

- [x] **NS-UI-02:** Add a Phase 1 results tab and a completion gate that unlocks Phase 2 planning without claiming Phase 2 implementation.
- [x] **NS-UI-03:** Present Phase 1 as a Discovery Agent with a visual artifact tree, JSON previews, and individual or bundled artifact downloads.
- [x] **NS-UI-04:** Run discovery for a trusted uploaded repository and show only its five derived artifacts in the Discovery Agent tab.
- [x] **NS-UI-05:** Replace technical relationship/evidence IDs in the operator artifact with resolved names and source locations.
- [x] **NS-UI-06:** Allow repository-only trusted discovery through Roslyn when no OpenAPI document is available.
- [x] **NS-UI-07:** Deterministically collapse repeated Roslyn observations before DiscoveryModel global-ID validation.
- [x] **NS-UI-08:** Select the controller-owning Web API project from multi-project uploads and reject empty discovery as unsuccessful.
- [x] **NS-UI-09:** Support conventional ASP.NET Core MVC actions and remove the fixture-specific DTO namespace restriction.
- [x] **NS-UI-10:** Explore and aggregate every controller-owning non-test project in an uploaded repository.
- [x] **NS-UI-11:** Add Minimal API, endpoint-base, and syntax-degraded endpoint inventory against the provided eShopOnWeb repository.
- [x] **NS-UI-12:** Replace internal IDs in the operator-facing API Catalog with operation/model names, HTTP status labels, and supporting source locations.
- [x] **NS-UI-13:** Discover MVC `View(model)` response ViewModels and show their nested and inherited model relations inside each API Catalog response.
- [x] **NS-UI-14:** Remove internal IDs from all five operator-facing artifacts and enforce readable names and source locations during artifact generation.
- [x] **NS-UI-15 / M7.7:** Restrict Phase 1 entities to endpoint-reachable, user-authored `*ViewModel` types; preserve endpoint and nested ViewModel relationships while excluding DTOs, domain models, generated types, and unrelated models.
- [x] **NS-UI-16 / M7.8:** Expand the endpoint contract boundary to concrete `*ViewModel`, `*Request`, and `*Response` types; exclude `Base*` infrastructure models and DTOs, and show request and response model trees in the API Catalog.
- [x] **NS-P2-01 / P2.1-P2.7a:** Implement the API Analyzer Agent with taxonomy-preferred or repository-derived domain/capability classification, local Chroma ingestion and bounded retrieval, endpoint/entity/attribute/enum semantics, fixed OpenAPI extensions, provenance, validation, and UI artifacts.
- [x] **NS-P2-01a / P2.4a:** Preserve parameter/request details and source lineage in enriched OpenAPI, explicitly identify response contract models, and retain deterministic ViewModel/field descriptions during partial semantic runs.
- [x] **NS-P2-01b / P2.4b:** Expand each response-model extension with its component reference and described direct attributes, and correct partial-run ViewModel component descriptions.
- [x] **NS-UI-17 / P2.6a:** Improve the Discovery Agent region and application-details experience with guided inputs, separated source uploads, and a completed-run application summary.
- [x] **NS-PROD-01 / P2.7b:** Separate API Analyzer contracts, prompts, provider adapters, and bounded tools into production namespaces; document the source/generated-file boundary and retain compatibility imports.
- [x] **NS-PROD-02 / P2.7c:** Create explicit `discovery_agent/` and `api_analyzer/` package boundaries and require serialized `discovery-model.json` as the only runtime handoff between them.
- [ ] **NS-P2-02 / P2.8:** Replace the currently rejected OpenAI API key with an active approved key, restart Streamlit, run Phase 2 against an approved real repository, review domain/capability and all generated semantics in `enriched-openapi.yaml`, and record acceptance evidence.
- [ ] **NS-DEEP-01:** Implement evidence-linked call paths, mappings, persistence, integrations, security, shared-code, and Razor Page discovery before claiming a deep repository analysis.
- [ ] **NS-09:** Run the accepted workflow against an approved real regional Quote API before production use.

## Information to capture with the sample API

- Region and source-system names
- Absolute or repository-relative `.sln`/`.csproj` path
- Target framework and required .NET SDK
- Quote controller and primary endpoint(s)
- OpenAPI file path and version
- Build/test command
- Any source folders that must be excluded
- Whether the sample contains confidential or regulated data

## Rule for future updates

When an item is completed, check it here, update its milestone task in `IMPLEMENTATION_PLAN.md`, record evidence in `STATUS.md`, and move the next executable action to the top of this file.
