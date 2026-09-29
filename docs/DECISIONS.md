# Architecture Decision Log

This file records durable decisions. Do not use it as a general activity log.

## ADR-001 - Discovery before canonicalization

- Date: 2026-09-23
- Status: Accepted

### Context

Reliable canonical-model generation depends on complete, traceable regional API discovery.

### Decision

Deliver a Discovery MVP before adding classification, alignment, or canonical generation. Start with one region and one Quote API.

### Consequences

- The first release contains no LLM calls.
- Discovery quality can be measured independently.
- Canonical-model work is gated on Discovery MVP acceptance.

## ADR-002 - Deterministic tools with LangGraph orchestration

- Date: 2026-09-23
- Status: Accepted

### Context

Source code and OpenAPI structures can be extracted more reliably with parsers than with an LLM.

### Decision

Use Roslyn for .NET analysis, an OpenAPI parser for specifications, and LangGraph only to orchestrate the workflow and state transitions.

### Consequences

- Parsing, normalization, validation, and artifact generation remain normal services.
- Agentic reasoning can be introduced later at the semantic classification and alignment boundary.

## ADR-003 - One shared versioned discovery contract

- Date: 2026-09-23
- Status: Accepted

### Context

Separate source-specific downstream models would complicate reconciliation and evolution.

### Decision

Roslyn and OpenAPI discovery both emit evidence compatible with a versioned DiscoveryModel contract. Source-specific detail is retained through evidence and lineage.

### Consequences

- The contract must represent conflicts and partial evidence.
- Contract fixtures and JSON Schema precede parser implementation.

## ADR-004 - Preserve conflicts and lineage

- Date: 2026-09-23
- Status: Accepted

### Context

OpenAPI and implementation details may disagree, and canonical governance requires traceability.

### Decision

Never silently overwrite conflicting source observations. Preserve both, attach lineage, and emit diagnostics.

### Consequences

- Reconciliation output is auditable.
- Consumers must account for warnings and conflicts.

## ADR-005 - Permit an intake-only UI before Discovery MVP acceptance

- Date: 2026-09-23
- Status: Accepted

### Context

Repository and OpenAPI inputs need a simple operator-facing upload surface, while the implementation plan defers the discovery review and approval UI until after the deterministic pipeline is accepted.

### Decision

Permit a narrow Streamlit intake page during M0. It may collect metadata, inspect uploaded files without extracting or executing them, report readiness, and export a deterministic intake manifest. It must not simulate DiscoveryModel generation, semantic classification, canonicalization, or approval workflows.

### Consequences

- Operators can prepare a real repository input before M1-M6 are complete.
- The page explicitly reports that full discovery is not implemented yet.
- Discovery results and review workflows remain gated by their planned milestones.

## ADR-006 - Keep discovery branches sequential for the MVP

- Date: 2026-09-24
- Status: Accepted

### Context

Roslyn and OpenAPI discovery are independent, but the fixture run is short and MSBuild project loading has process and execution implications.

### Decision

Keep the M5 graph sequential for the Discovery MVP. Reconsider parallel branches only after real-repository profiling demonstrates material benefit and isolated sidecar execution is established.

### Consequences

- Node order and structured logs remain simple and deterministic.
- The MVP does not claim parallel execution.

## ADR-007 - Accept the fixture-based Discovery MVP

- Date: 2026-09-24
- Status: Accepted

### Context

Milestones M0-M7 are complete, the deterministic fixture workflow passes automated and manual acceptance, and all generated artifacts are schema-valid and byte-stable.

### Decision

Accept the Discovery MVP for the supported ASP.NET Core controller and local OpenAPI 3 scope. Treat the documented limitations and the required real-repository production-readiness run as explicit follow-up work.

### Consequences

- Classification and alignment planning may begin under the release gate, but are not part of this implementation.
- The current MVP must not be represented as supporting minimal APIs, classic ASP.NET Web API, external OpenAPI references, or semantic call graphs.

## ADR-008 - Adopt a seven-phase platform roadmap

- Date: 2026-09-24
- Status: Superseded by ADR-014

### Context

The accepted Discovery MVP is only the foundation for a multi-region Insurance Canonical Model platform. Source reconciliation inside discovery must not be confused with future cross-region normalization.

### Decision

Organize the platform into seven phases: Discovery, cross-region Normalization, Classification, Alignment, Canonicalization, Review and Versioning, and Mapping and Impact. Treat the completed M0-M7 release as Platform Phase 1. Keep Phase 2 architecturally separate even when a future LangGraph workflow invokes it after discovery.

### Consequences

- The UI displays Phase 1 as complete and Phases 2-7 as not started.
- Phase 1 source normalization remains deterministic evidence reconciliation only.
- Classification and alignment agents cannot substitute for the missing Phase 2 contract and service.

## ADR-009 - Gate Phase 2 UI on Phase 1 acceptance

- Date: 2026-09-24
- Status: Superseded by ADR-013

### Context

Operators need to inspect the accepted Discovery result before moving into cross-region normalization, while the UI must not imply that an unlocked future phase is already implemented.

### Decision

Show Phase 1 results and Phase 2 normalization as separate Streamlit tabs. Enable the continuation control only for an accepted Phase 1 result. Unlocking Phase 2 starts its planning state and does not change the implementation status of its contract or service.

### Consequences

