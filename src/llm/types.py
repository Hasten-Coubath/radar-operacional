"""Tipos independentes de provedor para requisições e respostas de LLM."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict

Effort = Literal["low", "medium", "high", "xhigh", "max"]


class LLMRequest(BaseModel):
    """Tudo o que influencia a saída do modelo. É também a base da chave de cache."""

    model_config = ConfigDict(frozen=True)

    model: str
    messages: list[dict[str, Any]]
    max_tokens: int
    system: str | None = None
    tools: list[dict[str, Any]] | None = None
    output_schema: dict[str, Any] | None = None  # JSON Schema (Pydantic) da saída esperada
    effort: Effort | None = None

    def cache_key(self, provider: str) -> str:
        """SHA-256 do JSON canônico (provedor + modelo + prompt + entrada + parâmetros)."""
        payload = {"provider": provider, **self.model_dump(mode="json")}
        blob = json.dumps(payload, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
        return hashlib.sha256(blob.encode("utf-8")).hexdigest()


class LLMUsage(BaseModel):
    input_tokens: int = 0
    output_tokens: int = 0
    cache_read_input_tokens: int = 0
    cache_creation_input_tokens: int = 0


class LLMResponse(BaseModel):
    """Resposta serializável: blocos de conteúdo como dicts, para caber no cache em disco."""

    content: list[dict[str, Any]]
    stop_reason: str | None
    model: str
    usage: LLMUsage
    latency_s: float
    request_id: str | None = None

    @property
    def text(self) -> str:
        return "".join(b.get("text", "") for b in self.content if b.get("type") == "text")

    @property
    def tool_uses(self) -> list[dict[str, Any]]:
        return [b for b in self.content if b.get("type") == "tool_use"]


@dataclass(frozen=True)
class LLMResult:
    """Resposta mais metadados da chamada: chave de cache, hit/miss e custo."""

    response: LLMResponse
    cache_key: str
    cached: bool
    cost_usd_live: float | None  # quanto essa resposta custou (ou custaria) na API

    @property
    def cost_usd_spent(self) -> float | None:
        """Custo efetivamente gasto nesta execução (zero em cache hit)."""
        return 0.0 if self.cached else self.cost_usd_live
