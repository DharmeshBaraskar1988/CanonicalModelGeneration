# Repository RAG

The Discovery Agent requires a .NET repository ZIP. OpenAPI YAML/JSON is optional reconciliation
evidence; it cannot be used alone for a new Phase 1 run.

## Example: how code is chunked

For a detailed method-body and metadata walkthrough, see [How repository code is chunked](CODE_CHUNKING.md).

The Quote fixture contains `src/RegionalQuoteApi/Models/QuoteResponse.cs`. Roslyn creates this
hierarchy from its syntax:

```text
QuoteResponse.cs                       file (lines 1-26)
└─ RegionalQuoteApi.Models.QuoteResponse class (lines 3-12)
   ├─ QuoteId                           property (line 5)
   ├─ Status                            property (line 7)
   ├─ Premium                           property (line 9)
   └─ ValidUntil                        property (line 11)
```

Each chunk stores a stable ID, parent ID, original relative file path, source hash, symbol,
line range and bounded redacted code. `CONTAINS` edges connect the hierarchy. If a body exceeds
1,800 characters, child windows cover its full text. Name-based calls, references and inheritance
produce typed **candidate** edges, preserving ambiguity until semantic symbol resolution exists.

For a `QuoteResponse.Premium` search, exact DiscoveryModel lineage selects the property at line 9.
Hybrid lexical and vector ranking adds relevant code, then bounded parent/relationship expansion
provides class context. A free-text search without an exact subject may yield approximate matches.
The index exposes unresolved references and coverage gaps rather than claiming that a name match
establishes an execution path.

## Build, search, and interpret

In the **Repository RAG** tab, upload a repository or use the Discovery Agent's current repository.
Choose a local Sentence Transformer or OpenAI embedding model, then build the index. The local
MiniLM model is pinned to revision `1110a243fdf4706b3f48f1d95db1a4f5529b4d41` and uses pooled
token windows. It runs fully offline from `.models/all-MiniLM-L6-v2` (override with
`CMG_EMBEDDING_MODEL_DIR`); download it once with `canonical-rag download-model`, which is the only
step that contacts Hugging Face. OpenAI offers `text-embedding-ada-002`, `text-embedding-3-small` and
`text-embedding-3-large`; it requires explicit acknowledgement because all included redacted
chunks are sent to that provider during indexing. There is no hash-vector fallback in production.

Select an endpoint, entity, attribute or enum for exact retrieval. A free code query uses lexical,
vector and relationship search without an exact subject. After reviewing the code,
**Explain selected target** (or **Explain retrieved code** for a free query) asks the API Analyzer
to interpret those snippets. That step needs a
working OpenAI key and separate acknowledgement for the selected source context. The result has
an inferred description, confidence, exact structural identity, source locations and gaps.
The embedding alone never supplies business meaning. Focused attribute interpretation analyzes
its owning model as one batch and presents the chosen field's meaning. Focused interpretation now
also asks for separate observed/inferred code claims, each citing a retrieved chunk ID. For
`QuoteResponse.Premium`, this can distinguish the property declaration from the
`InMemoryQuoteService.Create` calculation. A target with no grounded code claim is marked partial,
even if the provider returned a model description.
For a free code query, the API Analyzer returns observed/inferred/unknown claims. Each observed
or inferred claim must cite one of the retrieved chunk IDs. The UI displays the claim confidence
and cited code. Candidate call links do not become proven execution paths.

Indexes live in ignored `.rag/<index>/` folders, each containing `rag-manifest.json` and `chroma/`.
Use **Reopen a saved index** with the same repository, DiscoveryModel and embedding profile after
restarting the UI. The manifest download contains redacted chunks and hierarchy, not the vectors.
Source hashes, DiscoveryModel digest and embedding configuration are checked before analyzer reuse.

CLI examples from the project root:

```powershell
python -m canonical_model_generator.cli --region IN --system quote --openapi fixtures/RegionalQuoteApi/openapi/quote-api.yaml --output .tmp/yaml-discovery
python -m canonical_model_generator.cli --region IN --system quote --repository fixtures/RegionalQuoteApi --project fixtures/RegionalQuoteApi/src/RegionalQuoteApi/RegionalQuoteApi.csproj --output .tmp/repo-discovery
python -m canonical_model_generator.repository_rag.cli index --repository fixtures/RegionalQuoteApi --discovery .tmp/repo-discovery/discovery-model.json --output .rag/quote
python -m canonical_model_generator.repository_rag.cli query --index .rag/quote --query QuoteResponse.Premium
```

Cloud indexing adds `--embedding-provider openai --embedding-model text-embedding-ada-002
--allow-source-sharing`. Cloud queries also require `--allow-source-sharing`. The CLI reads
`OPENAI_API_KEY` from the environment or ignored `.env`; keys are never saved in index artifacts.

Current limits: 5,000 files, 1 MB/file, 30 MB total source, 20,000 chunks, 1,800 characters/chunk,
32 embedding documents/batch, 120-second syntax extraction, and 8 results/12,000 characters by
default per query. Build/vendor/generated files and out-of-root links are excluded. Redaction is
pattern-based and cannot guarantee detection of arbitrary secrets. Generated semantic text remains
an inference requiring review; deep call paths, persistence and security stay open work.

Verification: `python -m pytest` exercises both input paths, hierarchy, attribution, persistence,
snapshot/model mismatch, retrieval and analyzer reuse with offline fake embeddings/providers.
`python scripts/verify_rag_fixture.py` runs the actual local MiniLM model through the Streamlit
index/retrieve flow and writes `.tmp/rag-acceptance.json`. Live OpenAI accuracy acceptance remains
pending a working approved key.

Implementation references: [OpenAI embeddings](https://developers.openai.com/api/docs/guides/embeddings),
[Sentence Transformer](https://sbert.net/docs/package_reference/sentence_transformer/model.html),
[Chroma retrieval](https://docs.trychroma.com/docs/querying-collections/query-and-get).
