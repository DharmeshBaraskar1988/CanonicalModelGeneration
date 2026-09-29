# Canonical Model Generator - Implementation Plan

Last updated: 2026-09-29
Current release: Phase 2 API Analyzer Agent  
Overall status: In progress

## Plan amendment - ACORD alignment and canonical review (2026-09-29)

Status: Complete for a single-region, reviewer-approved alignment artifact; canonical version
governance and multi-region consolidation remain later capabilities.

- [x] **A2.1** Compare one selected regional entity/attribute catalog with one accepted ACORD ingestion using deterministic name, type, description, and structural scoring.
- [x] **A2.2** Classify entities, attributes, domains, and capabilities as full match, partial match, or not matched, and report weighted matched and unmatched percentages.
- [x] **A2.3** Present unmatched and partial details first while retaining filters that expose every full-match result and its supporting descriptions, comments, constraints, and candidate.
- [x] **A2.4** Let a reviewer select the ACORD candidate or enter a manual canonical name and require a reason for every partial, unmatched, or manual decision.
- [x] **A2.5** Block approval until every entity, attribute, domain, and capability decision is valid; never mutate Regional View or ACORD ingestion evidence.
- [x] **A2.6** Generate and persist an approved canonical artifact containing canonical entities, attributes, domains, capabilities, canonical endpoints, approved entity usages, and the complete mapping/reason ledger.
- [x] **A2.7** Add a Canonical View with model, endpoint, and approval-mapping views plus JSON download, saved-history reopening, deterministic unit coverage, and Streamlit flow coverage.

This slice advances roadmap alignment and produces an approved single-region canonical model. It
does not claim enterprise canonical versioning, multi-region conflict resolution, regional adapter
generation, or change-impact analysis.

## Plan amendment - ACORD reference RAG (2026-09-29)

Status: Complete; ACORD-to-regional alignment remains a later, separately accepted capability.

- [x] **A1.1** Accept one authorized ACORD OpenAPI 3 YAML/JSON document with an explicit reference label and approved version in the independent ACORD workspace.
- [x] **A1.2** Deterministically extract endpoints, parameters, request/response bodies, named schemas, inline nested objects, attributes, enums, and structural relationships.
- [x] **A1.3** Preserve available summaries, descriptions, `$comment`/documentation notes, constraints, source hashes, and JSON-pointer lineage without inventing semantic content.
- [x] **A1.4** Create bounded endpoint and entity chunks that keep their descriptions, comments, fields, response/request models, and constraints together; persist them in an ACORD-specific local Chroma index.
- [x] **A1.5** Present the same five operator artifact views as Discovery, with individual/bundled downloads, a downloadable RAG manifest, saved-ingestion reopening, and retrieval inspection.
- [x] **A1.6** Verify recursive extraction, artifact rendering, persistence, and retrieval with focused tests; keep regional alignment and canonical generation out of this slice.
- [x] **A1.7** Keep a selected ACORD YAML/JSON upload stable while the other intake fields rerun, show an explicit selected-file confirmation, and report each genuinely missing field separately before ingestion.

This amendment intentionally executes before the existing P2.8 live-model acceptance item because
the operator explicitly requested the independent ACORD ingestion workspace. It does not weaken or
complete P2.8.

## Plan amendment - Repository RAG (2026-09-26)

Status: Complete; live OpenAI semantic accuracy remains a separate Phase 2 acceptance item.

