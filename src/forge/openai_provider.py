"""Pinned OpenAI provider boundary for planner/reflection calls.

No network call occurs unless OPENAI_API_KEY is configured and a caller invokes
complete(). The model is explicit and recorded with every result.
"""
from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any, Protocol, cast

from dotenv import load_dotenv


class ProviderError(RuntimeError):
    def __init__(self, kind: str, message: str):
        super().__init__(message)
        self.kind = kind


@dataclass(frozen=True)
class ModelResponse:
    model: str
    text: str
    input_tokens: int | None = None
    output_tokens: int | None = None


class CompletionClient(Protocol):
    responses: Any


@dataclass
class OpenAIProvider:
    api_key: str | None = None
    base_url: str | None = None
    model: str | None = None
    client: CompletionClient | None = None
    timeout_s: float = 60.0
    load_env: bool = True

    def __post_init__(self):
        if self.load_env:
            load_dotenv(override=False)
        self.api_key = self.api_key or os.getenv("OPENAI_API_KEY")
        self.base_url = self.base_url or os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1")
        self.model = self.model or os.getenv("OPENAI_MODEL", "gpt-5-nano")

    @property
    def configured(self) -> bool:
        return bool(self.api_key)

    def complete(self, *, instructions: str, input_text: str, response_schema: dict[str, Any] | None = None) -> ModelResponse:
        if not self.api_key:
            raise ProviderError("missing_credentials", "OPENAI_API_KEY is not configured")
        client = self.client
        if client is None:
            try:
                import neatlogs
                from openai import OpenAI
                client = neatlogs.wrap(OpenAI(api_key=self.api_key, base_url=self.base_url, timeout=self.timeout_s))
            except ImportError as exc:
                raise ProviderError("missing_sdk", "openai package is not installed") from exc
        try:
            request: dict[str, Any] = {
                "model": cast(str, self.model),
                "instructions": instructions,
                "input": input_text,
            }
            if response_schema is not None:
                request["text"] = {
                    "format": {
                        "type": "json_schema",
                        "name": "forge_skill_candidate",
                        "strict": True,
                        "schema": response_schema,
                    }
                }
            response = client.responses.create(**request)
        except Exception as exc:
            name = type(exc).__name__.lower()
            kind = "rate_limit" if "rate" in name else "provider_error"
            raise ProviderError(kind, f"OpenAI request failed: {type(exc).__name__}") from exc
        text = getattr(response, "output_text", None)
        if not text:
            raise ProviderError("invalid_response", "OpenAI response did not contain output_text")
        usage = getattr(response, "usage", None)
        return ModelResponse(
            model=cast(str, self.model),
            text=text,
            input_tokens=getattr(usage, "input_tokens", None),
            output_tokens=getattr(usage, "output_tokens", None),
        )
