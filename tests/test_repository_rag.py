import json
from pathlib import Path

import pytest

from canonical_model_generator.discovery_agent.model import DiscoveryModel
from canonical_model_generator.discovery_agent.roslyn import extract_roslyn
from canonical_model_generator.discovery_agent.workflow import run_discovery
from canonical_model_generator.repository_rag.chunking import build_chunks, read_sources, redact
from canonical_model_generator.repository_rag.embeddings import EmbeddingConfig, create_embedder
from canonical_model_generator.repository_rag.index import ChromaRepositoryIndex

FIXTURE = Path("fixtures/RegionalQuoteApi").resolve()


@pytest.fixture(scope="module")
def quote_model():
    return extract_roslyn(
        FIXTURE / "src/RegionalQuoteApi/RegionalQuoteApi.csproj", FIXTURE, "IN", "quote"
    )


def test_hierarchy_and_exact_subject_retrieval_survive_reopening(
    tmp_path, quote_model, fake_embedder
):
    index = ChromaRepositoryIndex(tmp_path / "index", fake_embedder)
    try:
        stats = index.ingest(FIXTURE, quote_model)
        assert stats["chunksIndexed"] > stats["filesIndexed"]
        assert not stats["gaps"]
        entity = next(
            item for item in quote_model.entities if item.original_name.endswith("QuoteResponse")
        )
        attribute = next(item for item in entity.attributes if item.original_name == "Premium")
        targets = [quote_model.operations[0], entity, attribute]
        expected = ["MethodDeclaration", "ClassDeclaration", "PropertyDeclaration"]
        for target, kind in zip(targets, expected, strict=True):
            hits = index.query(target.name, subject_id=target.id)
            assert hits[0]["kind"] == kind
            assert hits[0]["retrievalReason"] == "exact-lineage"
            assert target.id in hits[0]["subjectIds"]
            assert hits[0]["parentId"]
            assert len({item["id"] for item in hits}) == len(hits)
        original = index.query("QuoteResponse.Premium", subject_id=attribute.id)
        assert any("QuoteResponse" in item["symbol"] for item in original[1:])
    finally:
        index.close()
    index = ChromaRepositoryIndex(tmp_path / "index", fake_embedder)
    try:
        assert index.query("QuoteResponse.Premium", subject_id=attribute.id) == original
        index.validate_snapshot(FIXTURE, quote_model)
        with pytest.raises(ValueError, match="Unknown discovery"):
            index.query("Premium", subject_id="not-a-subject")
        assert sum(len(item["text"]) for item in index.query("Premium", max_characters=80)) <= 80
    finally:
        index.close()


def test_index_rejects_changed_sources_and_embedding_profile(tmp_path, fake_embedder):
    repository = tmp_path / "repo"
    repository.mkdir()
    source = repository / "Api.cs"
    source.write_text("class First { public int Value { get; set; } }", encoding="utf-8")
    index = ChromaRepositoryIndex(tmp_path / "index", fake_embedder)
    try:
        index.ingest(repository)
        source.write_text("class Second {}", encoding="utf-8")
        with pytest.raises(ValueError, match="snapshot changed"):
            index.ingest(repository)
    finally:
        index.close()
    fake_embedder.config = EmbeddingConfig(provider="openai", model="text-embedding-ada-002")
    with pytest.raises(ValueError, match="model mismatch"):
        ChromaRepositoryIndex(tmp_path / "index", fake_embedder)


def test_syntax_chunks_preserve_duplicates_overloads_windows_and_secret_redaction(tmp_path):
    (tmp_path / "Api.cs").write_text(
        "namespace Sample;\nclass First {\n public int Value {get;set;}\n"
        " public void Run(int x) { Helper(); }\n public void Run(string x) {}\n"
        " public void Helper() {}\n}\nclass Second {\n public int Value {get;set;}\n}\n"
        + "// long code context\n" * 300
        + "// FINAL_CODE_MARKER\n",
        encoding="utf-8",
    )
    (tmp_path / "settings.json").write_text('{"ApiKey": "super secret value"}', encoding="utf-8")
    files, gaps = read_sources(tmp_path)
    assert not gaps
    chunks, edges, gaps = build_chunks(files)
    assert len({item["id"] for item in chunks}) == len(chunks)
    fields = [c for c in chunks if c["name"] == "Value"]
    assert len(fields) == 2 and fields[0]["parentId"] != fields[1]["parentId"]
    methods = [c for c in chunks if c["name"] == "Run"]
    assert len(methods) == 2 and methods[0]["symbol"] != methods[1]["symbol"]
    assert any(e["kind"] == "CALLS_CANDIDATE" for e in edges)
    assert any("FINAL_CODE_MARKER" in c["text"] for c in chunks)
    assert "super secret" not in json.dumps(chunks)
    assert all(len(c["text"]) <= 1800 for c in chunks)
    assert all(c["startLine"] <= c["endLine"] for c in chunks)
    assert (
        redact('password = "value with spaces"\nnext') == "// [REDACTED secret-bearing line]\nnext"
    )