- [x] **R1.1** Accept repository ZIP with optional OpenAPI YAML/JSON input. Specification-only coverage was implemented here and later removed by R1.10.
- [x] **R1.2** Extract file/type/member hierarchy using Roslyn syntax, with stable source spans, parent-child links, typed reference candidates, explicit ambiguity, bounded chunk splitting and redaction.
- [x] **R1.3** Provide local Sentence Transformer and OpenAI `text-embedding-ada-002`/embedding-3 model adapters selectable in the UI, with explicit cloud source sharing.
- [x] **R1.4** Persist snapshot/model-specific Chroma indexes and versioned manifests; retrieve endpoint/entity/attribute context using exact lineage, lexical/vector ranking, and parent/relationship expansion.
- [x] **R1.5** Add an independent UI indexing/retrieval flow, reuse its artifact in API Analyzer, and verify hierarchy, attribution, persistence, isolation and both input paths.
- [x] **R1.6** Interpret a selected Discovery target or free code query using retrieved, cited source chunks; reject unsupported citations and distinguish structural facts from inferred meaning.
- [x] **R1.7** For focused target interpretation, inspect retrieved code usages as separate observed/inferred claims with validated chunk citations; mark a result partial when no grounded code claim is available.
- [x] **R1.8** Correct repeated long-line window identity collisions, preserve distinct retrieval occurrences, and fail before Chroma upsert if any duplicate chunk identity remains. Verified with regression tests and repository-RAG indexing.
- [x] **R1.9** Correct Roslyn syntax identities for a `GlobalStatement` and nested `LocalFunctionStatement` with the same span, preserving parent-child lineage and both retrieval results. Verified against the reported eShopOnWeb source snapshot and Chroma regression test.
- [x] **R1.10** Require the .NET repository in Phase 1 across the Discovery graph, CLI, and Streamlit intake; keep OpenAPI YAML/JSON optional reconciliation evidence.
- [x] **P2.6c** Isolate each Streamlit Discovery submission and newly built RAG index; do not expose or reuse indexes from other uploads, and pass only the selected application's index to API Analyzer.
- [x] **P2.4c / P2.6d** Retain OpenAPI request/response/failure details when reconciling repository evidence, and allow the selected API Analyzer application profile to be rerun after success or failure.
- [x] **P2.4d** Keep request and response body structure present in enriched OpenAPI by emitting an empty JSON schema when no contract model is discovered.
- [x] **P2.4e** Always emit the enriched OpenAPI `servers` and `components.schemas` structures, using a deterministic relative server when no deployment URL is available.
- [x] **P2.4f** Render each operation's request body before its responses, including an explicit empty schema when no request model was discovered.
- [x] **P2.4g** Include an `x-request-model` block on model-backed request bodies containing the component name/reference, model description, and every direct attribute's requiredness, schema, and semantic or structural description.
- [x] **P2.3a** Reconcile provider response-status omissions, additions, and duplicates against the authoritative Phase 1 inventory before validation; retain each discovered status exactly once and record the mismatch as an explicit semantic context gap.
- [x] **P2.6l** Require a repository and snapshot-matched saved RAG index for every API Analyzer run. The relationship artifact originally included in this slice was removed from the Phase 2 contract by P2.7g/ADR-031.
- [x] **P2.6m** Make partial Analyzer coverage explicit in the Regional catalog and project a unique analyzed endpoint domain onto its directly mapped request/response model when entity enrichment has not completed; label that domain as endpoint-derived rather than entity-analyzed.
- [x] **P2.6n** Collapse superseded duplicate application/repository runs in the Regional all-APIs projection using deterministic semantic/Discovery coverage quality, while preserving explicit historical run selection.
- [x] **P2.6o** Let Repository RAG select an exact saved application profile and reopen its persisted manifest/Chroma association; distinguish profiles with and without an available local index in both RAG and API Analyzer selectors.
- [x] **P2.6p** Make the current Discovery ingestion immediately identifiable and first-selectable in Repository RAG using region/application/repository/run identity plus current and index-readiness labels.
- [x] **P2.6q** Add a six-stage application workflow board and numbered workspaces that preserve the active repository identity across Discovery, RAG, API Analyzer, and Regional View while visibly gating unimplemented ACORD ingestion and alignment.
- [x] **P2.6r** Add sidebar navigation for the first three agent stages and synchronize it with the main workspace tabs.
- [x] **P2.6s** Replace the sidebar radio with compact workspace tags, reduce the selected-application journey to a progress-only four-stage regional pipeline, and expose ACORD ingestion as a separate unnumbered RAG pipeline workspace.
- [x] **P2.6t** Remove per-entity entity/attribute normalization controls and proposal columns from Regional View; count partial/current work as reached progress and make Regional View the current fourth stage after API Analyzer completes.
- [x] **P2.6u** Group Streamlit navigation into Crawler code (Discovery, Repository RAG, API Analyzer, Regional View) and ACORD view (ACORD ingestion, ACORD alignment); keep alignment gated and identify the regional entity/domain catalog as its future comparison input.
- [x] **P2.6v** Remove ACORD workspaces from the visible crawler tab row and expose ACORD ingestion, ACORD alignment, and Canonical View as separate sidebar pages. Add planned Canonical View sections for entity alignment, domain/capability alignment, and aligned-versus-unaligned ACORD gap coverage.
- [x] **P2.6w** Replace the CSS-hidden ACORD tab implementation with structurally separate keyed page containers; ensure the only members of the top `st.tabs` control are Discovery, Repository RAG, API Analyzer, and Regional View.

