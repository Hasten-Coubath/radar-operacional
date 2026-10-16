"""Provedores de LLM. Cada um traduz `LLMRequest` para a API real e de volta."""

from __future__ import annotations

import time
from typing import Any, Protocol

from src.llm.types import LLMRequest, LLMResponse, LLMUsage


class LLMProvider(Protocol):
    name: str

    def generate(self, request: LLMRequest) -> LLMResponse: ...


class AnthropicProvider:
    """Messages API da Anthropic via SDK oficial. O cliente da SDK é criado sob demanda."""

    name = "anthropic"

    def __init__(self, *, timeout_s: float = 60.0, max_retries: int = 2, client: Any = None):
        self._timeout_s = timeout_s
        self._max_retries = max_retries
        self._client = client

    @property
    def client(self) -> Any:
        if self._client is None:
            import anthropic

            self._client = anthropic.Anthropic(
                timeout=self._timeout_s, max_retries=self._max_retries
            )
        return self._client

    @staticmethod
    def build_params(request: LLMRequest) -> dict[str, Any]:
        """Monta os kwargs de `messages.create`. O schema vira o formato estrito da API."""
        import anthropic

        params: dict[str, Any] = {
            "model": request.model,
            "max_tokens": request.max_tokens,
            "messages": request.messages,
        }
        if request.system:
            params["system"] = request.system
        if request.tools:
            params["tools"] = request.tools
        output_config: dict[str, Any] = {}
        if request.effort:
            output_config["effort"] = request.effort
        if request.output_schema:
            output_config["format"] = {
                "type": "json_schema",
                "schema": anthropic.transform_schema(request.output_schema),
            }
        if output_config:
            params["output_config"] = output_config
        return params

    def generate(self, request: LLMRequest) -> LLMResponse:
        params = self.build_params(request)
        start = time.perf_counter()
        msg = self.client.messages.create(**params)
        latency = time.perf_counter() - start
        usage = msg.usage
        return LLMResponse(
            content=[block.model_dump(mode="json", exclude_none=True) for block in msg.content],
            stop_reason=msg.stop_reason,
            model=msg.model,
            usage=LLMUsage(
                input_tokens=usage.input_tokens,
                output_tokens=usage.output_tokens,
                cache_read_input_tokens=usage.cache_read_input_tokens or 0,
                cache_creation_input_tokens=usage.cache_creation_input_tokens or 0,
            ),
            latency_s=latency,
            request_id=getattr(msg, "_request_id", None),
        )


def make_provider(name: str, *, timeout_s: float, max_retries: int) -> LLMProvider:
    if name == "anthropic":
        return AnthropicProvider(timeout_s=timeout_s, max_retries=max_retries)
    raise ValueError(f"Provedor de LLM desconhecido: {name!r}")
