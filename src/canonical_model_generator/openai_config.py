"""Central OpenAI configuration resolution for every application entry point."""

from __future__ import annotations

import os
from collections.abc import Mapping

OPENAI_API_KEY_ENV = "OPENAI_API_KEY"
OPENAI_MODEL_ENV = "OPENAI_MODEL"
DEFAULT_OPENAI_MODEL = "gpt-4o-mini"


def resolve_openai_api_key(*, environ: Mapping[str, str] | None = None) -> str | None:
    """Return the configured key from the environment, which the ignored `.env` file loads."""
    environment = os.environ if environ is None else environ
    candidate = environment.get(OPENAI_API_KEY_ENV)
    if candidate and candidate.strip():
        return candidate.strip()
    return None


def resolve_openai_model(*, environ: Mapping[str, str] | None = None) -> str:
    """Return the configured model from the environment, or the documented default."""
    environment = os.environ if environ is None else environ
    candidate = environment.get(OPENAI_MODEL_ENV)
    if candidate and candidate.strip():
        return candidate.strip()
    return DEFAULT_OPENAI_MODEL