def test_identical_windows_on_one_long_line_have_distinct_stable_ids(tmp_path, fake_embedder):
    repository = tmp_path / "repo"
    repository.mkdir()
    (repository / "repeated.json").write_text("x" * 3600, encoding="utf-8")
    files, _ = read_sources(repository)
    chunks, _, _ = build_chunks(files)
    windows = [chunk for chunk in chunks if chunk["kind"] == "window"]
    assert len(windows) == 2
    assert [chunk["windowIndex"] for chunk in windows] == [0, 1]
    assert windows[0]["text"] == windows[1]["text"]
    assert windows[0]["id"] != windows[1]["id"]
    assert [chunk["id"] for chunk in build_chunks(files)[0]] == [chunk["id"] for chunk in chunks]

    index = ChromaRepositoryIndex(tmp_path / "index", fake_embedder)
    try:
        assert index.ingest(repository)["chunksIndexed"] == 3
        hits = index.query("repeated.json", limit=3)
        assert {hit["windowIndex"] for hit in hits if hit["kind"] == "window"} == {0, 1}
    finally:
        index.close()


def test_global_statement_and_local_function_with_shared_span_are_distinct_chunks(
    tmp_path, fake_embedder
):
    (tmp_path / "Program.cs").write_text(
        'static void Configure()\n{\n    Console.WriteLine("configured");\n}\n',
        encoding="utf-8",
    )
    files, _ = read_sources(tmp_path)
    chunks, edges, _ = build_chunks(files)
    same_span = [
        chunk
        for chunk in chunks
        if chunk["startLine"] == 1 and chunk["endLine"] == 4 and chunk["kind"] != "file"
    ]
    assert {chunk["kind"] for chunk in same_span} == {
        "GlobalStatement",
        "LocalFunctionStatement",
    }
    assert len({chunk["id"] for chunk in same_span}) == 2
    global_statement = next(chunk for chunk in same_span if chunk["kind"] == "GlobalStatement")
    local_function = next(chunk for chunk in same_span if chunk["kind"] == "LocalFunctionStatement")
    assert local_function["parentId"] == global_statement["id"]
    assert any(
        edge["source"] == global_statement["id"]
        and edge["target"] == local_function["id"]
        and edge["kind"] == "CONTAINS"
        for edge in edges
    )
    index = ChromaRepositoryIndex(tmp_path / ".rag", fake_embedder)
    try:
        assert index.ingest(tmp_path)["chunksIndexed"] == len(chunks)
        hits = index.query("Configure", limit=5)
        assert {hit["kind"] for hit in hits} >= {
            "GlobalStatement",
            "LocalFunctionStatement",
        }
    finally:
        index.close()


def test_duplicate_chunk_ids_fail_before_chroma_upsert(tmp_path, fake_embedder, monkeypatch):
    repository = tmp_path / "repo"
    repository.mkdir()
    (repository / "source.json").write_text("{}", encoding="utf-8")
    duplicate = {
        "id": "same-id",
        "path": "source.json",
        "startLine": 1,
        "kind": "window",
    }
    monkeypatch.setattr(
        "canonical_model_generator.repository_rag.index.build_chunks",
        lambda files: ([duplicate, duplicate.copy()], [], []),
    )
    index = ChromaRepositoryIndex(tmp_path / "index", fake_embedder)
    try:
        with pytest.raises(ValueError, match="Duplicate code-chunk identity before indexing"):
            index.ingest(repository)
        assert not index.manifest_path.exists()
    finally:
        index.close()


def test_repository_is_required_and_openapi_is_optional(tmp_path):
    state = run_discovery(
        region="IN",
        system="quote",
        openapi=FIXTURE / "openapi/quote-api.yaml",
        output=tmp_path / "yaml",
    )
    assert state["errors"] == [
        "A repository boundary and project are required; OpenAPI is optional"
    ]
    assert not (tmp_path / "yaml").exists()
    state = run_discovery(
        region="IN",
        system="quote",
        repository=FIXTURE,
        project=FIXTURE / "src/RegionalQuoteApi/RegionalQuoteApi.csproj",
        output=tmp_path / "repo",
    )
    assert not state["errors"] and len(state["model"].operations) == 2
    DiscoveryModel.model_validate_json((tmp_path / "repo/discovery-model.json").read_bytes())
    missing = run_discovery(region="IN", system="quote", output=tmp_path / "missing")
    assert missing["errors"]


