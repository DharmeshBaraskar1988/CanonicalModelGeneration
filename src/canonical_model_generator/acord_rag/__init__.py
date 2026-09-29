"""Independent ACORD OpenAPI ingestion and retrieval pipeline."""

from canonical_model_generator.acord_rag.index import AcordDocumentIndex
from canonical_model_generator.acord_rag.pipeline import (
    ACORD_ARTIFACTS,
    build_acord_chunks,
    generate_acord_artifacts,
    parse_acord_document,
)

__all__ = [
    "ACORD_ARTIFACTS",
    "AcordDocumentIndex",
    "build_acord_chunks",
    "generate_acord_artifacts",
    "parse_acord_document",
]
