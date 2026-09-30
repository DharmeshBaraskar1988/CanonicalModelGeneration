import json
from types import SimpleNamespace

import openai

from canonical_model_generator.api_analyzer.providers.openai import OpenAISemanticProvider
from canonical_model_generator.canonical_gap import CanonicalGapDraft, OpenAICanonicalGapProvider
from canonical_model_generator.llm_audit import write_llm_call_log
from canonical_model_generator.openai_config import (
    DEFAULT_OPENAI_MODEL,
    resolve_openai_api_key,
    resolve_openai_model,
)


def test_openai_configuration_is_resolved_from_the_environment_only() -> None:
    environment = {"OPENAI_API_KEY": " environment-key ", "OPENAI_MODEL": " env-model "}

    assert resolve_openai_api_key(environ=environment) == "environment-key"
    assert resolve_openai_api_key(environ={"OPENAI_API_KEY": "   "}) is None
    assert resolve_openai_api_key(environ={}) is None
    assert resolve_openai_model(environ=environment) == "env-model"
    assert resolve_openai_model(environ={"OPENAI_MODEL": "   "}) == DEFAULT_OPENAI_MODEL
    assert resolve_openai_model(environ={}) == DEFAULT_OPENAI_MODEL


def test_call_log_contains_token_counts_but_no_request_content(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("LLM_CALL_LOG_DIRECTORY", str(tmp_path))
    destination = write_llm_call_log(
        provider="openai",
        operation="EndpointSemantic",
        model="test-model",
        status="completed",
        input_tokens=123,
        output_tokens=45,
        total_tokens=168,
        estimated_input_tokens=120,
        produced_result=True,
        provider_request_id="request-1",
    )

    record = json.loads(destination.read_text(encoding="utf-8"))
    assert record["usage"] == {
        "inputTokens": 123,
        "outputTokens": 45,
        "totalTokens": 168,
    }
    assert record["request"]["estimatedInputTokens"] == 120
    assert set(record) == {
        "schemaVersion",
        "callId",
        "timestampUtc",
        "provider",
        "operation",
        "model",
        "status",
        "usage",
        "request",
        "response",
        "error",
    }
    assert "prompt" not in destination.read_text(encoding="utf-8").casefold()


def test_structured_response_and_gap_calls_each_write_a_json_log(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("LLM_CALL_LOG_DIRECTORY", str(tmp_path))
    responses = [
        SimpleNamespace(
            id="semantic-request",
            usage=SimpleNamespace(input_tokens=11, output_tokens=7, total_tokens=18),
            output_parsed="semantic-result",
        ),
        SimpleNamespace(
            id="gap-request",
            usage=SimpleNamespace(input_tokens=13, output_tokens=9, total_tokens=22),
            output_parsed=CanonicalGapDraft(
                name="Policy",
                description="A policy contract.",
                type="object",
                constraints_json="{}",
                rationale="Supported by the supplied regional item.",
            ),
        ),
    ]
    client = SimpleNamespace(
        responses=SimpleNamespace(parse=lambda **kwargs: responses.pop(0)),
        models=SimpleNamespace(retrieve=lambda model: None),
    )
    monkeypatch.setattr(openai, "OpenAI", lambda **kwargs: client)

    semantic = OpenAISemanticProvider(api_key="never-written", model="test-model")
    assert semantic._parse(str, "instructions", {"private": "request content"}) == (
        "semantic-result"
    )
    gap = OpenAICanonicalGapProvider(api_key="never-written", model="test-model")
    assert gap.generate({"private": "gap content"})["name"] == "Policy"

    logs = sorted(tmp_path.rglob("*.json"))
    assert len(logs) == 2
    records = [json.loads(path.read_text(encoding="utf-8")) for path in logs]
    assert {record["operation"] for record in records} == {"str", "CanonicalGapDraft"}
    assert {record["usage"]["totalTokens"] for record in records} == {18, 22}
    serialized = json.dumps(records)
    assert "never-written" not in serialized
    assert "request content" not in serialized
    assert "gap content" not in serialized


def test_failed_structured_response_call_is_logged_without_error_text(
    tmp_path, monkeypatch
) -> None:
    monkeypatch.setenv("LLM_CALL_LOG_DIRECTORY", str(tmp_path))

    def fail(**kwargs):
        raise RuntimeError("provider echoed a private credential")

    client = SimpleNamespace(
        responses=SimpleNamespace(parse=fail),
        models=SimpleNamespace(retrieve=lambda model: None),
    )
    monkeypatch.setattr(openai, "OpenAI", lambda **kwargs: client)
    provider = OpenAISemanticProvider(api_key="never-written", model="test-model")

    try:
        provider._parse(str, "instructions", {"private": "request content"})
    except RuntimeError:
        pass

    logs = list(tmp_path.rglob("*.json"))
    assert len(logs) == 1
    serialized = logs[0].read_text(encoding="utf-8")
    record = json.loads(serialized)
    assert record["status"] == "failed"
    assert record["usage"] == {
        "inputTokens": None,
        "outputTokens": None,
        "totalTokens": None,
    }
    assert record["error"] == {"httpStatus": None, "type": "RuntimeError"}
    assert "private credential" not in serialized