- The UI provides a clear transition from accepted discovery to normalization planning.
- Phase 2 remains visibly unimplemented until its own acceptance criteria are defined and verified.
- The unlock state is session-scoped and resets when the browser session ends.

## ADR-010 - Permit trusted repository execution in the local Discovery UI

- Date: 2026-09-24
- Status: Accepted

### Context

The operator explicitly wants artifact results generated from the repository uploaded in the Discovery Agent tab, rather than fixture-backed results or an intake manifest.

### Decision

Treat repositories uploaded to this local application as trusted code. Extract each validated ZIP into an ephemeral directory, run the deterministic Roslyn/OpenAPI Discovery workflow, retain the five derived JSON artifacts in Streamlit session state, and delete the extracted workspace after the run.

### Consequences

- Uploaded project evaluation may execute MSBuild behavior and must only be used with trusted repositories.
- Artifact results always belong to the current successful upload and are cleared when a new run starts.
- Production or untrusted uploads still require an isolated execution boundary.
- The internal DiscoveryModel is validated and generated but is not displayed as one of the five operator-facing artifacts.

## ADR-011 - Allow a Roslyn-only repository fallback

- Date: 2026-09-24
- Status: Accepted

### Context

Some trusted repository uploads do not include an OpenAPI document, but operators still need discovery results from the implementation evidence that is available.

### Decision

Allow the local Discovery Agent to generate its five operator artifacts from Roslyn evidence alone when OpenAPI is absent. Continue to use the full Roslyn/OpenAPI reconciliation path whenever an OpenAPI document is uploaded or detected.

### Consequences

- Repository-only discovery no longer fails because OpenAPI is missing.
- Roslyn-only artifacts cannot report specification/implementation conflicts or OpenAPI pointer lineage.
- The accepted full-evidence Discovery path remains Roslyn plus OpenAPI.

## ADR-012 - Keep Phase 2 deterministic and source-preserving

- Date: 2026-09-24
- Status: Superseded by ADR-013

### Context

Cross-region inputs use different naming, routing, and type conventions, but deciding whether concepts mean the same thing belongs to the later alignment phase.

### Decision

Phase 2 accepts one or more validated Phase 1 DiscoveryModels and produces a versioned technical-normalization portfolio. It deterministically standardizes identifiers, routes, methods, types, constraints, and relationships while retaining original source names and readable lineage. It performs no classification, semantic matching, or canonical-model proposal.

### Consequences

- Multiple regional systems can be compared using a consistent technical representation.
- Phase 4 remains responsible for full, partial, new, and conflicting semantic matches.
- The first UI slice normalizes the current Phase 1 result; multi-region portfolio intake remains a separate Phase 2 task.

## ADR-013 - Make Phase 2 evidence-grounded semantic OpenAPI generation

- Date: 2026-09-24
- Status: Amended by ADR-014

### Context

The immediate product need is a detailed OpenAPI specification containing meaningful endpoint, entity, and attribute descriptions derived from the implementation. Cross-region technical normalization is not currently required. Phase 1 already provides structural facts and source lineage, while business meaning requires constrained semantic interpretation of relevant code.

### Decision

Replace Phase 2 cross-region normalization with Semantic OpenAPI Enrichment and Generation. Treat Phase 1 as the sole authority for structural elements. Build bounded, repository-scoped, redacted code contexts from Phase 1 lineage and send them to an OpenAI model only after explicit operator acknowledgement. Require Pydantic Structured Outputs, exact structural-ID preservation, confidence, inference classification, source evidence mapping, OpenAPI validation, and explicit partial-run gaps. Analyze all attributes of an entity in one request. Generate `enriched-openapi.yaml`, `semantic-metadata.json`, `evidence-map.json`, and `enrichment-report.json`.

### Consequences

- Technical normalization is deferred and removed from the active UI, but its existing inactive module is retained for possible later reuse.
- LLM output may explain discovered contracts but cannot create endpoints, fields, types, routes, responses, or validations.
- Repository source is external data and cannot change prompts or tool policy; likely secrets are redacted before submission.
- Semantic descriptions remain inferred, evidence-linked, confidence-scored, and subject to human review.
- Missing call paths, persistence, integrations, and security context remain visible gaps until deterministic discovery supports them.
- Phase 2 is not accepted until a live run against an approved repository is manually reviewed.

## ADR-014 - Make Phase 2 the API Analyzer and Phase 3 ACORD alignment

- Date: 2026-09-24
- Status: Accepted

### Context

Later ACORD alignment needs one repository-independent regional contract containing domain, capability, endpoint semantics, entity semantics, attribute semantics, enum meaning, technical structure, evidence, and confidence. The earlier Phase 2 output did not embed domain and capability in OpenAPI and did not investigate low-confidence endpoint context.

### Decision

Name Phase 2 the API Analyzer Agent. It must use a controlled insurance domain/capability taxonomy, permit `UNCLASSIFIED` with a suggestion, and enrich the Phase 1 structure through schema-validated OpenAI analysis. Deterministic code merges semantic results into one self-contained `enriched-openapi.yaml` using only `x-domain`, `x-capability`, `x-business-concept`, `x-business-purpose`, `x-source`, and `x-confidence` for semantic extensions. Domain, capability, and endpoint confidence below 0.70 trigger at most one bounded repository symbol-context retrieval and re-analysis. Values from 0.70 through 0.89 require review; values of at least 0.90 are auto-accept candidates, not final approvals. Phase 3 is ACORD alignment and normally consumes the enriched OpenAPI without re-analyzing the repository.

