"""Selectable real embedding providers. No implicit hashing fallback."""

from __future__ import annotations

import json
import math
import os
from functools import lru_cache
from pathlib import Path
from typing import Literal, Protocol

from pydantic import BaseModel, ConfigDict, model_validator

from canonical_model_generator.llm_audit import usage_token_counts, write_llm_call_log

LOCAL_MODEL = "sentence-transformers/all-MiniLM-L6-v2"
LOCAL_REVISION = "1110a243fdf4706b3f48f1d95db1a4f5529b4d41"
# The local model is loaded only from this folder; nothing is fetched from Hugging Face at runtime.
MODEL_DIR_ENV = "CMG_EMBEDDING_MODEL_DIR"
DEFAULT_MODEL_DIR = Path(__file__).resolve().parents[3] / ".models" / "all-MiniLM-L6-v2"
MODEL_MARKER = "cmg-model.json"
_MODEL_FILES = ["*.json", "*.txt", "model.safetensors", "1_Pooling/*"]
OPENAI_MODELS = ("text-embedding-ada-002", "text-embedding-3-small", "text-embedding-3-large")


class EmbeddingConfig(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    provider: Literal["sentence_transformer", "openai"] = "sentence_transformer"
    model: str = LOCAL_MODEL
    revision: str | None = LOCAL_REVISION

    @model_validator(mode="after")
    def validate_model(self) -> EmbeddingConfig:
        allowed = (LOCAL_MODEL,) if self.provider == "sentence_transformer" else OPENAI_MODELS
        if self.model not in allowed:
            raise ValueError("Unsupported embedding model")
        if self.provider == "openai":
            object.__setattr__(self, "revision", None)
        return self


class Embedder(Protocol):
    config: EmbeddingConfig

    def embed(self, texts: list[str]) -> list[list[float]]: ...


def local_model_dir() -> Path:
    return Path(os.environ.get(MODEL_DIR_ENV) or DEFAULT_MODEL_DIR)


def download_local_model(target: Path | None = None) -> Path:
    """One-time, explicit download of the pinned model. The only step that contacts Hugging Face."""
    from huggingface_hub import snapshot_download

    target = target or local_model_dir()
    snapshot_download(
        LOCAL_MODEL, revision=LOCAL_REVISION, local_dir=target, allow_patterns=_MODEL_FILES
    )
    marker = {"model": LOCAL_MODEL, "revision": LOCAL_REVISION}
    (target / MODEL_MARKER).write_text(json.dumps(marker, indent=2), encoding="utf-8")
    return target


@lru_cache(maxsize=2)
def _local_model(name: str, revision: str | None):
    directory = local_model_dir()
    try:
        marker = json.loads((directory / MODEL_MARKER).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        raise RuntimeError(
            f"Local embedding model not found in {directory}. Download it once with "
            "`canonical-rag download-model` or set CMG_EMBEDDING_MODEL_DIR."
        ) from None
    if marker != {"model": name, "revision": revision}:
        raise RuntimeError(
            f"Local embedding model in {directory} is {marker.get('model')}@"
            f"{marker.get('revision')}; expected {name}@{revision}. Re-run "
            "`canonical-rag download-model`."
        )
    # Hard offline: no Hub lookups, update checks or telemetry while embedding source code.
    os.environ.setdefault("HF_HUB_OFFLINE", "1")
    os.environ.setdefault("TRANSFORMERS_OFFLINE", "1")
    os.environ.setdefault("HF_HUB_DISABLE_TELEMETRY", "1")
    from sentence_transformers import SentenceTransformer

    return SentenceTransformer(
        str(directory), device="cpu", local_files_only=True, trust_remote_code=False
    )


class SentenceTransformerEmbedder:
    def __init__(self, config: EmbeddingConfig) -> None:
        self.config = config

    def embed(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []
        model = _local_model(self.config.model, self.config.revision)
        # Pool all token windows; never silently drop the tail of a code chunk.
        tokenizer = model.tokenizer
        width = int(model.max_seq_length) - tokenizer.num_special_tokens_to_add()
        windows: list[str] = []
        owners: list[int] = []
        for owner, text in enumerate(texts):
            tokens = tokenizer.encode(text, add_special_tokens=False, truncation=False)
            for start in range(0, max(1, len(tokens)), width):
                windows.append(tokenizer.decode(tokens[start : start + width]) or " ")
                owners.append(owner)
        vectors = model.encode(windows, normalize_embeddings=True, show_progress_bar=False)
        output = [[0.0] * len(vectors[0]) for _ in texts]
        for owner, vector in zip(owners, vectors, strict=True):
            for position, value in enumerate(vector):
                output[owner][position] += float(value)
        return [_normalize(vector) for vector in output]


class OpenAIEmbedder:
    def __init__(
        self, config: EmbeddingConfig, *, api_key: str | None, allow_source_sharing: bool
    ) -> None:
        if not allow_source_sharing:
            raise ValueError("OpenAI embeddings require explicit source-sharing acknowledgement")
        if not api_key:
            raise ValueError("Configure the shared OpenAI API key to use OpenAI embeddings")
        from openai import OpenAI

        self.config = config
        self.client = OpenAI(api_key=api_key, timeout=60, max_retries=2)

    def embed(self, texts: list[str]) -> list[list[float]]:
        # Repository documents are bounded well below the model's token limit.
        if not texts:
            return []
        if any(not text or len(text) > 8000 for text in texts):
            raise ValueError("Embedding input must contain 1-8000 characters")
        try:
            result = self.client.embeddings.create(
                model=self.config.model, input=texts, encoding_format="float"
            )
        except Exception as exc:
            write_llm_call_log(
                provider="openai",
                operation="RepositoryEmbedding",
                model=self.config.model,
                status="failed",
                input_tokens=None,
                output_tokens=None,
                total_tokens=None,
                input_items=len(texts),
                produced_result=False,
                error=exc,
            )
            status = getattr(exc, "status_code", None)
            raise RuntimeError(
                f"OpenAI embeddings failed (HTTP {status or 'unavailable'}). "
                "Check the key, model access and connection."
            ) from None
        usage = getattr(result, "usage", None)
        input_tokens, output_tokens, total_tokens = usage_token_counts(usage)
        try:
            ordered = sorted(result.data, key=lambda item: item.index)
            if [item.index for item in ordered] != list(range(len(texts))):
                raise ValueError("Embedding provider returned incomplete results")
        except Exception as exc:
            write_llm_call_log(
                provider="openai",
                operation="RepositoryEmbedding",
                model=self.config.model,
                status="failed",
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                total_tokens=total_tokens,
                input_items=len(texts),
                produced_result=False,
                provider_request_id=getattr(result, "id", None),
                error=exc,
            )
            raise
        write_llm_call_log(
            provider="openai",
            operation="RepositoryEmbedding",
            model=self.config.model,
            status="completed",
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            total_tokens=total_tokens,
            input_items=len(texts),
            produced_result=True,
            provider_request_id=getattr(result, "id", None),
        )
        return [item.embedding for item in ordered]


def _normalize(vector: list[float]) -> list[float]:
    magnitude = math.sqrt(sum(value * value for value in vector)) or 1.0
    return [value / magnitude for value in vector]


def create_embedder(
    config: EmbeddingConfig | None = None,
    *,
    api_key: str | None = None,
    allow_source_sharing: bool = False,
) -> Embedder:
    config = config or EmbeddingConfig()
    if config.provider == "openai":
        return OpenAIEmbedder(config, api_key=api_key, allow_source_sharing=allow_source_sharing)
    return SentenceTransformerEmbedder(config)