Acceptance: exact subject retrieval returns its owning source and cited context; duplicate symbol
names are not silently conflated; all limits and unresolved reference candidates are visible;
reopening an index preserves results and rejects mismatched source/model inputs. Local model
execution and offline adapter contracts are verified separately from live OpenAI access.

## 1. Objective

Build a deterministic discovery workflow that analyzes one regional insurance .NET Web API repository and, when supplied, its OpenAPI specification; normalizes the available evidence into a versioned `DiscoveryModel`; validates the result; and generates traceable discovery artifacts.

The Discovery MVP is the foundation for later classification, regional alignment, and canonical-model generation. Those later capabilities are deliberately outside this release.

## 2. Target workflow

```text
.NET repository -> Roslyn analyzer ----+
                                        +-> Normalize -> Reconcile -> Validate -> Artifacts
Optional OpenAPI spec -> OpenAPI parser -+
```

LangGraph orchestrates this workflow. Parsing, normalization, reconciliation, and validation remain deterministic services.

## 3. Technology baseline

- Python 3.12
- LangGraph
- Pydantic 2
- pytest
- .NET 8
- Roslyn (`Microsoft.CodeAnalysis`)
- xUnit
- `System.Text.Json`
- OpenAPI JSON and YAML support

Exact dependency versions will be pinned during project scaffolding.

## 4. Milestones

### M0 - Inputs and project baseline

Status: Complete

- [x] **M0.1** Obtain one representative regional Quote API repository or fixture.
- [x] **M0.2** Obtain its OpenAPI JSON or YAML specification.
- [x] **M0.3** Record supported .NET SDK and solution layout.
- [x] **M0.4** Establish Python and .NET project scaffolds.
- [x] **M0.5** Add baseline lint, format, build, and test commands.
- [x] **M0.6** Add an intake-only Streamlit page with safe ZIP inspection and deterministic manifest output.
- [x] **M0.7** Publish an installation and user guide covering Python setup, .NET SDK and NuGet dependency restoration, UI and CLI execution, verification, and troubleshooting.

Acceptance criteria:

- The selected Quote API and OpenAPI spec are accessible locally.
- Empty Python and .NET test suites execute successfully.
- Setup and verification commands are documented.
- The intake UI never extracts or executes uploaded repository content and clearly distinguishes intake from full discovery.

### M1 - DiscoveryModel v1 contract

Status: Complete

- [x] **M1.1** Define metadata and source descriptors.
- [x] **M1.2** Define operation, parameter, request, and response models.
- [x] **M1.3** Define entity, attribute, type, nullability, and collection models.
- [x] **M1.4** Define enum and validation models.
- [x] **M1.5** Define relationship vocabulary.
- [x] **M1.6** Define source-lineage and evidence models.
- [x] **M1.7** Define diagnostics, severity, summary, and run status.
- [x] **M1.8** Define deterministic stable-ID rules.
- [x] **M1.9** Add representative valid and invalid JSON fixtures.
- [x] **M1.10** Export and version a JSON Schema.

Acceptance criteria:

- Pydantic validates the representative fixture.
- Invalid references and malformed records fail with useful errors.
- The contract can represent both Roslyn and OpenAPI evidence without source-specific downstream models.

### M2 - Roslyn analyzer vertical slice

Status: Complete

- [x] **M2.1** Load a solution or project using Roslyn/MSBuild.
- [x] **M2.2** Discover controllers, actions, routes, and HTTP methods.
- [x] **M2.3** Resolve request and response DTOs.
- [x] **M2.4** Extract properties, CLR types, nullability, collections, inheritance, and nested types.
- [x] **M2.5** Extract enums and common validation attributes.
- [x] **M2.6** Emit `ACCEPTS`, `RETURNS`, `CONTAINS`, and `INHERITS` relationships.
- [x] **M2.7** Attach file, symbol, and line-level lineage.
- [x] **M2.8** Serialize analyzer output conforming to DiscoveryModel v1.
- [x] **M2.9** Add analyzer unit and fixture tests.

