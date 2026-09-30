"""Build/reopen code indexes and retrieve cited context without running an LLM agent."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from dotenv import load_dotenv

from canonical_model_generator.discovery_agent.model import DiscoveryModel
from canonical_model_generator.openai_config import resolve_openai_api_key
from canonical_model_generator.repository_rag.embeddings import (
    LOCAL_MODEL,
    EmbeddingConfig,
    create_embedder,
)
from canonical_model_generator.repository_rag.index import ChromaRepositoryIndex


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="canonical-rag")
    commands = parser.add_subparsers(dest="command", required=True)
    build = commands.add_parser("index")
    build.add_argument("--repository", required=True, type=Path)
    build.add_argument("--output", required=True, type=Path)
    build.add_argument("--discovery", type=Path)
    build.add_argument(
        "--embedding-provider",
        choices=["sentence_transformer", "openai"],
        default="sentence_transformer",
    )
    build.add_argument("--embedding-model")
    build.add_argument("--allow-source-sharing", action="store_true")
    query = commands.add_parser("query")
    query.add_argument("--index", required=True, type=Path)
    query.add_argument("--query", required=True)
    query.add_argument("--subject-id")
    query.add_argument("--limit", type=int, default=8)
    query.add_argument("--allow-source-sharing", action="store_true")
    args = parser.parse_args(argv)
    load_dotenv()
    index = None
    try:
        if args.command == "index":
            config = EmbeddingConfig(
                provider=args.embedding_provider,
                model=args.embedding_model
                or (
                    LOCAL_MODEL
                    if args.embedding_provider == "sentence_transformer"
                    else "text-embedding-ada-002"
                ),
            )
            location = args.output
        else:
            manifest = json.loads((args.index / "rag-manifest.json").read_text(encoding="utf-8"))
            config = EmbeddingConfig.model_validate(manifest["embedding"])
            location = args.index
        adapter = create_embedder(
            config,
            api_key=resolve_openai_api_key(),
            allow_source_sharing=args.allow_source_sharing,
        )
        index = ChromaRepositoryIndex(location, adapter)
        if args.command == "index":
            model = (
                DiscoveryModel.model_validate_json(args.discovery.read_bytes())
                if args.discovery
                else None
            )
            result = index.ingest(
                args.repository, model, lambda message: print(message, file=sys.stderr)
            )
        else:
            result = index.query(args.query, subject_id=args.subject_id, limit=args.limit)
        print(json.dumps(result, indent=2))
        return 0
    except (OSError, RuntimeError, ValueError) as exc:
        print(str(exc), file=sys.stderr)
        return 1
    finally:
        if index is not None:
            index.close()


if __name__ == "__main__":
    raise SystemExit(main())
