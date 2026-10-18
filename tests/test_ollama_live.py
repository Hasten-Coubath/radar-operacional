"""Teste real com o Ollama local: um único item, sem custo.

Fora da execução padrão do pytest. Rode com `pytest -m ollama`. É pulado se o servidor não
responder ou se o modelo configurado não estiver baixado.
"""

from __future__ import annotations

import json
import urllib.request
from pathlib import Path
from typing import Literal

import pytest
from pydantic import BaseModel, Field

from src.config import load_config
from src.llm.client import LLMClient

pytestmark = pytest.mark.ollama

# Texto escrito para o teste (não vem do dataset, para não tocar em dados de avaliação).
REVIEW = "Comprei faz um mês, o prazo era de 10 dias e até agora nada de chegar. Péssimo."


class CausaTeste(BaseModel):
    causa: Literal["atraso_entrega", "produto_defeituoso", "elogio", "outro"]
    confianca: float = Field(ge=0, le=1)


@pytest.fixture(scope="module")
def cfg() -> dict[str, object]:
    cfg = load_config()
    llm = cfg["llm"]
    if llm["provider"] != "ollama":
        pytest.skip("provedor configurado não é ollama")
    base_url = llm["providers"]["ollama"]["base_url"].rstrip("/")
    try:
        with urllib.request.urlopen(f"{base_url}/api/tags", timeout=3) as resp:
            tags = json.loads(resp.read())
    except OSError as e:
        pytest.skip(f"Ollama não responde em {base_url}: {e}")
    model = llm["roles"]["classifier"]["model"]
    names = {m["name"] for m in tags.get("models", [])}
    if model not in names and f"{model}:latest" not in names:
        pytest.skip(f"modelo {model} não está baixado (ollama pull {model})")
    return cfg


def make_client(cfg: dict[str, object], tmp_path: Path) -> LLMClient:
    llm = dict(cfg["llm"])  # type: ignore[call-overload]
    llm.update(cache_dir=str(tmp_path / "cache"), usage_log=str(tmp_path / "usage.jsonl"))
    return LLMClient.from_config({**cfg, "llm": llm})


def test_structured_classification_one_item(cfg: dict[str, object], tmp_path: Path) -> None:
    client = make_client(cfg, tmp_path)
    request = client.request_for(
        "classifier",
        [{"role": "user", "content": f"Avaliação: {REVIEW}"}],
        system="Classifique a causa da avaliação. Responda só com JSON: "
        + json.dumps(CausaTeste.model_json_schema(), ensure_ascii=False),
    )
    out = client.generate_structured(request, CausaTeste, tag="teste_ollama")

    assert out.parsed is not None, out.errors
    first = out.attempts[0].response
    print(f"\n{out.parsed} | {first.usage} | {out.latency_s:.2f}s | {first.timings}")
    assert first.thinking == "", "think=false deveria desligar o raciocínio"
    assert first.usage.output_tokens > 0 and out.latency_s > 0
    assert out.attempts[0].cost_usd_live == 0.0

    again = client.generate_structured(request, CausaTeste, tag="teste_ollama")
    assert again.parsed == out.parsed and again.attempts[0].cached


def test_tool_call_one_item(cfg: dict[str, object], tmp_path: Path) -> None:
    """Verifica que o modelo devolve uma chamada de ferramenta válida (base da Fase 8)."""
    client = make_client(cfg, tmp_path)
    tool = {
        "name": "query_sql",
        "description": "Executa uma consulta SELECT no banco e devolve as linhas.",
        "input_schema": {
            "type": "object",
            "properties": {"sql": {"type": "string", "description": "consulta SELECT"}},
            "required": ["sql"],
        },
    }
    request = client.request_for(
        "classifier",
        [
            {
                "role": "user",
                "content": "Quantos pedidos existem na tabela orders? Use a ferramenta.",
            }
        ],
        tools=[tool],
    )
    result = client.generate(request, tag="teste_ollama")
    print(f"\n{result.response.content} | {result.response.latency_s:.2f}s")
    assert result.response.stop_reason == "tool_use"
    call = result.response.tool_uses[0]
    assert call["name"] == "query_sql" and "select" in call["input"]["sql"].lower()
