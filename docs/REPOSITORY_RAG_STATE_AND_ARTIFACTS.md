# Repository RAG: saved index and retrieval handoff

Repository RAG is a **separate service**, not a LangGraph node or agent state. It can run before
API analysis, with or without a DiscoveryModel. Its main implementation is
[index.py](../src/canonical_model_generator/repository_rag/index.py); see also
[code chunking](CODE_CHUNKING.md).

## Build steps and values

| Step | Reads | Produces | Persistent? |
| --- | --- | --- | --- |
| Read sources | Repository snapshot | Bounded, redacted file texts; raw-file hashes; skipped-file gaps | Recorded in manifest after indexing |
| Parse and chunk | Redacted C# and other supported text | File/type/member/window chunks, spans, parent IDs, `CONTAINS` and reference-candidate edges | Manifest |
| Bind Discovery subjects (optional) | Chunks plus validated `DiscoveryModel` | Endpoint/entity/attribute/enum target list, exact source bindings, binding gaps | Manifest |
| Embed and store | Path + symbol + chunk text, selected embedding profile | Vectors and Chroma collection | `chroma/` |
| Save manifest | All above plus source/model fingerprint and statistics | `rag-manifest.json` | Yes |

The saved index directory contains **both** `rag-manifest.json` and `chroma/`. The manifest
includes redacted chunk text, relationships, target bindings, file hashes, embedding profile,
and statistics; the Chroma directory contains the vectors. Downloading only the manifest does
not give you a complete searchable index. In the UI, indexes are saved under ignored `.rag/`.

## Retrieval and interpretation

| Action | Reads | Returns / stores |
| --- | --- | --- |
| `index.query(text, subject_id=...)` | Saved index; optional exact Discovery target ID | Bounded snippet dictionaries with `chunkId`, path, lines, symbol, text, retrieval reason; UI stores these in `rag_results` |
| `inspect_retrieved_target(...)` | Serialized DiscoveryModel, matching saved index, target ID, semantic provider | Focused `rag_semantics` value: target description, separate cited code claims, confidence, gaps, and citations |
| `inspect_retrieved_code(...)` | Saved index, free query, semantic provider | Focused `rag_semantics` value: observed/inferred/unknown claims and chunk citations |

These retrieval/interpretation values are **not** additional files written by the RAG service.
Only retrieved, bounded, redacted snippets are supplied to semantic analysis, after operator
consent. A similarity score is retrieval evidence, not semantic meaning. Name-based call and
reference edges are candidate links, not proven execution paths. A selected target without a
grounded code claim is partial.

## How the API Analyzer reuses it

The API Analyzer always requires `discovery-model.json` as its structural input. When a
repository is available, it may also receive the repository path and `rag_store_path` as
**separate supporting inputs**. It checks source hashes, DiscoveryModel digest, and embedding
profile before reuse; a mismatch requires a new index. The saved index is never a substitute
for `discovery-model.json`, and no Discovery graph state is passed through it.

The Streamlit repository workflow requires building a fresh saved index before running the full
API Analyzer. Each Discovery submission and each index build is isolated; the UI does not list or
reuse indexes from other uploads. Library callers may omit `rag_store_path`; then the Analyzer
builds a temporary index for that run. New Phase 1 runs always include a repository; defensive
support for older specification-only artifacts remains internal to the Analyzer.

Previous: [Discovery Agent state and artifacts](DISCOVERY_AGENT_STATE_AND_ARTIFACTS.md).
Next: [API Analyzer state and artifacts](API_ANALYZER_STATE_AND_ARTIFACTS.md).