### Consequences

- Phase 2 owns insurance domain/capability classification and all regional semantic enrichment.
- Phase 2 generates no `x-acord-*` fields and makes no ACORD mapping claims.
- Phase 3 ACORD alignment is deferred until the enriched OpenAPI contract is accepted.
- Phase 1 remains authoritative for all structural API facts, including response codes.
- A low-confidence retry can retrieve additional code only inside the uploaded repository, with path bounds, redaction, size limits, and one investigation round.
- Provider credentials and model access are validated once before item analysis. Permanent authentication, permission, or model errors stop the loop and become one explicit partial-run issue; transient provider failures use bounded SDK retries.
- The seven phases are Discovery, API Analyzer, ACORD Alignment, Canonicalization, Review/Versioning, Regional Mapping, and Change Impact.

## ADR-015 - Use local Chroma retrieval and repository-derived technical classification

- Date: 2026-09-24
- Status: Accepted

### Context

Lineage windows alone can omit service implementations, views, authorization configuration, and other repository evidence needed for useful domain, capability, and description decisions. A closed insurance-only taxonomy also forces unrelated technical endpoints into `UNCLASSIFIED`, while Phase 1 may already contain enough model information to resolve CLR names used by generated schemas.

### Decision

For each Phase 2 run, ingest bounded redacted repository chunks into an ephemeral local Chroma collection using deterministic local embeddings. Retrieve target-specific chunks before analyzing every endpoint, entity, and enum, and use Chroma again for a bounded low-confidence follow-up. Continue to prefer the controlled insurance taxonomy when evidence supports it, but allow concise repository-derived controller/module domains and action/business capabilities for technical APIs. Emit exactly one operation tag equal to the selected domain. Resolve CLR type names against Phase 1 entities and enums before emitting `x-unresolved-clr-type`.

### Consequences

- The vector index and embeddings remain local and are removed after the uploaded-repository run; only selected redacted chunks are eligible for model context.
- Retrieval is bounded by file size, file count, chunk count, result count, and context characters, and exclusions cover build, vendor, environment, and secret-store paths.
- Chroma improves evidence recall but does not make retrieved prose authoritative; Phase 1 remains the source of structural truth.
- `UNCLASSIFIED` remains available only when neither the taxonomy nor repository evidence supports a defensible domain or capability.
- Generated operations expose one consistent tag that matches `x-domain`.

## ADR-016 - Limit Phase 1 entities to endpoint ViewModels

- Date: 2026-09-24
- Status: Superseded by ADR-017

### Context

The broad Phase 1 model treated request/response DTOs, domain classes, and other source types as entities. The required product boundary is narrower: an entity represents a user-facing ViewModel used by an API endpoint, and operator artifacts should not contain unrelated DTOs or generated framework/build types.

### Decision

After deterministic extraction and reconciliation, retain only user-authored class names ending in `ViewModel` that are directly referenced by an endpoint request, response, or parameter. Recursively retain referenced/base `*ViewModel` types. Require Roslyn source lineage outside `bin`/`obj` and exclude `.g.cs`, `.generated.cs`, and `.designer.cs` definitions. Keep enums and validations only when retained ViewModels use them. Preserve direct endpoint `ACCEPTS`/`RETURNS`, ViewModel-to-attribute, nested ViewModel `CONTAINS`, and inheritance relationships, then prune all dangling references, evidence, lineage, and unused sources.

### Consequences

- DTOs, domain entities, OpenAPI-only schemas, generated types, and unrelated ViewModels no longer appear as Phase 1 entities.
- An endpoint without a qualifying ViewModel remains in the API Catalog but has no entity relationship.
- Nested ViewModels remain connected transitively to the endpoint through the root ViewModel.
- The Quote fixture now intentionally has zero entities because its models do not use the `ViewModel` suffix.
- Phase 2 enriches only the ViewModels admitted by this Phase 1 boundary, while Chroma may still retrieve other repository files as supporting semantic evidence.

## ADR-017 - Include concrete endpoint request and response contracts

- Date: 2026-09-24
- Status: Accepted

### Context

The ViewModel-only boundary omitted concrete API request and response contracts, while broad name-based discovery previously exposed messaging infrastructure such as `BaseMessage`, `BaseRequest`, and `BaseResponse` alongside unrelated DTOs.

### Decision

Retain only user-authored, endpoint-reachable classes ending in `ViewModel`, `Request`, or `Response`. Exclude names beginning with `Base`, generated/build output, DTOs, domain types, and unrelated models. Recursively retain only nested or inherited types that satisfy the same contract-name rule. Show bounded, cycle-safe request and response model trees in the API Catalog and the same retained contracts in the Data Model.

### Consequences

- Concrete endpoint requests and responses appear in both operator artifacts.
- Infrastructure bases such as `BaseMessage`, `BaseRequest`, and `BaseResponse` do not appear or become inherited model nodes.
- DTOs can remain visible only as unresolved field type text when a retained contract declares such a property; they are not emitted as Data Model entities.
- Roslyn source lineage remains mandatory, preventing external .NET/library classes from becoming entities.

## ADR-018 - Separate agent packages with an artifact-only handoff

- Date: 2026-09-25
- Status: Accepted

### Context

Phase 1 Discovery and Phase 2 API Analyzer had different responsibilities, but Discovery modules
were located at the package root and the analyzer entry point accepted an in-memory DiscoveryModel.
This obscured the agent boundary and allowed callers to couple the workflows through Python state.

