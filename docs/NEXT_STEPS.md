# Next Steps

Last updated: 2026-09-30

The first unchecked item is the recommended next action.

## Immediate

- [ ] **NS-FIX-03:** Fix two pre-existing test isolation failures — `test_acord_alignment_renders_entity_domain_and_approval_workspaces` needs `monkeypatch` for `ALIGNMENT_AGENT_DATABASE`, and `test_phase_two_selects_the_matching_region_repository_and_discovery_artifact` needs `monkeypatch` for `CANONICAL_DATABASE`. Both fail because real project databases (`.alignments/alignment-agent.sqlite3` with existing checkpoints and `.canonical/canonical-models.sqlite3` with v1/v2/v3) leak into the tests.
- [x] **NS-FIX-02:** Fix Domain column missing from Regional normalization review tab and approval state lost on page reload.
- [x] **NS-FIX-01 / P2.6ae:** Clear the baseline defects found by running the application: the corrupted `Â·` separator in the delete-alignment dialog, the dialog closing on a full-script rerun, two Streamlit assertions reading the wrong AppTest widget collection, and the failing Ruff lint/format gates.
- [x] **NS-UI-44 / P2.6ad:** Remove OpenAI API key and model settings from the front end and read `OPENAI_API_KEY` and `OPENAI_MODEL` from the ignored `.env` file only.
- [x] **NS-ALIGN-03 / A3.1-A3.5:** Route alignment proposal generation through a dedicated LangGraph Alignment Agent with a proper package boundary, baseline-first/ACORD fallback, bounded retry, SQLite checkpoints and review drafts, and failed-node resume from the same saved evidence.
- [x] **NS-UI-43 / P2.6ac:** Show every unresolved alignment decision instead of the first ten, grouped by approval versus invalid/missing detail in a compact scrollable review panel.
- [x] **NS-UI-42 / P2.6ab:** Replace Domain/Capability tables with one compact Domain → Capability review tree that has status filtering, per-node reviewed decisions and approval, approval-reset semantics, progress, and confirmed bulk approval for filtered nodes.
- [x] **NS-CANONICAL-03 / C2.7:** Make the validated ACORD alignment submit action append the approved model directly to SQLite as the next immutable `vN`, expose clear lock/readiness feedback, and keep every submitted version selectable as an approved canonical baseline.
- [x] **NS-UI-41 / P2.6aa:** Compact the Entity → Attribute tree with on-demand node review, apply Full/Partial/Not-matched filtering to both levels, and add a confirmed approve-all action for the filtered nodes with a shared reason and clearer unresolved-count categories.
- [x] **NS-UI-40 / P2.6z:** Add explicit entity/attribute approval checkboxes to the review tree, reset approval when a decision changes, show approval progress, and block final submission until every tree node is approved.
- [x] **NS-UI-39 / P2.6y:** Replace the duplicate entity/attribute tables and attribute selector with one Entity → Attribute tree in which every attribute appears once with its evidence and review controls.
- [x] **NS-UI-38 / P2.6x:** Present entity matches as an expandable Entity → Attributes review tree with tabular field evidence, radio-button full/partial/not-matched review status, reviewed description and reason, and separate preservation of proposed versus reviewed status in approved artifacts.
- [x] **NS-CANONICAL-02 / C2.1-C2.6:** Use a submitted canonical version as the baseline for later regions, compare baseline first and ACORD second, expose true gaps for manual or reviewer-invoked OpenAI proposals with descriptions and constraints, and merge only approved deltas into the Canonical Model workflow.
- [x] **NS-CANONICAL-01 / C1.1-C1.5:** Add whole-model final review, per-item keep-original/reject decisions, immutable SQLite version submission, version history, and reviewed OpenAPI JSON/YAML generation with descriptions and constraints.
- [x] **NS-ALIGN-02 / A2.8:** Make the approved Canonical Model an explicitly named separate sidebar page while preserving navigation for sessions that stored the former Canonical View label.
- [x] **NS-ALIGN-01 / A2.1-A2.7:** Implement the ACORD Alignment workspace with separate regional entity/attribute and domain/capability reviews, full/partial/not-matched status, unmatched-first percentage reporting, ACORD-or-manual decisions with required reasons, approval gating, persisted review artifacts, and the final Canonical Model/Endpoint views.
- [x] **NS-UI-37 / P2.6w:** Make ACORD ingestion, ACORD alignment, and Canonical View structurally separate sidebar pages rather than hidden tabs; keep exactly four crawler tabs in the top tab control.
- [x] **NS-UI-36 / P2.6v:** Keep only the four crawler stages in the visible top tab row; expose ACORD ingestion, ACORD alignment, and Canonical View as separate sidebar pages, with planned entity, domain/capability, and percentage gap views.
- [x] **NS-ACORD-02 / A1.7:** Fix ACORD YAML upload intake so the selected file survives label/version/authorization reruns, ingestion reads the keyed uploader value, and validation identifies the exact missing input.
- [x] **NS-UI-35 / P2.6u:** Split sidebar navigation into Crawler code and ACORD view groups, and add a gated ACORD alignment workspace describing alignment with the regionally generated entity and domain catalog.
- [x] **NS-ACORD-01 / A1.1-A1.6:** Implement the independent ACORD OpenAPI YAML/JSON RAG pipeline with recursive endpoint/model extraction, descriptions/comments/constraints, Discovery-equivalent artifacts, persistent semantic chunks, saved-history reopening, and retrieval inspection. This operator-requested slice intentionally ran before P2.8 without performing alignment.
- [x] **NS-UI-34 / P2.6t:** Remove per-entity normalization settings from Regional View and make the four-stage progress bar advance through partial Analyzer coverage to Regional View when analysis completes.
- [x] **NS-P2-14 / P2.7h:** Continue a partial API Analyzer run with a fresh bounded budget while reusing validated completed semantics and sending only unfinished targets to the provider.
- [x] **NS-UI-33 / P2.6s:** Replace the sidebar radio with compact workspace tags, remove the six workflow status cards, keep a four-stage regional progress bar, and move ACORD ingestion into a separate unnumbered RAG pipeline workspace.
- [x] **NS-P2-13 / P2.7g:** Remove the LLM usage summary/ledger from the API Analyzer UI and remove entity-relationship source from Phase 2 generation, persistence, preview, downloads, and the artifact contract.
- [x] **NS-P2-12 / P2.7f:** Enforce text-only LLM payloads and Phase 2 artifacts; remove SVG generation and browser-rendered diagrams. The interim Mermaid source was subsequently removed by P2.7g.
- [x] **NS-P2-11 / P2.3a:** Reconcile provider response-status deviations to the authoritative Discovery inventory, retain every discovered status exactly once, and expose the disagreement as a review gap rather than dropping the endpoint.
- [x] **NS-UI-32 / P2.6r:** Add a clickable sidebar agent menu for Discovery, Repository RAG, and API Analyzer that opens the corresponding main workspace while preserving selected application and repository state.
- [x] **NS-P2-09 / P2.7e:** Show input/output/total token usage for every LLM call and let the operator configure per-request maximum input and output tokens.
- [x] **NS-P2-10 / P2.4g:** Add `x-request-model` to every model-backed OpenAPI request body with its component reference, model description, requiredness, and complete direct attribute details, symmetric with `x-response-model`.
- [x] **NS-UI-29 / P2.6m:** In partial API Analyzer runs, show the coverage/stop warning and let an unenriched model inherit a unique domain from its directly mapped analyzed endpoints, with the fallback source clearly labeled.
- [x] **NS-UI-30 / P2.6n:** In the Regional catalog's all-APIs view, collapse superseded runs with the same region/application/repository identity and retain the run with the strongest semantic and Discovery coverage; keep explicit per-run selection available.
- [x] **NS-RAG-05 / P2.6o:** Add an application/index selector directly to Repository RAG, label saved profiles as `RAG ready` or `no RAG index`, reopen the selected saved manifest/Chroma association, and show the same readiness label in the API Analyzer selector.
- [x] **NS-RAG-06 / P2.6p:** Put the active Discovery run first in Repository RAG and label every choice with region, application, repository, run ID, current-discovery state, and RAG readiness.
- [x] **NS-UI-31 / P2.6q:** Present the platform as one six-stage application pipeline—Discovery, Repository RAG, API Analyzer, Regional View, ACORD ingestion, and ACORD alignment—with selected-repository identity and honest complete/partial/ready/locked/planned status.
- [x] **NS-P2-08 / P2.7d:** Document the high-level architecture and exact LLM data flow; add tiktoken preflight counting, per-request input/output ceilings, configurable run-token and request ceilings, fail-closed budget stops, and provider-reported usage in the enrichment report and UI.
- [x] **NS-P2-07 / P2.6l:** Make repository RAG mandatory at the API Analyzer boundary. The originally generated relationship artifacts were subsequently removed by ADR-031.
- [x] **NS-UI-26 / P2.6k:** Add an entire-region normalization approval tab with per-entity and per-field original-versus-AI decisions, optional comments, deterministic approved-name/type deduplication, complete source/API/endpoint truth mapping, and Excel plus Mermaid downloads.
- [x] **NS-P2-06 / P2.4f:** Show each operation's request body before responses in enriched OpenAPI, including the empty request structure.
- [x] **NS-P1-01 / R1.10:** Require a repository in Phase 1 and treat OpenAPI YAML/JSON as optional reconciliation evidence across the graph, CLI, UI, tests, and operator documentation.
- [x] **NS-P2-05 / P2.4e:** Always emit `servers` and `components.schemas` in enriched OpenAPI, with a deterministic relative server when no deployment URL is available.
- [x] **NS-P2-04 / P2.4d:** Keep request and response body structure present in enriched OpenAPI by emitting an empty JSON schema when no contract model is discovered.
- [x] **NS-UI-25 / P2.6j:** Persist trusted application profiles locally and add a previous-application selector that restores the repository, Discovery artifacts, RAG association, and Phase 2 output after restart.
- [x] **NS-UI-24 / P2.6i:** Add review-only, per-entity LLM normalization for entity and attribute names/descriptions on the Regional catalog page, with consent, schema validation, side-by-side proposal columns, and deterministic restoration of source names when a provider changes only their casing.
- [x] **NS-UI-23 / P2.6h:** Add API Analyzer descriptions and business metadata to regional entity, field, and endpoint tree views, with explicit pending values before enrichment.
- [x] **NS-UI-22 / P2.6g:** Replace the regional domain/capability table with a Region → Domain → Capability → API → Endpoint tree, retaining pending classifications explicitly.
- [x] **NS-UI-21 / P2.6f:** Replace the regional model-mapping table with a Region → API → Model tree that expands into endpoint usages and model fields.
- [x] **NS-UI-20 / P2.6e:** Add a regional catalog page with region and API filters, an all-APIs view, contract-model-to-endpoint mappings, and domain/capability endpoint inventory across completed in-session applications.
- [x] **NS-P2-03 / P2.4c-P2.6d:** Preserve OpenAPI request, response, and failure-status details during reconciliation and provide a retry action for the selected API Analyzer application profile.
- [x] **NS-UI-19 / P2.6c:** Isolate each Discovery upload and its freshly built RAG index in the Streamlit session; remove cross-upload saved-index selection so API Analyzer uses only the selected application's index.
- [x] **NS-RAG-04 / R1.9:** Fix Roslyn syntax-node identity for top-level statements and nested local functions that share a source span; verify against the reported eShopOnWeb snapshot.
- [x] **NS-RAG-03 / R1.8:** Fix duplicate Chroma IDs for repeated long-line windows, retain both retrieval occurrences, and reject any remaining collision before upsert. The reported repository itself was not available for a live retry.
- [x] **NS-RAG-01 / R1.1-R1.6:** Implement repository intake with optional YAML/JSON and reusable repository RAG: Roslyn hierarchy, typed relationship candidates, selectable Sentence Transformer/OpenAI embeddings, persistent Chroma, endpoint/entity/attribute retrieval, and grounded API Analyzer interpretation.
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
- [x] **NS-UI-27 / M7.9:** Supersede suffix-based contract filtering with endpoint reachability: retain user-authored DTOs, domain models, ViewModels, requests, responses, nested property models, collection element models, and inherited models when they are actually used by an API endpoint; continue excluding generated and unrelated types.
- [x] **NS-UI-28 / M7.10:** Preserve endpoint request, response, collection-element, and nested models when unresolved ASP.NET Core or NuGet dependencies force controller discovery through syntax fallback.
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
