"""Deterministic token budgeting for paid semantic-provider calls."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any

import tiktoken


class TokenBudgetExceeded(RuntimeError):
    """Raised before a provider call that would exceed the configured run budget."""


@dataclass(frozen=True)
class TokenBudgetConfig:
    max_run_tokens: int = 120_000
    max_requests: int = 100
    max_input_tokens_per_request: int = 24_000
    max_output_tokens_per_request: int = 4_000

    def __post_init__(self) -> None:
        for name, value in asdict(self).items():
            if value <= 0:
                raise ValueError(f"{name} must be greater than zero")


class TokenBudget:
    """Estimate before sending and record provider-reported usage after completion."""

    def __init__(self, model: str, config: TokenBudgetConfig | None = None) -> None:
        self.model = model
        self.config = config or TokenBudgetConfig()
        try:
            self._encoding = tiktoken.encoding_for_model(model)
        except KeyError:
            self._encoding = tiktoken.get_encoding("o200k_base")
        self.requests_started = 0
        self.requests_completed = 0
        self.results_produced = 0
        self.estimated_input_tokens = 0
        self._pending_estimates: list[int] = []
        self.actual_input_tokens = 0
        self.actual_output_tokens = 0
        self.calls: list[dict[str, Any]] = []

    def reserve(self, instructions: str, payload: str, *, operation: str = "semantic") -> int:
        estimated = len(self._encoding.encode(instructions)) + len(self._encoding.encode(payload))
        if estimated > self.config.max_input_tokens_per_request:
            raise TokenBudgetExceeded(
                f"Estimated request input ({estimated} tokens) exceeds the per-request limit "
                f"({self.config.max_input_tokens_per_request})."
            )
        if self.requests_started >= self.config.max_requests:
            raise TokenBudgetExceeded(
                f"Run request limit reached ({self.config.max_requests}); no further paid calls "
                "will be made."
            )
        committed = self.actual_input_tokens + self.actual_output_tokens
        projected = (
            committed
            + sum(self._pending_estimates)
            + estimated
            + self.config.max_output_tokens_per_request
        )
        if projected > self.config.max_run_tokens:
            raise TokenBudgetExceeded(
                f"Projected run usage ({projected} tokens) exceeds the run limit "
                f"({self.config.max_run_tokens}); no further paid calls will be made."
            )
        self.requests_started += 1
        self.estimated_input_tokens += estimated
        self._pending_estimates.append(estimated)
        self.calls.append(
            {
                "requestNumber": self.requests_started,
                "operation": operation,
                "status": "started",
                "estimatedInputTokens": estimated,
                "maxOutputTokens": self.config.max_output_tokens_per_request,
                "actualInputTokens": None,
                "actualOutputTokens": None,
                "actualTotalTokens": None,
                "producedResult": False,
            }
        )
        return estimated

    def record(self, *, input_tokens: int, output_tokens: int, produced_result: bool) -> None:
        self.requests_completed += 1
        if self._pending_estimates:
            self._pending_estimates.pop()
        self.actual_input_tokens += max(0, input_tokens)
        self.actual_output_tokens += max(0, output_tokens)
        if produced_result:
            self.results_produced += 1
        call = self.calls[-1]
        call.update(
            {
                "status": "completed",
                "actualInputTokens": max(0, input_tokens),
                "actualOutputTokens": max(0, output_tokens),
                "actualTotalTokens": max(0, input_tokens) + max(0, output_tokens),
                "producedResult": produced_result,
            }
        )

    def record_failure(self) -> None:
        """Retain an attempted call whose provider usage could not be obtained."""
        if self.calls and self.calls[-1]["status"] == "started":
            self.calls[-1]["status"] = "failed-usage-unavailable"

    def snapshot(self) -> dict[str, Any]:
        return {
            "model": self.model,
            "requestsStarted": self.requests_started,
            "requestsCompleted": self.requests_completed,
            "resultsProduced": self.results_produced,
            "estimatedInputTokens": self.estimated_input_tokens,
            "actualInputTokens": self.actual_input_tokens,
            "actualOutputTokens": self.actual_output_tokens,
            "actualTotalTokens": self.actual_input_tokens + self.actual_output_tokens,
            "calls": [dict(item) for item in self.calls],
            "limits": {
                "maxRunTokens": self.config.max_run_tokens,
                "maxRequests": self.config.max_requests,
                "maxInputTokensPerRequest": self.config.max_input_tokens_per_request,
                "maxOutputTokensPerRequest": self.config.max_output_tokens_per_request,
            },
        }