### Decision

Place deterministic Phase 1 implementation in `discovery_agent/` and semantic Phase 2 implementation
in `api_analyzer/`. The only runtime handoff is serialized `discovery-model.json` content (bytes, a
file path, or its decoded mapping). Phase 2 validates that artifact before constructing its private
graph state. Keep thin root-level imports temporarily for source compatibility; they are not agent
handoff APIs.

### Consequences

- The two agents are visible as separate production folders with independent workflows.
- Phase 2 cannot receive Phase 1 LangGraph state or a live DiscoveryModel instance through its public
  entry point.
- Artifact validation detects an invalid handoff before semantic analysis or provider calls.
- Compatibility imports can be removed in a future breaking release after downstream callers migrate.

## ADR-019 - Repository or specification intake and reusable hierarchical RAG

- Date: 2026-09-26
- Status: Superseded by ADR-025; amends ADR-015 and ADR-018

### Context

Operators may have a .NET repository, an OpenAPI document, or both. Fixed line windows and hashed
vectors do not provide the requested code hierarchy or semantic embeddings, and an ephemeral
index cannot be inspected and reused independently of semantic generation.

### Decision

Allow either discovery input independently. Repository discovery keeps the accepted endpoint
contract scope; specification-only discovery preserves the document's schemas without requiring
Roslyn lineage. Missing implementation evidence remains explicit in specification-only enrichment.

Create `repository_rag/` as a service separate from both agents. Parse bounded redacted C# text
with a syntax-only Roslyn sidecar, producing file/type/member/top-level chunks and bounded child
windows. Preserve source hashes, relative spans, parent-child links, DiscoveryModel relationships,
and name-based call/reference/inheritance candidates. Candidate links are not semantic call paths;
ambiguous matches and unresolved references remain recorded.

Use selectable local Sentence Transformer embeddings or OpenAI embeddings (including requested
`text-embedding-ada-002`). Cloud embedding requires explicit acknowledgement for all included
redacted chunks. Local MiniLM uses a pinned model revision and pooled token windows. Never silently
fall back to hash vectors. Store each snapshot/profile in local Chroma with a versioned manifest.

Retrieve exact subject lineage first, then combine identifier lexical ranking and vector ranking,
and expand bounded parent/relationship context. Preserve separate fully qualified symbols and
overload parameter lists. Analyzer reuse requires source hash and discovery artifact agreement.

### Consequences

- Persistent indexes live under ignored `.rag/` in the UI; users can reopen them with the same inputs
  or use the standalone CLI. A downloaded manifest alone does not include the Chroma database.
- Discovery remains deterministic; embeddings run as a distinct explicit RAG action.
- Source-only uploads can build a syntax index independently; DiscoveryModel enables exact target
  selectors and ID bindings when available.
- API Analyzer continues to receive serialized artifacts: DiscoveryModel plus an optional local
  index artifact reference. No agent graph state is exchanged.
- Syntax references include unresolved/external names and cannot prove runtime dispatch, persistence
  behavior, security, or business semantics. Deep semantic extraction remains deferred.
- User-requested RAG work takes priority over P2.8 live semantic acceptance.

## ADR-020 - Explain selected retrieval targets with grounded semantics

- Date: 2026-09-26
- Status: Accepted

### Context

Code retrieval finds relevant source but does not itself explain a contract model, attribute or
endpoint. Operators need to inspect one selected target's meaning before running the full API
Analyzer, while keeping code observations and inferred business descriptions distinct.

### Decision

Add focused semantic inspection to the API Analyzer. It accepts the serialized DiscoveryModel,
an exact target ID, the saved RAG index and the existing provider contract. It builds bounded
context from exact lineage and related chunks, then uses the same schema-validated endpoint,
entity-batch or enum analysis as the full agent. An attribute inspection validates the entire
owning entity result and returns the chosen field's meaning. Results include confidence,
source spans and gaps; a target without an exact source binding remains unknown. The UI invokes
this only after an explicit source-sharing acknowledgement.
For a free code query without a DiscoveryModel target, use a separate structured code-analysis
contract. Ground every observed or inferred claim in a retrieved chunk ID and reject citations
outside the context; keep unknown claims and gaps explicit.

### Consequences

- Embedding similarity ranks code; it does not count as a semantic conclusion.
- Semantic descriptions remain inferred and human-reviewable. Cited snippets are context
  considered by the provider, not proof of every sentence in its response.
- The provider cannot add or rename structural endpoints or fields during focused inspection.
- Live interpretation depends on a working OpenAI API key. Offline behavior is fixture-tested
  through the provider port.

## ADR-021 - Select matching application inputs for Phase 2 within a browser session

- Date: 2026-09-27
- Status: Accepted

### Context

Running Discovery and Repository RAG did not make the selected region, application, repository
archive, and saved index explicit at the API Analyzer boundary. A single active session result
could also be replaced by the next Discovery run, leaving users unsure which repository Phase 2
would analyze.

### Decision

Keep completed application profiles separate in Streamlit session state. Identify each profile
by its validated Discovery artifact and repository bytes; show region, application name, and ZIP
name in the Phase 2 selector. Restore that profile's serialized Discovery artifact, repository
archive, RAG path, and Phase 2 outputs together. Rebuild/reopen of its RAG index invalidates its
previous Phase 2 output. Require an index for repository-based UI enrichment, show all missing
run requirements, and allow a password-masked API key override held only in the session.

