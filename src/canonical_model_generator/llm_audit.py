"""Secret-safe, per-call JSON audit logging for external model requests."""

from __future__ import annotations

import json
import os
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal
from uuid import uuid4

LLM_LOG_DIRECTORY_ENV = "LLM_CALL_LOG_DIRECTORY"
LLM_LOG_SCHEMA_VERSION = "llm-call-log/1.0"


def llm_log_directory() -> Path:
    """Return the configured log root, defaulting to ignored project-local storage."""
    configured = os.getenv(LLM_LOG_DIRECTORY_ENV)
    if configured and configured.strip():
        return Path(configured.strip()).expanduser().resolve()
    return Path(__file__).resolve().parents[2] / ".llm-logs"


def write_llm_call_log(
    *,
    provider: str,
    operation: str,
    model: str,
    status: Literal["completed", "failed"],
    input_tokens: int | None,
    output_tokens: int | None,
    total_tokens: int | None,
    estimated_input_tokens: int | None = None,
    input_items: int | None = None,
    produced_result: bool | None = None,
    provider_request_id: str | None = None,
    error: BaseException | None = None,
) -> Path:
    """Write one atomic JSON file without request content, response content, or credentials."""
    timestamp = datetime.now(UTC)
    call_id = uuid4().hex
    error_status = getattr(error, "status_code", None) if error is not None else None
    record: dict[str, Any] = {
        "schemaVersion": LLM_LOG_SCHEMA_VERSION,
        "callId": call_id,
        "timestampUtc": timestamp.isoformat().replace("+00:00", "Z"),
        "provider": provider,
        "operation": operation,
        "model": model,
        "status": status,
        "usage": {
            "inputTokens": _non_negative_or_none(input_tokens),
            "outputTokens": _non_negative_or_none(output_tokens),
            "totalTokens": _non_negative_or_none(total_tokens),
        },
        "request": {
            "estimatedInputTokens": _non_negative_or_none(estimated_input_tokens),
            "inputItems": _non_negative_or_none(input_items),
        },
        "response": {
            "providerRequestId": provider_request_id,
            "producedResult": produced_result,
        },
        "error": (
            {
                "type": type(error).__name__,
                "httpStatus": error_status if isinstance(error_status, int) else None,
            }
            if error is not None
            else None
        ),
    }
    day_directory = llm_log_directory() / timestamp.date().isoformat()
    day_directory.mkdir(parents=True, exist_ok=True)
    filename = f"{timestamp.strftime('%H%M%S.%fZ')}-{_safe_filename_part(operation)}-{call_id}.json"
    destination = day_directory / filename
    temporary = day_directory / f".{filename}.tmp"
    temporary.write_text(
        json.dumps(record, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    temporary.replace(destination)
    return destination


def usage_token_counts(usage: object | None) -> tuple[int | None, int | None, int | None]:
    """Normalize Responses and Embeddings API usage field names."""
    if usage is None:
        return None, None, None
    input_tokens = getattr(usage, "input_tokens", None)
    if input_tokens is None:
        input_tokens = getattr(usage, "prompt_tokens", None)
    output_tokens = getattr(usage, "output_tokens", None)
    if output_tokens is None and hasattr(usage, "prompt_tokens"):
        output_tokens = 0
    total_tokens = getattr(usage, "total_tokens", None)
    if total_tokens is None and input_tokens is not None and output_tokens is not None:
        total_tokens = int(input_tokens) + int(output_tokens)
    return (
        _non_negative_or_none(input_tokens),
        _non_negative_or_none(output_tokens),
        _non_negative_or_none(total_tokens),
    )


def _non_negative_or_none(value: object) -> int | None:
    if value is None:
        return None
    try:
        return max(0, int(value))
    except (TypeError, ValueError):
        return None


def _safe_filename_part(value: str) -> str:
    safe = "".join(character if character.isalnum() else "-" for character in value.strip())
    return safe.strip("-")[:80] or "call"
