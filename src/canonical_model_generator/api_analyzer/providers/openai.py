"""OpenAI Responses API adapter for the API Analyzer."""

from __future__ import annotations

import json
from typing import Any

from canonical_model_generator.api_analyzer.contracts import (
    CodeSemantic,
    EndpointSemantic,
    EntitySemantic,
    EnumSemantic,
    NormalizedEntity,
)
from canonical_model_generator.api_analyzer.prompts import (
    CODE_SYSTEM_PROMPT,
    ENDPOINT_SYSTEM_PROMPT,
    ENTITY_SYSTEM_PROMPT,
    ENUM_SYSTEM_PROMPT,
    NORMALIZATION_SYSTEM_PROMPT,
)


class OpenAISemanticProvider:
    """OpenAI adapter using Pydantic Structured Outputs."""

    def __init__(self, *, api_key: str, model: str = "gpt-4o-mini") -> None:
        from openai import OpenAI

        self._client = OpenAI(api_key=api_key.strip(), max_retries=2)
        self._model = model

    @property
    def model_name(self) -> str:
        return self._model

    def validate_connection(self) -> None:
        self._client.models.retrieve(self._model)

    def analyze_endpoint(self, context: dict[str, Any]) -> EndpointSemantic:
        return self._parse(EndpointSemantic, ENDPOINT_SYSTEM_PROMPT, context)

    def analyze_entity(self, context: dict[str, Any]) -> EntitySemantic:
        return self._parse(EntitySemantic, ENTITY_SYSTEM_PROMPT, context)

    def analyze_enum(self, context: dict[str, Any]) -> EnumSemantic:
        return self._parse(EnumSemantic, ENUM_SYSTEM_PROMPT, context)

    def analyze_code(self, context: dict[str, Any]) -> CodeSemantic:
        return self._parse(CodeSemantic, CODE_SYSTEM_PROMPT, context)

    def normalize_entity(self, context: dict[str, Any]) -> NormalizedEntity:
        return self._parse(NormalizedEntity, NORMALIZATION_SYSTEM_PROMPT, context)

    def _parse(self, output_type: type[Any], instructions: str, context: dict[str, Any]) -> Any:
        response = self._client.responses.parse(
            model=self._model,
            input=[
                {"role": "system", "content": instructions},
                {"role": "user", "content": json.dumps(context, indent=2, sort_keys=True)},
            ],
            text_format=output_type,
        )
        if response.output_parsed is None:
            raise RuntimeError("OpenAI returned no schema-valid semantic result")
        return response.output_parsed