### Consequences

- The UI cannot silently use another selected repository's RAG path or Discovery artifact.
- Uploaded ZIP bytes remain session-only; this change does not create a persistent repository
  registry. A browser-session or server restart requires rerunning Discovery and reopening the
  saved index with the same ZIP.
- Presence of an API key only enables a run. Provider access and semantic accuracy still require
  preflight and approved live review.

## ADR-022 - Present a read-only regional API catalog before regional canonical mapping

- Date: 2026-09-27
- Status: Accepted

### Context

Operators need to inspect all Claim, Quote, and other APIs in one region, or focus on one API, while comparing endpoint contract models and API Analyzer domain/capability results. Platform Phase 6 regional-to-canonical mapping is not implemented.

### Decision

Add a read-only Streamlit regional catalog backed only by completed in-session application profiles. Provide a region selector, an all-APIs or single-API selector, an expandable Region → API → Model tree for deterministic endpoint-contract links and fields, and an expandable Region → Domain → Capability → API → Endpoint tree for Phase 2 classifications. Include the available API Analyzer descriptions, business concepts or purposes, and confidence values on entity, field, and endpoint nodes. Label missing classifications or descriptions as awaiting API Analyzer output and do not infer or present canonical mappings.

### Consequences

- Multiple applications in EU, US, or a custom region can be compared without merging their source artifacts.
- Discovery remains the authority for endpoints and contract mappings; API Analyzer artifacts remain the authority for domain and capability.
- The page does not satisfy or pre-implement Phase 6 regional-to-canonical mapping.

## ADR-023 - Keep single-API normalization as a review-only proposal

- Date: 2026-09-27
- Status: Accepted

### Context

Operators want clearer, normalized entity and attribute names and descriptions before the later cross-API comparison and canonicalization work. LLM proposals must not overwrite deterministic source structure or be mistaken for approved canonical mappings.

### Decision

Allow one explicitly consented Structured Outputs call per selected entity on the Regional catalog page. Send only that regional entity, its complete attribute structure, and available API Analyzer semantics. Require the response to preserve every entity and attribute ID and original name. Store valid proposals only in Streamlit session state and display normalized names, descriptions, and confidence beside the originals. Do not mutate Discovery, enriched OpenAPI, or saved artifacts, and do not compare APIs in this step.

### Consequences

- Operators can review clearer regional terminology without changing structural truth.
- A malformed response that adds, removes, or remaps an attribute is rejected.
- Proposals disappear with the browser session and are not approvals.
- Cross-API comparison and canonical matching remain separate later work.

## ADR-024 - Persist trusted application history locally

- Date: 2026-09-27
- Status: Accepted; amends ADR-021

### Context

Session-only profiles prevent operators from returning to a previously analyzed repository after a browser or Streamlit restart. Re-uploading and rerunning Discovery also loses the convenient association between the repository, its artifacts, its RAG index, and Phase 2 output.

### Decision

Persist each trusted application profile under `.applications/<run-id>/`, which remains ignored by source control. Store the original trusted repository ZIP when supplied, the validated Discovery artifact and five presentation artifacts, profile and project metadata, the associated RAG path/manifest, and Phase 2 artifacts/errors. Load valid records at startup and expose an explicit previous-application selector. Keep runs isolated by UUID and ignore incomplete or invalid record directories.

### Consequences

- Users can resume work on earlier repositories without re-uploading them.
- Repository source is now intentionally retained on local disk instead of only in browser session memory; operators must protect or remove `.applications/` according to their data-handling policy.
- Removing `.applications/<run-id>/` removes that history record but does not automatically remove a separately stored `.rag/` index.
- API keys and source-sharing consent are never persisted.

## ADR-025 - Require a repository in Phase 1

- Date: 2026-09-28
- Status: Accepted; supersedes the independent specification-only intake in ADR-019

### Context

Phase 1 must discover an application from its implementation repository. An OpenAPI YAML/JSON
document can strengthen and reconcile that evidence, but a specification by itself does not meet
the required Phase 1 application-discovery boundary.

### Decision

Require a trusted .NET repository and selected project for every Phase 1 Discovery run. Accept an
OpenAPI 3 YAML/JSON document only as optional evidence to reconcile with the repository result.
Enforce this boundary in the Discovery graph, command-line interface, and Streamlit intake.

### Consequences

- Repository-only Discovery remains supported.
- Repository plus OpenAPI remains the fullest deterministic evidence path.
- New specification-only Discovery runs are rejected before extraction or artifact generation.
- The API Analyzer may retain defensive handling for older serialized specification-only artifacts,
  but the active Phase 1 workflow no longer creates them.

## ADR-026 - Make regional deduplication an explicit approved review artifact

- Date: 2026-09-28
- Status: Accepted; extends ADR-022 and ADR-023

### Context

Operators need one region-wide view that removes duplicate entity and attribute presentations while
retaining proof of which APIs and endpoints supplied every item. Per-entity AI normalization alone
does not provide an approval workflow or a lossless explanation of a regional merge.

### Decision

