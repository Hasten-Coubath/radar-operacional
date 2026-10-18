"""Testes do OllamaProvider com transporte falso: nenhuma chamada ao servidor."""

from __future__ import annotations

import json
import urllib.error
import urllib.request
from typing import Any

import pytest
from pydantic import BaseModel

from src.llm.providers import OllamaError, OllamaProvider, http_post_json, make_provider
from src.llm.types import LLMRequest, LLMResponse

MODEL = "qwen3:4b"


class Classe(BaseModel):
    causa: str
    confianca: float


class FakeTransport:
    def __init__(self, reply: dict[str, Any]) -> None:
        self.reply = reply
        self.calls: list[tuple[str, dict[str, Any], float]] = []

    def __call__(self, url: str, payload: dict[str, Any], timeout_s: float) -> dict[str, Any]:
        self.calls.append((url, payload, timeout_s))
        return self.reply


def ollama_reply(**message: Any) -> dict[str, Any]:
    return {
        "model": MODEL,
        "message": {"role": "assistant", "content": "", **message},
        "done": True,
        "done_reason": "stop",
        "total_duration": 2_500_000_000,
        "load_duration": 1_000_000_000,
        "prompt_eval_count": 120,
        "prompt_eval_duration": 300_000_000,
        "eval_count": 30,
        "eval_duration": 1_200_000_000,
    }


def req(**update: Any) -> LLMRequest:
    base = LLMRequest(
        model=MODEL,
        max_tokens=512,
        system="classifique",
        messages=[{"role": "user", "content": "chegou quebrado"}],
        think=False,
        options={"num_ctx": 4096, "temperature": 0, "seed": 42},
    )
    return base.model_copy(update=update)


def test_payload_structured_output_without_thinking() -> None:
    transport = FakeTransport(ollama_reply(content='{"causa": "x", "confianca": 0.9}'))
    provider = OllamaProvider(base_url="http://h:1/", keep_alive="5m", transport=transport)
    response = provider.generate(req(output_schema=Classe.model_json_schema()))

    url, payload, _ = transport.calls[0]
    assert url == "http://h:1/api/chat"
    assert payload["stream"] is False and payload["think"] is False
    assert payload["format"] == Classe.model_json_schema()
    assert payload["options"] == {"num_ctx": 4096, "temperature": 0, "seed": 42, "num_predict": 512}
    assert payload["keep_alive"] == "5m"
    assert payload["messages"] == [
        {"role": "system", "content": "classifique"},
        {"role": "user", "content": "chegou quebrado"},
    ]
    assert "tools" not in payload

    assert Classe.model_validate_json(response.text).causa == "x"
    assert response.stop_reason == "end_turn" and response.thinking == ""
    assert (response.usage.input_tokens, response.usage.output_tokens) == (120, 30)
    assert response.timings == {
        "total_s": 2.5,
        "load_s": 1.0,
        "prompt_eval_s": 0.3,
        "eval_s": 1.2,
    }
    assert LLMResponse.model_validate(json.loads(response.model_dump_json())) == response


def test_optional_fields_are_omitted() -> None:
    payload = OllamaProvider.build_payload(req(think=None, options=None, system=None))
    assert set(payload) == {"model", "messages", "stream", "options"}
    assert payload["options"] == {"num_predict": 512}


def test_effort_is_rejected() -> None:
    with pytest.raises(ValueError):
        OllamaProvider.build_payload(req(effort="low"))


def test_thinking_and_truncation_are_mapped() -> None:
    reply = ollama_reply(content="{", thinking="hmm") | {"done_reason": "length"}
    response = OllamaProvider.parse_response(reply, latency_s=1.0)
    assert response.content[0] == {"type": "thinking", "thinking": "hmm"}
    assert response.thinking == "hmm" and response.text == "{"
    assert response.stop_reason == "max_tokens"


def test_tool_call_roundtrip() -> None:
    """Ferramentas: definição, chamada devolvida e resultado reenviado no histórico."""
    tool = {
        "name": "query_sql",
        "description": "Executa um SELECT",
        "input_schema": {"type": "object", "properties": {"sql": {"type": "string"}}},
    }
    reply = ollama_reply(
        tool_calls=[{"function": {"name": "query_sql", "arguments": {"sql": "SELECT 1"}}}]
    )
    transport = FakeTransport(reply)
    response = OllamaProvider(transport=transport).generate(req(tools=[tool]))

    assert transport.calls[0][1]["tools"] == [
        {
            "type": "function",
            "function": {
                "name": "query_sql",
                "description": "Executa um SELECT",
                "parameters": tool["input_schema"],
            },
        }
    ]
    assert response.stop_reason == "tool_use"
    (call,) = response.tool_uses
    assert call["name"] == "query_sql" and call["input"] == {"sql": "SELECT 1"}

    history = [
        {"role": "user", "content": "investigue"},
        {"role": "assistant", "content": response.content},
        {
            "role": "user",
            "content": [{"type": "tool_result", "tool_use_id": call["id"], "content": "1"}],
        },
    ]
    messages = OllamaProvider.build_payload(req(system=None, messages=history))["messages"]
    assert messages == [
        {"role": "user", "content": "investigue"},
        {
            "role": "assistant",
            "content": "",
            "tool_calls": [{"function": {"name": "query_sql", "arguments": {"sql": "SELECT 1"}}}],
        },
        {"role": "tool", "tool_name": "query_sql", "content": "1"},
    ]


def test_string_tool_arguments_are_decoded() -> None:
    reply = ollama_reply(tool_calls=[{"function": {"name": "f", "arguments": '{"a": 1}'}}])
    assert OllamaProvider.parse_response(reply, 0.1).tool_uses[0]["input"] == {"a": 1}


def test_thinking_blocks_are_not_resent() -> None:
    history = [
        {"role": "user", "content": "oi"},
        {
            "role": "assistant",
            "content": [{"type": "thinking", "thinking": "..."}, {"type": "text", "text": "olá"}],
        },
    ]
    messages = OllamaProvider.build_payload(req(system=None, messages=history))["messages"]
    assert messages[1] == {"role": "assistant", "content": "olá"}


def test_unreachable_server_raises_clear_error(monkeypatch: pytest.MonkeyPatch) -> None:
    def refuse(*args: Any, **kwargs: Any) -> Any:
        raise urllib.error.URLError("connection refused")

    monkeypatch.setattr(urllib.request, "urlopen", refuse)
    with pytest.raises(OllamaError, match="ollama serve"):
        http_post_json("http://localhost:11434/api/chat", {}, 1.0)


def test_make_provider_reads_settings() -> None:
    provider = make_provider("ollama", {"base_url": "http://gpu:11434", "keep_alive": "1m"})
    assert isinstance(provider, OllamaProvider) and provider.base_url == "http://gpu:11434"
    with pytest.raises(ValueError):
        make_provider("desconhecido")