Optional after the core slice:

- [ ] **M2.10** Evaluate service call-path extraction and add `CALLS` only if sufficiently reliable.

Acceptance criteria:

- The chosen Quote API's endpoints, DTOs, fields, enums, validations, and core relationships are found.
- Analyzer output passes the DiscoveryModel schema.
- Repeated runs produce stable IDs and ordering.

### M3 - OpenAPI discovery

Status: Complete

- [x] **M3.1** Load OpenAPI JSON and YAML.
- [x] **M3.2** Extract paths, operations, parameters, request bodies, and responses.
- [x] **M3.3** Resolve local component `$ref` references safely.
- [x] **M3.4** Extract schemas, required fields, arrays, enums, formats, and constraints.
- [x] **M3.5** Support required composition cases such as `allOf`; record unsupported cases as diagnostics.
- [x] **M3.6** Attach document and JSON-pointer lineage.
- [x] **M3.7** Produce DiscoveryModel-compatible evidence.
- [x] **M3.8** Add parser unit and fixture tests.

Acceptance criteria:

- The chosen Quote OpenAPI document parses without losing operations or referenced schemas.
- Output passes the DiscoveryModel schema.
- Unsupported or ambiguous constructs generate explicit diagnostics.

### M4 - Normalization and reconciliation

Status: Complete

- [x] **M4.1** Normalize CLR and OpenAPI primitive types.
- [x] **M4.2** Normalize names while retaining original names.
- [x] **M4.3** Normalize nullability, requiredness, formats, arrays, and references.
- [x] **M4.4** Match Roslyn and OpenAPI elements using deterministic keys.
- [x] **M4.5** Merge agreeing evidence and retain both sources.
- [x] **M4.6** Emit diagnostics for type, requiredness, route, response, or constraint conflicts.
- [x] **M4.7** Enforce deterministic ordering.
- [x] **M4.8** Add unit tests for agreement, missing evidence, and conflicts.

Acceptance criteria:

- Matching evidence is combined without losing lineage.
- Conflicting evidence is preserved and reported, never silently overwritten.
- The same inputs produce byte-stable normalized JSON where environment-specific paths are excluded or normalized.

### M5 - LangGraph orchestration and CLI

Status: Complete

- [x] **M5.1** Define typed graph state.
- [x] **M5.2** Implement intake and input-validation node.
- [x] **M5.3** Implement Roslyn invocation node.
- [x] **M5.4** Implement OpenAPI discovery node.
- [x] **M5.5** Implement normalize/reconcile node.
- [x] **M5.6** Implement validation node.
- [x] **M5.7** Implement artifact-generation node.
- [x] **M5.8** Add routing for fatal errors and partial results.
- [x] **M5.9** Add a CLI accepting region, repository, OpenAPI, and output paths.
- [x] **M5.10** Add structured logs and run identifiers.
- [x] **M5.11** Evaluate parallel Roslyn/OpenAPI branches after the sequential workflow is stable.

Acceptance criteria:

- One CLI command runs the complete discovery workflow.
- Fatal input errors stop safely with a nonzero exit code.
- Nonfatal discovery gaps appear in diagnostics and allow usable artifacts to be produced.

### M6 - Artifact generation

Status: Complete

- [x] **M6.1** Generate `discovery-model.json`.
- [x] **M6.2** Generate `api-catalog.json`.
- [x] **M6.3** Generate `data-model.json`.
- [x] **M6.4** Generate `relationship-graph.json`.
- [x] **M6.5** Generate `validation-enums.json`.
- [x] **M6.6** Generate `lineage.json`.
- [x] **M6.7** Validate every generated artifact before committing it to the output directory.

Acceptance criteria:

- All artifacts are generated from one normalized model.
- Artifact counts agree with the summary.
- Every operation, entity, and attribute has source lineage or a diagnostic explaining why it does not.

### M7 - End-to-end verification and MVP acceptance

Status: Complete