Add a region-wide review workspace over all completed applications in the selected region. Bulk
normalization supplies a bounded inventory of regional entity names and field names/types so AI can
propose consistent terminology without asserting duplicate truth. A reviewer chooses the original or suggestion independently for
each entity and attribute and may add a comment. Approval creates a separate regional review
artifact. Entities merge only on the reviewer-approved normalized name; attributes within that
entity merge only on reviewer-approved name plus source type. The output retains source-to-regional
truth rows for every entity and attribute, all involved APIs and endpoint mappings, reviewer choices,
comments, and explicit retained-versus-merged actions. Export the approved result as Excel and its
lineage as Mermaid. Do not mutate or delete Discovery or API Analyzer facts.

### Consequences

- "Removed duplicate" means absent from the approved regional presentation, not deleted from a
  source application or artifact.
- Similar concepts with different approved names remain separate; same-name fields with different
  source types remain separate to avoid a silent type conflict.
- The regional review is human-approved and auditable, but it is not an ACORD mapping or the final
  enterprise canonical model.
- Re-approval regenerates downloads from the current decisions; source truth remains available in
  the workbook and Mermaid graph.

## ADR-027 - Require RAG and publish entity-relationship artifacts in API Analyzer

- Date: 2026-09-28
- Status: Accepted; strengthens ADR-019 and ADR-021

### Context

Allowing programmatic API Analyzer callers to omit the saved repository index made evidence
retrieval optional outside the Streamlit readiness checks. Operators also need the discovered
contract-model relationships as both a visible diagram and portable artifacts.

### Decision

Require repository source plus a saved, manifest-backed, snapshot-matched RAG index at the public
API Analyzer boundary. Reject specification-only and implicit ephemeral-index analysis. During
artifact rendering, generate an ER diagram from deterministic Discovery entities, attributes,
containment, and inheritance as Mermaid source and SVG. Render the Mermaid source in the API
Analyzer tab and include both formats in individual downloads and the Phase 2 bundle.

### Consequences

- Every accepted semantic run uses the same validated retrieval prerequisite, regardless of caller.
- Older specification-only Discovery artifacts remain readable but cannot enter Phase 2 analysis.
- Diagram structure is deterministic Discovery truth; provider descriptions do not change nodes or
  edges.
- SVG is generated locally and does not require a browser-side export or external rendering service.

## ADR-028 - Enforce token budgets before paid semantic calls

- Date: 2026-09-28
- Status: Accepted; extends ADR-014 and ADR-027

### Context

Bounded source characters do not directly bound model tokens or total paid usage. A large
application can require endpoint, entity, enum, and investigation calls, and SDK retries can add
cost. Operators need a deterministic ceiling that stops spending before a run exhausts credits,
while retaining any useful results already produced.

### Decision

Count each semantic request's system prompt and serialized JSON context with `tiktoken` before it is
sent. Enforce configurable maximum tokens and requests per run, fixed per-request input and output
ceilings, and reserve the full output allowance when projecting the next request. Pass the output
ceiling to the Responses API. When a ceiling would be exceeded, reject the call locally, stop the
current analysis loop, record an explicit validation gap, and render partial artifacts. Capture
provider-reported input/output usage and structured-result counts in the enrichment report and UI.

### Consequences

- No semantic request begins when its projected token usage would exceed an operator-visible limit.
- Completed semantic results remain available if a later target exhausts the budget.
- Token ceilings are stable controls but are not currency estimates; model pricing remains external.
- Retry behavior remains bounded by the OpenAI client, while request and token reporting cover
  completed Responses API calls visible to the adapter.

## ADR-029 - Scope discovery models by endpoint reachability, not naming suffix

- Date: 2026-09-28
- Status: Accepted; supersedes ADR-016 and ADR-017 model-name restrictions

### Context

Real ASP.NET Core endpoints commonly use DTOs and domain-shaped models whose names do not end in
`ViewModel`, `Request`, or `Response`. For example, a controller can accept `ClaimDto` and return
`InsuranceClaim`. Suffix filtering therefore removed models that are part of the actual HTTP API
contract and also removed their nested child models.

### Decision

Start the retained model graph from user-authored request types, response types, and model-valued
endpoint parameters discovered by Roslyn. Recursively retain user-authored source types referenced
by properties (including collection element types) and inheritance, regardless of class-name suffix.
Continue to exclude generated/build-output types and models that are not reachable from an endpoint.
Preserve endpoint, containment, inheritance, evidence, and source-lineage relationships.

### Consequences

- DTOs and domain models used by an endpoint are first-class Discovery entities.
- Nested and collection child models appear in the Data Model, API Catalog trees, enriched OpenAPI,
  and ER artifacts.
- Unrelated repository classes remain outside the Discovery contract.
- A broadly shared base model is retained when an endpoint-reachable model actually inherits it.

## ADR-030 - Keep API Analyzer provider input and artifacts text-only

- Date: 2026-09-28
- Status: Accepted; amends ADR-027

### Context

The API Analyzer semantic contract needs only structured Discovery facts and bounded source text.
An SVG relationship artifact and browser-rendered Mermaid views added an image surface that is not
required for model reasoning or the machine-readable Phase 2 handoff.

### Decision

Send semantic providers only system and user string messages containing prompts and serialized JSON
context. Do not send images, image URLs, or binary content. Do not generate or render image artifacts
in Phase 2. Retain the deterministic entity-relationship `.mmd` artifact strictly as plain UTF-8
source, and filter legacy image artifacts when loading or presenting saved application records.

### Consequences

