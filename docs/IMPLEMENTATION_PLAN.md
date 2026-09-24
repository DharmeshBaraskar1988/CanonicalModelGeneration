# Canonical Model Generator - Implementation Plan

Last updated: 2026-09-24  
Current release: Phase 2 API Analyzer Agent  
Overall status: In progress

## 1. Objective

Build a deterministic discovery workflow that analyzes one regional insurance .NET Web API and its OpenAPI specification, normalizes both sources into a versioned `DiscoveryModel`, validates the result, and generates traceable discovery artifacts.

The Discovery MVP is the foundation for later classification, regional alignment, and canonical-model generation. Those later capabilities are deliberately outside this release.

## 2. Target workflow

```text
.NET repository -> Roslyn analyzer ----+
                                        +-> Normalize -> Reconcile -> Validate -> Artifacts
OpenAPI spec ---> OpenAPI parser -------+
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

Acceptance criteria:

- All expected Quote endpoints are identified.
- Endpoint-linked ViewModel request and response types resolve correctly.
- Expected endpoint contract fields, referenced enums, validations, and endpoint/nested relationships are captured; base infrastructure classes, DTOs, and other model categories are intentionally excluded.
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
3. **ACORD alignment — Not started:** compare the enriched regional contract with approved ACORD references.
4. **Canonicalization — Not started:** propose the common canonical model.
5. **Review and versioning — Not started:** approve and govern canonical versions.
6. **Regional mapping — Not started:** maintain region-to-canonical mappings.
7. **Change impact — Not started:** assess future regional and canonical changes.

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

The Roslyn analyzer recognizes public conventional MVC actions in addition to attribute-routed API actions. When explicit routing metadata is absent it derives a deterministic controller/action route. The accepted Phase 1 output retains user-authored concrete `*ViewModel`, `*Request`, and `*Response` classes directly used by endpoints or reachable through retained contract-model properties/inheritance. `Base*` infrastructure classes, DTOs, domain models, generated types, and unrelated models are removed with their dangling evidence and relationships. The API Catalog expands both request and response model trees.

Uploaded repositories are explored across all non-test projects that own controller files. Their Roslyn models are aggregated deterministically before optional OpenAPI reconciliation, and the UI lists every analyzed project rather than representing one selected project as the repository result.

When compilation dependencies are unresolved, endpoint inventory falls back to syntax evidence for controller actions, attributed endpoint-base actions, and Minimal API route registrations. Such runs remain degraded; syntax fallback does not establish semantic call paths, model mappings, persistence behavior, integration behavior, or effective security.

## 10. Phase 2 - API Analyzer Agent and enriched OpenAPI

Status: In progress

- [x] **P2.1** Define structured domain, capability, endpoint, entity, attribute, enum, response, provenance, investigation, and enrichment-report contracts.
- [x] **P2.2** Build bounded code contexts from Phase 1 lineage plus repository-wide endpoint/model signals, with boundary checks, context limits, and likely-secret redaction.
- [x] **P2.3** Add an OpenAI Responses API provider with Pydantic Structured Outputs, a controlled insurance domain/capability taxonomy, strict structural-ID/response validation, connection preflight, bounded transient retries, and fail-fast permanent-error handling.
- [x] **P2.4** Generate OpenAPI 3.0 paths, parameters, request bodies, responses, schemas, types, enums, and validations from Phase 1 facts, enriched with the fixed `x-domain`, `x-capability`, `x-business-concept`, `x-business-purpose`, `x-source`, and `x-confidence` vocabulary.
- [x] **P2.5** Add one bounded low-confidence code-retrieval/re-analysis round, confidence bands, OpenAPI reparsing, coverage accounting, explicit gaps, and evidence mapping.
- [x] **P2.6** Add a gated Streamlit API Analyzer Agent with source-sharing acknowledgement, model selection, discovered-versus-enriched coverage metrics, live loop progress, actionable provider errors, previews, and individual or bundled downloads.
- [x] **P2.7** Orchestrate provider preflight, context building, endpoint classification/enrichment, entity/attribute batching, enum enrichment, rendering, and validation with LangGraph.
- [x] **P2.7a** Ingest bounded redacted repository chunks into an ephemeral local Chroma index, retrieve target-specific evidence before semantic decisions, allow evidence-backed controller/module domains and action capabilities, emit one domain tag per operation, and resolve known Phase 1 CLR type names before marking a type unresolved.
- [x] **P2.4a** Preserve described and sourced non-body parameters and OpenAPI 3 request bodies, identify response contract models explicitly, and emit deterministic structural descriptions for response ViewModels and fields when semantic enrichment is partial.
- [x] **P2.4b** Include component references and described direct attributes in each response-model extension while retaining standard OpenAPI response `$ref` schemas.
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
