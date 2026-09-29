import pytest

from canonical_model_generator.api_analyzer.token_budget import (
    TokenBudget,
    TokenBudgetConfig,
    TokenBudgetExceeded,
)


def test_token_budget_stops_before_request_limit_is_exceeded() -> None:
    budget = TokenBudget(
        "gpt-4o-mini",
        TokenBudgetConfig(
            max_run_tokens=20_000,
            max_requests=1,
            max_input_tokens_per_request=10_000,
            max_output_tokens_per_request=1_000,
        ),
    )
    budget.reserve("system", "first payload")
    budget.record(input_tokens=10, output_tokens=5, produced_result=True)

    with pytest.raises(TokenBudgetExceeded, match="request limit"):
        budget.reserve("system", "second payload")

    assert budget.snapshot()["actualTotalTokens"] == 15
    assert budget.snapshot()["resultsProduced"] == 1
    assert budget.snapshot()["calls"] == [
        {
            "requestNumber": 1,
            "operation": "semantic",
            "status": "completed",
            "estimatedInputTokens": budget.snapshot()["estimatedInputTokens"],
            "maxOutputTokens": 1_000,
            "actualInputTokens": 10,
            "actualOutputTokens": 5,
            "actualTotalTokens": 15,
            "producedResult": True,
        }
    ]


def test_token_budget_reserves_output_before_spending() -> None:
    budget = TokenBudget(
        "gpt-4o-mini",
        TokenBudgetConfig(
            max_run_tokens=1_000,
            max_requests=10,
            max_input_tokens_per_request=10_000,
            max_output_tokens_per_request=1_000,
        ),
    )

    with pytest.raises(TokenBudgetExceeded, match="Projected run usage"):
        budget.reserve("system", "payload")

    assert budget.snapshot()["requestsStarted"] == 0


def test_token_budget_rejects_oversized_input() -> None:
    budget = TokenBudget(
        "gpt-4o-mini",
        TokenBudgetConfig(
            max_run_tokens=20_000,
            max_requests=10,
            max_input_tokens_per_request=2,
            max_output_tokens_per_request=1_000,
        ),
    )

    with pytest.raises(TokenBudgetExceeded, match="per-request limit"):
        budget.reserve("system instructions", "a payload with several tokens")

    assert budget.snapshot()["requestsStarted"] == 0


def test_token_budget_records_failed_call_without_inventing_actual_usage() -> None:
    budget = TokenBudget(
        "gpt-4o-mini",
        TokenBudgetConfig(max_run_tokens=10_000, max_output_tokens_per_request=1_000),
    )
    budget.reserve("system", "payload", operation="EndpointSemantic")
    budget.record_failure()

    call = budget.snapshot()["calls"][0]
    assert call["operation"] == "EndpointSemantic"
    assert call["status"] == "failed-usage-unavailable"
    assert call["actualInputTokens"] is None
    assert call["actualOutputTokens"] is None
