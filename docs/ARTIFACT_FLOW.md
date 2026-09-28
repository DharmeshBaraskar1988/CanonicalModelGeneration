# Artifact flow across Discovery, RAG, and API Analyzer

The current implementation has **two LangGraph agents** and one separate repository-index
service. A graph *state* is temporary working data; an *artifact* is a serialized output or a
saved index that another step can open.

```text
Repository + optional OpenAPI
  → Discovery Agent state
  → discovery-model.json ───────────────────────┐
  → five readable Discovery JSON views           │
                                                 ├→ API Analyzer state
Repository → Repository RAG → saved index ──────┘  → four Phase 2 artifacts
```

| Artifact | Producer | Actual consumer |
| --- | --- | --- |
| `discovery-model.json` | Discovery `generate_artifacts` | API Analyzer input validator and graph; optional RAG target binding |
| Five readable Discovery JSON views | Discovery `generate_artifacts` | UI/operator preview and download; **not** the API Analyzer |
| `rag-manifest.json` **plus** `chroma/` | Repository RAG `ingest` | RAG query/focused interpretation; optionally reused by full API Analyzer |
| Retrieved snippets / focused explanation | RAG query / API Analyzer `inspect` functions | Current UI session; not a saved full-run artifact |
| Six Phase 2 files | API Analyzer `render_and_validate` | UI/operator preview and download, including Mermaid-source and SVG ER diagrams; `enriched-openapi.yaml` is the planned Phase 3 input, but Phase 3 is not implemented |

Read each step in detail:

1. [Discovery Agent: state, steps, and six artifacts](DISCOVERY_AGENT_STATE_AND_ARTIFACTS.md)
2. [Repository RAG: saved index, retrieval, and optional handoff](REPOSITORY_RAG_STATE_AND_ARTIFACTS.md)
3. [API Analyzer: state, steps, and four artifacts](API_ANALYZER_STATE_AND_ARTIFACTS.md)

The one **required agent-to-agent handoff** is serialized `discovery-model.json`. The optional
saved RAG index supplements that model with implementation evidence; it does not replace it.
