# Next Steps

Last updated: 2026-09-24

The first unchecked item is the recommended next action.

## Immediate

- [x] **NS-01 / M0.1-M0.3:** Add or identify one representative regional Quote API and record its solution path, .NET SDK version, region name, system name, and OpenAPI path.
- [x] **NS-UI-01 / M0.6:** Add a safe intake-only Streamlit page for repository and OpenAPI upload, inventory preview, and manifest download.
- [x] **NS-02 / M0.4-M0.5:** Scaffold the Python and .NET projects with empty passing test suites.
- [x] **NS-03 / M1.1-M1.10:** Implement and fixture-test DiscoveryModel v1 before building either parser.

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