- Model calls are auditable as text-only payloads.
- Phase 2 emits five text-based artifacts and no SVG, raster image, or rendered diagram.
- Existing image files on disk are historical data but are ignored by application loading and UI.
- Consumers that want a visual diagram must render the `.mmd` outside this workflow.

## ADR-031 - Keep usage accounting internal and remove Phase 2 relationship artifacts

- Date: 2026-09-28
- Status: Accepted; amends ADR-028 and ADR-030

### Context

The API Analyzer result page displayed a large aggregate token count and per-call ledger, and Phase 2
still emitted a plain-text entity-relationship source after image output was removed. Neither item is
required to consume the enriched API contract, and both add operator-facing output noise.

### Decision

Keep token budgets, preflight enforcement, provider-reported accounting, and the machine-readable
`tokenUsage` report field. Remove the aggregate usage message and per-call table from Streamlit.
Remove entity-relationship source generation and exclude legacy `.mmd` and image artifacts from the
active/saved Phase 2 artifact collection. Define the Phase 2 output contract as enriched OpenAPI plus
semantic metadata, evidence map, and enrichment report only.

### Consequences

- Token limits still prevent overspending and remain auditable in `enrichment-report.json`.
- Operators no longer see the usage summary or ledger in the normal result view.
- Phase 2 produces four required artifacts and no relationship diagram/source artifact.
- Existing historical relationship files on disk are ignored rather than deleted.

## ADR template

## ADR-032 - Separate ACORD ingestion from the regional application pipeline

- Date: 2026-09-28
- Status: Accepted; amends the workflow presentation in P2.6q

### Context

The six-stage UI incorrectly implied that ACORD ingestion and alignment were steps 5 and 6 of each
selected regional application's Discovery-to-review journey. ACORD reference material requires an
independent ingestion and retrieval lifecycle.

### Decision

Present the selected regional application as four stages: Discovery, Repository RAG, API Analyzer,
and Regional View. Show only aggregate progress for those stages, without per-stage status cards.
Expose ACORD ingestion as a separate, unnumbered workspace and describe it as a future independent
RAG pipeline. Do not expose ACORD alignment as a numbered workspace before ingestion is implemented
and its reference artifact is accepted.

### Consequences

- Regional application progress no longer includes planned ACORD work.
- ACORD can later own separate inputs, provenance, indexing, acceptance, and progress state.
- Alignment remains gated without implying that it is currently available.

## ADR-033 - Resume partial semantic analysis by structural target ID

- Date: 2026-09-28
- Status: Accepted; extends ADR-028

### Context

Large repositories can exhaust the configured per-run token ceiling after producing valid semantic
results for only part of the Discovery inventory. Restarting repeats paid calls for completed
targets and can reach the same ceiling again.

### Decision

Allow a partial Phase 2 artifact set to seed a continuation. Validate every prior endpoint, entity,
attribute, enum, and response result against the current Discovery artifact before reuse. Skip
completed IDs and call the provider only for unfinished targets. Give each explicit continuation a
fresh configured token/request budget, merge new validated results into regenerated artifacts, and
retain cumulative usage for audit. Keep full restart as a distinct operator action.

### Consequences

- Budget exhaustion produces resumable output instead of forcing repeated paid analysis.
- A large application may require multiple explicit continuation runs.
- Changed or mismatched Discovery structures reject prior semantics rather than reusing them.
- The token ceiling remains effective per run; continuation is not an unbounded call.

## ADR-034 - Remove per-entity normalization and define reached-stage progress

- Date: 2026-09-29
- Status: Accepted; amends ADR-023

### Context

The Regional View exposed optional entity-by-entity LLM normalization settings even though the
operator does not require that workflow. Its progress bar also counted only states named
`Complete`; consequently a valid partial Analyzer result did not advance the bar and the final
read-only Regional View could never contribute to completion.

### Decision

Remove the per-entity normalization settings, action, and proposal columns. Keep authoritative
Discovery/API Analyzer model data and the separately approved region-wide review workflow. Define
the regional pipeline indicator as stages reached: `Complete`, `Partial`, and `Current` contribute
to progress. When API Analyzer completes, Regional View becomes the current fourth stage without
attempting to switch Streamlit tabs programmatically.

### Consequences

- Regional model inspection no longer makes an optional LLM normalization call per entity.
- Partial analysis visibly advances the pipeline while remaining labeled partial with coverage.
- Completed analysis reaches stage four even if the operator has not manually opened its tab.
- Navigation remains user-controlled and compatible with Streamlit widget state.

## ADR-035 - Ingest ACORD references as independent structural truth

- Date: 2026-09-29
- Status: Accepted; implements the ingestion boundary introduced by ADR-032

### Context

The ACORD workspace needs to accept an approved YAML/JSON API reference and make its endpoints,
models, nested fields, prose, and constraints retrievable before any comparison with a regional
application. Reusing regional Discovery would incorrectly require a .NET repository, while sending
the document through an LLM would make structural extraction nondeterministic.

### Decision

Accept one authorized OpenAPI 3 YAML/JSON document per ACORD ingestion, with an operator-supplied
reference label and approved version. Parse endpoint and schema structure deterministically,
promote inline nested objects into linked entities, retain available summary, description,
`$comment`/documentation notes, validation constraints, source hash, and JSON-pointer lineage, and
generate the same five operator views as Discovery. Create bounded endpoint/entity chunks and store
their embeddings in an ACORD-specific persistent local Chroma index. Persist each ingestion under
ignored `.acord/<run-id>/` storage and allow exact saved references to be reopened and queried.
Do not compare the reference with regional APIs, generate canonical mappings, or use an LLM in this
ingestion slice.

