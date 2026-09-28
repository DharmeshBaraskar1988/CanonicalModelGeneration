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

## ADR template

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
