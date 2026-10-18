"""Provedores de LLM. Cada um traduz `LLMRequest` para a API real e de volta.

O formato interno de mensagens e de conteúdo é o da Messages API da Anthropic (blocos `text`,
`thinking`, `tool_use`, `tool_result`); o `OllamaProvider` converte de/para a API do Ollama,
para que o resto do projeto (inclusive o loop do agente) não dependa do provedor.
"""

from __future__ import annotations

import json
import time
import urllib.error
import urllib.request
from collections.abc import Callable
from typing import Any, Protocol

from src.llm.types import LLMRequest, LLMResponse, LLMUsage


class LLMProvider(Protocol):
    name: str

    def generate(self, request: LLMRequest) -> LLMResponse: ...


# --- Ollama (padrão: local, custo zero) ---

# (url, payload, timeout_s) -> JSON da resposta
Transport = Callable[[str, dict[str, Any], float], dict[str, Any]]

_STOP_REASONS = {"stop": "end_turn", "length": "max_tokens"}
_TIMINGS = {
    "total_duration": "total_s",
    "load_duration": "load_s",
    "prompt_eval_duration": "prompt_eval_s",
    "eval_duration": "eval_s",
}


class OllamaError(RuntimeError):
    """Falha de comunicação com o servidor do Ollama (fora do ar, modelo ausente, HTTP 4xx/5xx)."""


def http_post_json(url: str, payload: dict[str, Any], timeout_s: float) -> dict[str, Any]:
    """POST JSON com a biblioteca padrão (sem dependência extra)."""
    req = urllib.request.Request(
        url,
        data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout_s) as resp:
            data: dict[str, Any] = json.loads(resp.read().decode("utf-8"))
            return data
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", "replace")[:500]
        raise OllamaError(f"HTTP {e.code} em {url}: {body}") from e
    except urllib.error.URLError as e:
        raise OllamaError(
            f"Ollama inacessível em {url} ({e.reason}). O servidor está rodando (`ollama serve`)?"
        ) from e


