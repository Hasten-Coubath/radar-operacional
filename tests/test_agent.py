"""Loop do agente e verificador com provedor roteirizado (sem chamadas ao Ollama)."""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any

import pytest

from src.agent.investigator import Alert, investigate
from src.agent.sql import ReadOnlySQL
from src.agent.verify import Briefing, Claim, same_value, unsupported_numbers, verify
from src.llm.cache import DiskCache
from src.llm.client import LLMClient, RoleSettings
from src.llm.cost import ModelPricing, PriceTable, UsageLogger
from src.llm.types import LLMRequest, LLMResponse, LLMUsage


class ScriptedProvider:
    """Devolve blocos roteirizados; registra as requisições."""

    name = "roteiro"

    def __init__(self, script: list[list[dict[str, Any]]]) -> None:
        self.script = script
        self.calls: list[LLMRequest] = []

    def generate(self, request: LLMRequest) -> LLMResponse:
        content = self.script[min(len(self.calls), len(self.script) - 1)]
        self.calls.append(request)
        stop = "tool_use" if any(b["type"] == "tool_use" for b in content) else "end_turn"
        return LLMResponse(
            content=content, stop_reason=stop, model=request.model, usage=LLMUsage(), latency_s=0.1
        )


@pytest.fixture
def sql(tmp_path: Path) -> ReadOnlySQL:
    path = tmp_path / "t.db"
    con = sqlite3.connect(path)
    con.execute("CREATE TABLE reviews (review_id TEXT, review_score INT, answered_week TEXT)")
    rows = [(f"r{i}", 1 if i < 30 else 5, "2018-04-02") for i in range(100)]
    con.executemany("INSERT INTO reviews VALUES (?, ?, ?)", rows)
    con.commit()
    con.close()
    return ReadOnlySQL(path)


def client(tmp_path: Path, provider: ScriptedProvider) -> LLMClient:
    return LLMClient(
        provider=provider,
        cache=DiskCache(tmp_path / "cache"),
        prices=PriceTable({"m": ModelPricing(input=0, output=0)}),
        usage_logger=UsageLogger(tmp_path / "u.jsonl"),
        roles={"agent": RoleSettings(model="m", max_tokens=256)},
    )


def tool(q: str, i: int = 0) -> dict[str, Any]:
    return {"type": "tool_use", "id": f"c{i}", "name": "run_sql", "input": {"query": q}}


def briefing_json(claims: list[dict[str, Any]], resumo: str = "Notas baixas em alta.") -> str:
    return json.dumps({"resumo": resumo, "causa_provavel": "produto", "afirmacoes": claims})


def test_loop_runs_tools_then_verifies_claims(tmp_path: Path, sql: ReadOnlySQL) -> None:
    good = {
        "texto": "30 notas 1",
        "valor": 30,
        "query_sql": "SELECT COUNT(*) FROM reviews WHERE review_score = 1",
    }
    bad = {"texto": "média 2", "valor": 2.0, "query_sql": "SELECT AVG(review_score) FROM reviews"}
    broken = {"texto": "x", "valor": 1, "query_sql": "DELETE FROM reviews"}
    prov = ScriptedProvider(
        [
            [tool("SELECT COUNT(*) FROM reviews WHERE review_score = 1")],
            [tool("DROP TABLE reviews", 1)],  # recusada: o erro volta ao modelo
            [{"type": "text", "text": "pronto"}],
            [{"type": "text", "text": briefing_json([good, bad, broken], "Foram 30 notas 1.")}],
        ]
    )
    inv = investigate(client(tmp_path, prov), sql, Alert("estado", "SP", "2018-04-02"), system="s")
    assert inv.iterations == 3 and len(inv.queries) == 2
    assert "erro" in inv.queries[1]
    # o resultado da ferramenta voltou ao modelo como tool_result
    second = prov.calls[1].messages
    assert second[-1]["content"][0]["type"] == "tool_result"
    assert json.loads(second[-1]["content"][0]["content"])["linhas"] == [[30]]
    assert [c.status for c in inv.checks] == ["verificada", "divergente", "erro"]
    assert inv.checks[1].valor_recalculado == pytest.approx(3.8)  # 30 × 1 + 70 × 5
    assert inv.unsupported == [] and inv.verified_share == pytest.approx(1 / 3)
    # a última chamada é o pedido do briefing, sem ferramentas e com schema
    assert prov.calls[-1].tools is None and prov.calls[-1].output_schema is not None
    # o banco não mudou
    assert sql.query("SELECT COUNT(*) FROM reviews").scalar() == 100


def test_iteration_limit_is_enforced(tmp_path: Path, sql: ReadOnlySQL) -> None:
    prov = ScriptedProvider([[tool("SELECT 1")]])  # nunca para de chamar a ferramenta
    inv = investigate(
        client(tmp_path, prov),
        sql,
        Alert("estado", "SP", "2018-04-02"),
        system="s",
        max_iterations=3,
    )
    assert inv.iterations == 3
    assert inv.briefing is None  # a resposta final não é JSON válido: nada a verificar


def test_numbers_in_summary_need_a_claim() -> None:
    b = Briefing(
        resumo="Em SP, na semana 2018-04-02, 30% das notas foram 1 e 12 vendedores foram afetados.",
        causa_provavel="entrega",
        afirmacoes=[Claim(texto="fração", valor=0.3, query_sql="SELECT 0.3")],
    )
    assert unsupported_numbers(b) == [12.0]  # 30 bate com 0,3 × 100
    assert same_value(0.4523, 0.45) and not same_value(0.46, 0.45)


def test_verify_requires_single_value(sql: ReadOnlySQL) -> None:
    b = Briefing(
        resumo="",
        causa_provavel="",
        afirmacoes=[Claim(texto="t", valor=1, query_sql="SELECT review_id FROM reviews")],
    )
    checks, _ = verify(b, sql)
    assert checks[0].status == "erro" and "único valor" in checks[0].detalhe


def test_briefings_json_for_panel(tmp_path: Path, sql: ReadOnlySQL) -> None:
    from src.agent.run import to_json

    good = {
        "texto": "30 notas 1",
        "valor": 30,
        "query_sql": "SELECT COUNT(*) FROM reviews WHERE review_score = 1",
    }
    prov = ScriptedProvider([[{"type": "text", "text": briefing_json([good])}]])
    inv = investigate(client(tmp_path, prov), sql, Alert("estado", "SP", "2018-04-02"), system="s")
    (out,) = to_json([inv])
    assert out["alerta"]["week"] == "2018-04-02"
    assert out["afirmacoes"][0]["status"] == "verificada"
    assert out["afirmacoes"][0]["valor_recalculado"] == 30
    json.dumps(out)  # serializável
