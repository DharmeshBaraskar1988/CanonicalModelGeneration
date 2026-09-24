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