### Consequences

- ACORD structure and prose remain traceable to the uploaded reference rather than inferred.
- Nested inline models and their constraints are available to later alignment retrieval.
- YAML formatting comments are not part of the OpenAPI data model; semantic `$comment`, description,
  supported vendor-note fields, and external-documentation metadata are retained.
- Local ingestion history may contain licensed reference content and must be protected or removed
  according to the operator's data-handling policy.
- ACORD-to-regional alignment remains a separately gated future capability.

## ADR-036 - Group crawler and ACORD workspaces by evidence pipeline

- Date: 2026-09-29
- Status: Accepted; extends ADR-032 and ADR-035

### Context

The sidebar listed the regional crawler stages and ACORD ingestion as one flat set even though they
operate on different source evidence and persistence lifecycles. Operators also need to see where
the future comparison between ACORD and the generated regional catalog will occur.

### Decision

Group navigation under `Crawler code` and `ACORD view`. The crawler group contains Discovery Agent,
Repository RAG, API Analyzer, and Regional View. The ACORD group contains ACORD ingestion and a
separate alignment workspace. Keep alignment gated until implemented, and identify its regional
inputs as the selected entity/attribute catalog plus the domain/capability catalog produced from
API Analyzer evidence.

### Consequences

- Navigation reflects the two independent ingestion and retrieval pipelines.
- ACORD ingestion remains usable without implying that comparison is already implemented.
- The future alignment boundary is visible and does not mutate either source catalog.

## ADR-037 - Keep standards workspaces outside the crawler tab strip

- Date: 2026-09-29
- Status: Accepted; extends ADR-036

### Context

Showing ACORD ingestion and alignment beside the four crawler tabs made the independent standards
pipeline look like additional stages of crawler execution. Operators also need one future-facing
place to review canonical alignment and quantify gaps.

### Decision

Keep only Discovery, Repository RAG, API Analyzer, and Regional View visible in the crawler tab row.
Open ACORD ingestion, ACORD alignment, and Canonical View from the separate ACORD sidebar menu.
Define Canonical View as three review areas: entity alignment, domain/capability alignment, and ACORD
gap identification with aligned and unaligned coverage percentages. Until mapping is implemented
and reviewed, show these sections as planned and do not invent percentage values.

### Consequences

- The crawler tab strip represents only crawler stages.
- Standards ingestion, comparison, and canonical review have separate navigation identities.
- Gap metrics remain empty until traceable alignment evidence exists.

## ADR-038 - Use separate page containers instead of hidden standards tabs

- Date: 2026-09-29
- Status: Accepted; strengthens ADR-037

### Context

Hiding ACORD tab buttons with CSS removed them visually but left ACORD workspaces as members of the
same tab control. That did not satisfy the requirement for separate pages and made the navigation
structure dependent on tab implementation details.

### Decision

Create the top tab control from the four crawler labels only. Render ACORD ingestion, ACORD
alignment, and Canonical View in separately keyed page containers selected through the ACORD sidebar
menu. Hide inactive page containers as layout hosts, not tab buttons, and synchronize crawler tab
selection independently from the active standards page.

### Consequences

- No ACORD or Canonical label exists in the top tab control.
- Standards pages retain the existing session state and saved artifacts.
- Crawler tab selection and standards-page selection have independent widget state.

## ADR-039 - Gate canonical output on explicit ACORD alignment review

- Date: 2026-09-29
- Status: Accepted; advances the alignment and canonicalization roadmap

### Context

Operators need to compare the regionally generated entity and domain catalogs with an accepted
ACORD reference, understand gaps, choose standards, and explain exceptions. Automatically replacing
regional names from a similarity score would discard reviewer intent and could present a proposed
mapping as canonical truth.

### Decision

Create deterministic alignment proposals for entities, attributes, domains, and capabilities using
name, type, description, and structural evidence. Use three operator statuses: full match, partial
match, and not matched. Calculate coverage with full matches weighted as one and partial matches as
one half, while also reporting the strict not-matched percentage. Match child attributes and
capabilities one-to-one within a proposed parent so a single ACORD child is not silently reused.

Require the reviewer to choose the ACORD candidate or a manual canonical name for every item.
Require a reason for every partial match, unmatched item, or manual choice, and block approval until
the entire entity/attribute and domain/capability inventory is resolved. Persist approval as a new
`.alignments/<id>/canonical-alignment.json` artifact containing canonical entities, canonical
endpoints, approved entity usages, match metrics, and a complete decision/reason ledger. Do not
modify Discovery, API Analyzer, Regional View, or ACORD ingestion artifacts.

### Consequences

- The UI can emphasize unmatched detail without hiding full matches or their evidence.
- Canonical names and endpoints are review outcomes, not automatic similarity-score assertions.
- Approved artifacts are reopenable and downloadable, and retain exact ACORD/run provenance.
- This delivers a single-region canonical model but does not implement multi-region consolidation,
  enterprise version governance, adapter generation, or change-impact analysis.

Copy this section for future decisions:

```markdown
## ADR-NNN - Title

- Date: YYYY-MM-DD
- Status: Proposed | Accepted | Superseded

### Context

Why the decision is needed.

### Decision

What was decided.

### Consequences

Expected benefits, costs, and constraints.
```