def test_cloud_embeddings_require_explicit_sharing():
    config = EmbeddingConfig(provider="openai", model="text-embedding-ada-002")
    with pytest.raises(ValueError, match="source-sharing"):
        create_embedder(config, api_key="unused", allow_source_sharing=False)


def test_free_text_code_interpretation_requires_citations(tmp_path, fake_embedder):
    from canonical_model_generator.api_analyzer.contracts import CodeClaim, CodeSemantic
    from canonical_model_generator.api_analyzer.inspect import inspect_retrieved_code

    repository = tmp_path / "repo"
    repository.mkdir()
    (repository / "QuoteService.cs").write_text(
        "class QuoteService { decimal CalculatePremium(decimal rate) { return rate * 100; } }",
        encoding="utf-8",
    )
    index = ChromaRepositoryIndex(tmp_path / "rag", fake_embedder)
    try:
        index.ingest(repository)

        class Provider:
            model_name = "offline"
            invalid = False

            def validate_connection(self):
                pass

            def analyze_code(self, context):
                assert any("CalculatePremium" in item["text"] for item in context["sourceSnippets"])
                citation = "invented" if self.invalid else context["sourceSnippets"][0]["chunkId"]
                return CodeSemantic(
                    summary="Premium calculation code",
                    role="Calculation helper",
                    claims=[
                        CodeClaim(
                            text="Multiplies rate by 100",
                            classification="observed",
                            confidence=0.9,
                            evidence_chunk_ids=[citation],
                        )
                    ],
                    gaps=[],
                )

        provider = Provider()
        result = inspect_retrieved_code(index, "CalculatePremium", provider)
        assert set(result["semantic"]["claims"][0]["evidenceChunkIds"]) <= {
            citation["chunkId"] for citation in result["citations"]
        }
        assert result["citations"][0]["path"] == "QuoteService.cs"
        provider.invalid = True
        with pytest.raises(RuntimeError, match="citation validity"):
            inspect_retrieved_code(index, "CalculatePremium", provider)
    finally:
        index.close()


def test_openai_embedding_adapter_orders_results_and_redacts_errors(monkeypatch):
    from types import SimpleNamespace

    import openai

    requests = []

    def create(**kwargs):
        requests.append(kwargs)
        return SimpleNamespace(
            data=[
                SimpleNamespace(index=1, embedding=[0.0, 1.0]),
                SimpleNamespace(index=0, embedding=[1.0, 0.0]),
            ]
        )

    monkeypatch.setattr(
        openai,
        "OpenAI",
        lambda **kwargs: SimpleNamespace(embeddings=SimpleNamespace(create=create)),
    )
    adapter = create_embedder(
        EmbeddingConfig(provider="openai", model="text-embedding-ada-002"),
        api_key="test-only",
        allow_source_sharing=True,
    )
    assert adapter.embed(["first", "second"]) == [[1.0, 0.0], [0.0, 1.0]]
    assert requests[0]["model"] == "text-embedding-ada-002"

    def fail(**kwargs):
        raise RuntimeError("provider echoed a private credential")

    adapter.client.embeddings.create = fail
    with pytest.raises(RuntimeError, match="OpenAI embeddings failed") as error:
        adapter.embed(["source"])
    assert "private credential" not in str(error.value)


def test_outside_repository_links_are_not_read(tmp_path):
    root = tmp_path / "repo"
    root.mkdir()
    outside = tmp_path / "outside.cs"
    outside.write_text("class ExternalSecret {}", encoding="utf-8")
    try:
        (root / "link.cs").symlink_to(outside)
    except OSError:
        pytest.skip("Windows symlink privileges unavailable")
    files, gaps = read_sources(root)
    assert files == [] and any("linked source" in gap for gap in gaps)


def test_prior_index_artifacts_are_not_reingested(tmp_path):
    (tmp_path / "Api.cs").write_text("class Api {}", encoding="utf-8")
    saved = tmp_path / ".rag" / "old"
    saved.mkdir(parents=True)
    (saved / "rag-manifest.json").write_text('{"old": true}', encoding="utf-8")
    files, _ = read_sources(tmp_path)
    assert [item["path"] for item in files] == ["Api.cs"]