- [x] **M7.1** Add an end-to-end test for the chosen Quote API.
- [x] **M7.2** Add golden-file/snapshot comparisons.
- [x] **M7.3** Manually compare output with the controller, DTOs, enums, validations, and OpenAPI spec.
- [x] **M7.4** Record coverage counts and known limitations.
- [x] **M7.5** Document local setup and usage.
- [x] **M7.6** Complete the MVP acceptance review.
- [x] **M7.7** Amend Phase 1 entity scope to retain only user-authored `*ViewModel` types reachable from API endpoints, preserve endpoint `ACCEPTS`/`RETURNS` links and nested/base ViewModel links, and exclude DTOs, domain models, generated types, and unrelated ViewModels.
- [x] **M7.8** Supersede the ViewModel-only boundary with endpoint-reachable concrete `*ViewModel`, `*Request`, and `*Response` contract models; exclude `Base*` infrastructure classes and DTOs, and expose request and response model trees in the API Catalog.
- [x] **M7.9** Supersede contract-name suffix filtering with endpoint reachability. Starting from controller/minimal-API request, response, and model-valued parameter types, retain every user-authored source model reachable through properties, collection elements, or inheritance, including DTOs and domain models; exclude generated and unrelated types.
- [x] **M7.10** In syntax-degraded controller discovery, resolve project-local body parameter and declared return payload types from source syntax, add them as graph roots, and recursively retain their nested models even when ASP.NET Core or third-party dependencies are unresolved.

Acceptance criteria:

- All expected Quote endpoints are identified.
- Endpoint-linked request and response types resolve correctly regardless of naming convention.
- Expected endpoint contract fields, referenced enums, validations, and endpoint/nested/inheritance relationships are captured; generated and unrelated repository models are excluded.
- OpenAPI/Roslyn conflicts are visible.
- Outputs are deterministic and schema-valid.
- Automated tests pass and manual review is recorded.

## 5. DiscoveryModel v1 contents

The contract must cover:

```text
DiscoveryModel
|- contractVersion
|- run
|- region
|- system
|- sources[]
|- operations[]
|- entities[]
|  |- attributes[]
|- enums[]
|- validations[]
|- relationships[]
|- evidence[]
|- lineage[]
|- diagnostics[]
`- summary
```

Exact fields and invariants are finalized in M1. IDs should be derived from stable semantic coordinates, not random UUIDs.

## 6. Out of scope for the Discovery MVP

- LLM calls or embeddings
- Business domain/capability classification
- Cross-region semantic alignment
- Canonical entity or attribute generation
- Discovery review or human approval UI (the intake-only upload page approved in ADR-005 is permitted)
- Database persistence
- Regional adapter generation
- Canonical-model version evolution

## 7. Risks and controls

| Risk | Control |
|---|---|
| Discovery contract changes repeatedly | Complete and fixture-test M1 before parser implementation. |
| Roslyn compilation fails on a customer solution | Preserve partial syntax/symbol results and emit diagnostics. |
| OpenAPI and source disagree | Store evidence from both and report a conflict. |
| Scope expands into canonicalization | Enforce the out-of-scope list and MVP acceptance gate. |
| Unstable generated output | Stable ID rules, deterministic sorting, and golden tests. |
| Call-graph analysis becomes expensive | Keep `CALLS` optional until core discovery is accepted. |

## 8. Release gate

Work on classification and alignment may begin only after M7 is accepted and a decision is recorded in `docs/DECISIONS.md`.

## 9. Platform roadmap after the Discovery MVP

The completed M0-M7 plan is Platform Phase 1. Future platform phases remain separate releases:

1. **Discovery — Complete:** regional API inventory and traceable discovery artifacts.
2. **API Analyzer Agent — In progress:** classify domain/capability and generate a source-grounded enriched OpenAPI contract.
3. **ACORD reference ingestion — Complete:** independently parse and index an approved ACORD OpenAPI reference.
4. **ACORD alignment — Complete for one-region review:** compare a selected regional catalog with an accepted ACORD reference, resolve every mapping, and persist the approved review artifact.
5. **Canonicalization — In progress:** generate the approved single-region canonical model and endpoints from alignment decisions; multi-region consolidation and version governance remain open.
6. **Review and versioning — Not started:** approve and govern canonical versions.
7. **Regional mapping — Not started:** maintain region-to-canonical mappings.
8. **Change impact — Not started:** assess future regional and canonical changes.

The normalization performed inside Phase 1 remains limited to reconciling Roslyn and OpenAPI observations for one source system. Cross-region technical normalization is deferred; it is not required by the current Phase 2 release.

The Streamlit UI exposes the accepted Phase 1 results in a dedicated tab. A successful Phase 1 run unlocks the Phase 2 API Analyzer Agent, which uses bounded, redacted source-code context and schema-validated OpenAI output to classify domain/capability and generate endpoint, ViewModel, attribute, and enum semantics. Operators can preview and download the self-contained enriched OpenAPI plus semantic metadata, evidence, and coverage artifacts.

The Phase 1 tab is presented as the Discovery Agent workspace. It visualizes the deterministic repository/OpenAPI extraction tree and exposes the accepted M7 JSON artifacts for preview and download.

For the trusted-code local workflow, the Discovery Agent extracts and analyzes the uploaded repository, then exposes only the five derived views: API Catalog, Data Model, Relationship Graph, Validation and Enums, and Lineage. The internal DiscoveryModel remains the validated source for those artifacts but is not presented as a sixth result.

Operator-facing relationship artifacts resolve internal identifiers into readable endpoint/ViewModel/attribute names and supporting source locations. Stable IDs remain in the internal DiscoveryModel for deterministic linking and validation.

The operator-facing API Catalog likewise presents operation names, resolved request and response model names, HTTP status labels, parameter details, and supporting source locations instead of internal operation, evidence, parameter, entity, or response identifiers.

For conventional MVC actions returning `IActionResult`, Roslyn resolves source-defined models passed to `View(model)`. Each API Catalog response includes a bounded, cycle-safe response-model tree containing reachable model fields, nested collection/object relations, inheritance, and model lineage.

All five operator-facing artifacts are presentation views and must expose readable subject/model/field names plus source locations rather than stable internal identifiers. Artifact generation rejects an operator payload containing internal ID-reference keys or stable-ID values. The internal `discovery-model.json` retains stable IDs because reconciliation, validation, and deterministic linking depend on them.

The local Discovery Agent supports a repository-only fallback. When OpenAPI is absent it generates the five operator artifacts from Roslyn evidence and preserves that reduced evidence scope; when OpenAPI is present it runs the full reconciliation path.

Roslyn mapping deterministically collapses repeated observations with the same stable ID before contract validation. This supports larger project graphs that report the same diagnostic or symbol more than once without weakening the DiscoveryModel global-ID invariant.

For multi-project repository uploads, the local UI selects the nearest project owning the discovered controller files, preferring API/Web projects over test projects. A run with no supported operations and no entities is reported as unsuccessful rather than exposing empty artifacts.

The Roslyn analyzer recognizes public conventional MVC actions in addition to attribute-routed API actions. When explicit routing metadata is absent it derives a deterministic controller/action route. The accepted Phase 1 output retains every user-authored model directly used by an endpoint or reachable through properties, collection elements, or inheritance, independent of naming suffix. Generated and unrelated models are removed with their dangling evidence and relationships. The API Catalog expands both request and response model trees. When dependencies are unresolved, syntax fallback resolves project-local parameter and declared return payload types so degraded runs retain the same endpoint model roots.

Uploaded repositories are explored across all non-test projects that own controller files. Their Roslyn models are aggregated deterministically before optional OpenAPI reconciliation, and the UI lists every analyzed project rather than representing one selected project as the repository result.

When compilation dependencies are unresolved, endpoint inventory falls back to syntax evidence for controller actions, attributed endpoint-base actions, and Minimal API route registrations. Syntax fallback retains project-local request/response declarations and their reachable model graphs, but such runs remain degraded and do not establish semantic call paths, persistence behavior, integration behavior, or effective security.

## 10. Phase 2 - API Analyzer Agent and enriched OpenAPI

Status: In progress

- [x] **P2.1** Define structured domain, capability, endpoint, entity, attribute, enum, response, provenance, investigation, and enrichment-report contracts.
- [x] **P2.2** Build bounded code contexts from Phase 1 lineage plus repository-wide endpoint/model signals, with boundary checks, context limits, and likely-secret redaction.
- [x] **P2.3** Add an OpenAI Responses API provider with Pydantic Structured Outputs, a controlled insurance domain/capability taxonomy, strict structural-ID/response validation, connection preflight, bounded transient retries, and fail-fast permanent-error handling.
- [x] **P2.4** Generate OpenAPI 3.0 paths, parameters, request bodies, responses, schemas, types, enums, and validations from Phase 1 facts, enriched with the fixed `x-domain`, `x-capability`, `x-business-concept`, `x-business-purpose`, `x-source`, and `x-confidence` vocabulary.
- [x] **P2.5** Add one bounded low-confidence code-retrieval/re-analysis round, confidence bands, OpenAPI reparsing, coverage accounting, explicit gaps, and evidence mapping.
- [x] **P2.6** Add a gated Streamlit API Analyzer Agent with source-sharing acknowledgement, model selection, discovered-versus-enriched coverage metrics, live loop progress, actionable provider errors, previews, and individual or bundled downloads.
- [x] **P2.6a** Improve regional application intake with a guided region selector, clear application identity, separated source inputs, and a completed-run profile summary.
- [x] **P2.6b** Allow selection of a completed in-session application by region, application name, and repository ZIP; restore its exact Discovery/RAG inputs, show Phase 2 readiness requirements, and accept a session-only key override.
- [x] **P2.6e** Add a read-only regional catalog over completed in-session applications. Filter by region and either all APIs or one API; show endpoint contract-model mappings separately from API Analyzer domain/capability classifications without claiming Phase 6 canonical regional mappings.
- [x] **P2.6f** Present model mappings as an expandable Region → API → Model hierarchy, with request/response endpoint mappings and field details beneath every model.
- [x] **P2.6g** Present classifications as an expandable Region → Domain → Capability → API → Endpoint hierarchy, preserving unclassified/pending endpoints as explicit branches.
- [x] **P2.6h** Enrich regional entity, attribute, and endpoint views with API Analyzer summary, description, business concept or purpose, and confidence fields while keeping missing semantic values explicit.
- [x] **P2.6i** Allow an explicitly consented OpenAI Structured Outputs call to propose normalized names and descriptions for one regional entity and all its attributes. This per-entity UI was subsequently removed by P2.6t; region-wide normalization review remains available.
- [x] **P2.6j** Persist each trusted application run under an ignored local run-ID directory and allow users to reopen previous applications after restart with their repository ZIP, Discovery artifacts, RAG association, and Phase 2 artifacts restored together.
- [x] **P2.6k** Add an approved entire-region review workspace that supplies a bounded regional inventory for consistent AI terminology, batches entity normalization, captures per-entity and per-attribute original-versus-AI decisions and comments, merges duplicate approved entity names and duplicate approved field name/type pairs without changing source artifacts, preserves a complete truth map to source APIs/entities/fields/endpoints, and exports Excel and Mermaid artifacts.
- [x] **P2.6l** Enforce RAG as a mandatory API Analyzer input. Entity-relationship artifact generation is no longer part of Phase 2.
- [x] **P2.6m** Distinguish partial Analyzer coverage from a never-run Analyzer in the Regional catalog, and use unique endpoint-domain evidence for directly linked models when their entity call remains pending.
- [x] **P2.6n** Prevent obsolete duplicate runs from appearing as separate APIs in the Regional all-APIs trees and metrics; retain historical runs in the exact run selector.
- [x] **P2.6o** Expose saved per-application RAG readiness and selection directly in the Repository RAG and API Analyzer tabs so an existing valid index can be reused without rebuilding.
- [x] **P2.6p** Surface the active Discovery ingestion first in Repository RAG with explicit region, application identity, run ID, and current/RAG state.
- [x] **P2.6q** Show one selected-application journey across the first four implemented stages and represent ACORD ingestion/alignment as planned, gated work rather than active functionality.
- [x] **P2.7** Orchestrate provider preflight, context building, endpoint classification/enrichment, entity/attribute batching, enum enrichment, rendering, and validation with LangGraph.
- [x] **P2.7a** Ingest bounded redacted repository chunks into an ephemeral local Chroma index, retrieve target-specific evidence before semantic decisions, allow evidence-backed controller/module domains and action capabilities, emit one domain tag per operation, and resolve known Phase 1 CLR type names before marking a type unresolved.
- [x] **P2.7b** Establish production module boundaries for API Analyzer contracts, versioned prompts, provider adapters, and bounded tools while preserving the existing public workflow API.
- [x] **P2.7c** Separate Discovery Agent and API Analyzer implementation folders and enforce serialized `discovery-model.json` as their runtime handoff contract; retain temporary root-level compatibility imports.
- [x] **P2.7d** Document the architecture and LLM payload boundary; enforce tiktoken-based input estimation, per-request and per-run token ceilings, paid-request ceilings, output-token reservation, fail-closed budget stops, and usage reporting.
- [x] **P2.7e** Record input/output/total token usage for every LLM call and expose operator-configurable per-request and run ceilings. P2.7g later removed the UI ledger while retaining enforcement and machine-readable audit data.
- [x] **P2.7f** Enforce text-only system/user LLM messages, prohibit image inputs and generated image artifacts, and filter legacy image artifacts from persistence/UI. Its interim plain-text Mermaid output was later removed by P2.7g.
- [x] **P2.7g** Remove the LLM usage summary/table from Streamlit and remove entity-relationship source from Phase 2 generation, persistence, preview, download bundles, and required artifacts; retain internal token enforcement and report accounting.
- [x] **P2.7h** Resume partial analysis from validated semantic metadata: reuse completed endpoint/entity/enum IDs, analyze only unfinished targets with a fresh configured run budget, merge cumulative audit usage, preserve a separate full-restart action, and identify budget termination as `budget_exhausted`.
- [x] **P2.4a** Preserve described and sourced non-body parameters and OpenAPI 3 request bodies, identify response contract models explicitly, and emit deterministic structural descriptions for response ViewModels and fields when semantic enrichment is partial.
- [x] **P2.4b** Include component references and described direct attributes in each response-model extension while retaining standard OpenAPI response `$ref` schemas.
- [x] **P2.4g** Include component references and described direct attributes in each request-model extension while retaining the standard request-body `$ref` schema and complete `components.schemas` definition.
- [ ] **P2.8** Complete live-model acceptance against an approved real repository and manually review semantic accuracy.

Acceptance criteria:

- Roslyn/Phase 1 remains authoritative for endpoints, fields, types, routes, responses, and validations; the LLM cannot add or rename structural elements.
- Only bounded, relevant, redacted source snippets are sent to OpenAI after explicit operator acknowledgement.
- Every endpoint has domain, capability, summary, description, business purpose, source traceability, and confidence in the enriched OpenAPI.
- Every entity, attribute, and enum has a description, business concept, source traceability, and confidence in the enriched OpenAPI.
- Domain and capability prefer the controlled insurance taxonomy when evidence supports it. Technical or administrative APIs use concise repository-derived controller/module domains and action/business capabilities; `UNCLASSIFIED` with a suggestion is reserved for genuinely unsupported cases.
- The fixed semantic extension vocabulary is `x-domain`, `x-capability`, `x-business-concept`, `x-business-purpose`, `x-source`, and `x-confidence`.
- No `x-acord-*` fields or ACORD conclusions are generated during Phase 2.
- Every semantic description retains its model, confidence, inference classification, and source evidence mapping.
- Entity attributes are analyzed in one entity-level batch rather than one model call per attribute.
- `enriched-openapi.yaml`, `semantic-metadata.json`, `evidence-map.json`, and `enrichment-report.json` are generated even for partial runs where possible.
- The generated OpenAPI reparses successfully and reports no missing Phase 1 operations before Phase 2 is accepted.
- Confidence of at least 0.90 is an auto-accept candidate, 0.70-0.89 requires review, and below 0.70 triggers one bounded code-context investigation before remaining an explicit gap.
- Low-confidence, missing-context, provider, and validation gaps remain explicit and require human review.
- Repository retrieval uses a bounded, redacted, local Chroma index; only selected retrieved snippets enter model context, and the index is removed at the end of the run.
- Each operation has exactly one OpenAPI tag equal to its chosen domain, and known Phase 1 model names resolve to component references before `x-unresolved-clr-type` is emitted.
- The enriched OpenAPI is the normal repository-independent input to Phase 3 ACORD alignment.
- A live run against an approved repository confirms semantic accuracy and acceptable source-sharing policy.