class OllamaProvider:
    """API `/api/chat` do Ollama, sem streaming.

    Saída estruturada via `format` (JSON Schema, decodificação restrita por gramática) e
    ferramentas via `tools`. `max_tokens` vira `options.num_predict`; o restante de
    `request.options` (num_ctx, temperature, seed...) é repassado como está.
    """

    name = "ollama"

    def __init__(
        self,
        *,
        base_url: str = "http://localhost:11434",
        timeout_s: float = 120.0,
        keep_alive: str | None = None,
        transport: Transport | None = None,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self._timeout_s = timeout_s
        self._keep_alive = keep_alive
        self._transport = transport or http_post_json

    @staticmethod
    def build_payload(request: LLMRequest, *, keep_alive: str | None = None) -> dict[str, Any]:
        if request.effort is not None:
            raise ValueError("Ollama não tem `effort`; use `think` e `options` no papel.")
        payload: dict[str, Any] = {
            "model": request.model,
            "messages": _to_ollama_messages(request),
            "stream": False,
            "options": {**(request.options or {}), "num_predict": request.max_tokens},
        }
        if request.think is not None:
            payload["think"] = request.think
        if request.output_schema:
            payload["format"] = request.output_schema
        if request.tools:
            payload["tools"] = [_to_ollama_tool(t) for t in request.tools]
        if keep_alive:
            payload["keep_alive"] = keep_alive
        return payload

    @staticmethod
    def parse_response(data: dict[str, Any], latency_s: float) -> LLMResponse:
        msg = data.get("message") or {}
        content: list[dict[str, Any]] = []
        if msg.get("thinking"):
            content.append({"type": "thinking", "thinking": msg["thinking"]})
        if msg.get("content"):
            content.append({"type": "text", "text": msg["content"]})
        for i, call in enumerate(msg.get("tool_calls") or []):
            fn = call.get("function") or {}
            args = fn.get("arguments") or {}
            if isinstance(args, str):
                try:
                    args = json.loads(args)
                except json.JSONDecodeError:
                    args = {"_raw": args}
            content.append(
                {
                    "type": "tool_use",
                    "id": call.get("id") or f"call_{i}",
                    "name": fn.get("name", ""),
                    "input": args,
                }
            )
        done_reason = data.get("done_reason")
        if any(b["type"] == "tool_use" for b in content):
            stop_reason: str | None = "tool_use"
        else:
            stop_reason = _STOP_REASONS.get(done_reason or "", done_reason)
        return LLMResponse(
            content=content,
            stop_reason=stop_reason,
            model=data.get("model", ""),
            usage=LLMUsage(
                input_tokens=data.get("prompt_eval_count") or 0,
                output_tokens=data.get("eval_count") or 0,
            ),
            latency_s=latency_s,
            timings={v: data[k] / 1e9 for k, v in _TIMINGS.items() if k in data},
        )

    def generate(self, request: LLMRequest) -> LLMResponse:
        payload = self.build_payload(request, keep_alive=self._keep_alive)
        start = time.perf_counter()
        data = self._transport(f"{self.base_url}/api/chat", payload, self._timeout_s)
        return self.parse_response(data, time.perf_counter() - start)


def _to_ollama_tool(tool: dict[str, Any]) -> dict[str, Any]:
    """Ferramenta no formato Anthropic (`input_schema`) -> formato de função do Ollama."""
    return {
        "type": "function",
        "function": {
            "name": tool["name"],
            "description": tool.get("description", ""),
            "parameters": tool["input_schema"],
        },
    }


def _to_ollama_messages(request: LLMRequest) -> list[dict[str, Any]]:
    """Mensagens com blocos (formato Anthropic) -> mensagens do Ollama.

    `tool_result` vira uma mensagem `role: tool` com o nome da ferramenta chamada; blocos de
    raciocínio anteriores não são reenviados (o template do Qwen3 os descarta do histórico).
    """
    out: list[dict[str, Any]] = []
    if request.system:
        out.append({"role": "system", "content": request.system})
    tool_names: dict[str, str] = {}
    for m in request.messages:
        content = m["content"]
        if isinstance(content, str):
            out.append({"role": m["role"], "content": content})
            continue
        texts: list[str] = []
        calls: list[dict[str, Any]] = []
        results: list[dict[str, Any]] = []
        for block in content:
            kind = block.get("type")
            if kind == "text":
                texts.append(block["text"])
            elif kind == "tool_use":
                tool_names[block["id"]] = block["name"]
                calls.append(
                    {"function": {"name": block["name"], "arguments": block.get("input", {})}}
                )
            elif kind == "tool_result":
                results.append(block)
            elif kind != "thinking":
                raise ValueError(f"Bloco de conteúdo não suportado no Ollama: {kind!r}")
        for r in results:
            out.append(
                {
                    "role": "tool",
                    "tool_name": tool_names.get(r["tool_use_id"], ""),
                    "content": _block_text(r.get("content", "")),
                }
            )
        if texts or calls or not results:
            msg: dict[str, Any] = {"role": m["role"], "content": "\n".join(texts)}
            if calls:
                msg["tool_calls"] = calls
            out.append(msg)
    return out


def _block_text(content: Any) -> str:
    if isinstance(content, str):
        return content
    return "".join(b.get("text", "") for b in content if b.get("type") == "text")


# --- Anthropic (opcional, pago) ---


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

        if request.options:
            raise ValueError(
                "`options` (amostragem, num_ctx) não se aplica à Anthropic; remova do papel."
            )
        params: dict[str, Any] = {
            "model": request.model,
            "max_tokens": request.max_tokens,
            "messages": request.messages,
        }
        if request.system:
            params["system"] = request.system
        if request.tools:
            params["tools"] = request.tools
        if request.think is not None:
            params["thinking"] = {"type": "adaptive" if request.think else "disabled"}
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


def make_provider(name: str, settings: dict[str, Any] | None = None) -> LLMProvider:
    """Cria o provedor pelo nome, com os parâmetros de `llm.providers.<nome>` do config."""
    s = settings or {}
    if name == "ollama":
        return OllamaProvider(
            base_url=s.get("base_url", "http://localhost:11434"),
            timeout_s=s.get("timeout_s", 120.0),
            keep_alive=s.get("keep_alive"),
        )
    if name == "anthropic":
        return AnthropicProvider(
            timeout_s=s.get("timeout_s", 60.0), max_retries=s.get("max_retries", 2)
        )
    raise ValueError(f"Provedor de LLM desconhecido: {name!r}")
