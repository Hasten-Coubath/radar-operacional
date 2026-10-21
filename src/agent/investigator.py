"""Agente investigador: loop simples de ferramentas com limite de iterações (Fase 8).

1. O modelo recebe o alerta e pode chamar `run_sql` até `max_iterations` vezes.
2. Quando para de chamar ferramentas (ou o limite acaba), é pedido o briefing em JSON (`Briefing`).
3. O verificador reexecuta cada afirmação (`src.agent.verify`).

Sem framework de agentes: só o `LLMClient` do projeto, então cache, log de uso e tempo valem
também aqui.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any

from src.agent.sql import QueryRejected, ReadOnlySQL
from src.agent.verify import Briefing, ClaimCheck, verify
from src.config import load_config, resolve_path
from src.llm.client import LLMClient

PROMPT_VERSION = "v1"
MAX_ITERATIONS = 8
MAX_RESULT_CHARS = 6000
RUN_SQL = {
    "name": "run_sql",
    "description": "Executa uma consulta SELECT somente leitura e devolve colunas e linhas.",
    "input_schema": {
        "type": "object",
        "properties": {"query": {"type": "string", "description": "uma consulta SELECT"}},
        "required": ["query"],
    },
}
METHOD_TEXT = {
    "Radar": "Alerta do Radar",
    "B2": (
        "Alerta do detector (a fração de avaliações com nota ≤ 2 respondidas na semana subiu "
        "acima da mediana das 26 semanas anteriores)"
    ),
}
FINAL_REQUEST = (
    "Escreva agora o briefing final em JSON com resumo, causa_provavel e afirmacoes. Cada "
    "afirmação precisa de uma query_sql que devolva exatamente o valor citado."
)


@dataclass(frozen=True)
class Alert:
    segment_type: str
    segment_value: str
    week: str
    familia: str | None = None
    escore: float | None = None
    metodo: str = "Radar"

    def text(self) -> str:
        fam = f", família de causa em alta: {self.familia}" if self.familia else ""
        esc = f", escore {self.escore:.1f}" if self.escore is not None else ""
        source = METHOD_TEXT.get(self.metodo, f"Alerta do detector {self.metodo}")
        return (
            f"{source}: {self.segment_type} = {self.segment_value}, semana {self.week}"
            f"{fam}{esc}. Investigue o que está acontecendo e escreva o briefing."
        )


@dataclass
class Investigation:
    alert: Alert
    briefing: Briefing | None
    checks: list[ClaimCheck] = field(default_factory=list)
    unsupported: list[float] = field(default_factory=list)
    queries: list[dict[str, Any]] = field(default_factory=list)
    iterations: int = 0
    latency_s: float = 0.0

    @property
    def verified_share(self) -> float:
        return (
            sum(c.status == "verificada" for c in self.checks) / len(self.checks)
            if self.checks
            else 0.0
        )


def load_prompt(version: str = PROMPT_VERSION) -> str:
    path = resolve_path(load_config()["paths"]["prompts_dir"]) / f"agent_{version}.md"
    return path.read_text(encoding="utf-8").strip()


def run_tool(sql: ReadOnlySQL, block: dict[str, Any]) -> tuple[str, dict[str, Any]]:
    """Executa um bloco `tool_use`; devolve o texto para o modelo e o registro da consulta."""
    query = str((block.get("input") or {}).get("query", ""))
    if block.get("name") != "run_sql":
        return json.dumps({"erro": f"ferramenta desconhecida: {block.get('name')}"}), {}
    try:
        r = sql.query(query)
    except QueryRejected as e:
        return json.dumps({"erro": str(e)}, ensure_ascii=False), {"query": query, "erro": str(e)}
    payload = {"colunas": r.columns, "linhas": r.rows, "truncado": r.truncated}
    text = json.dumps(payload, ensure_ascii=False, default=str)
    if len(text) > MAX_RESULT_CHARS:
        text = text[:MAX_RESULT_CHARS] + " ... (resultado cortado)"
    return text, {"query": query, "linhas": len(r.rows), "truncado": r.truncated}


def investigate(
    client: LLMClient,
    sql: ReadOnlySQL,
    alert: Alert,
    *,
    role: str = "agent",
    max_iterations: int = MAX_ITERATIONS,
    system: str | None = None,
) -> Investigation:
    system = system or load_prompt()
    tag = f"agent_{PROMPT_VERSION}"
    messages: list[dict[str, Any]] = [{"role": "user", "content": alert.text()}]
    out = Investigation(alert=alert, briefing=None)
    for _ in range(max_iterations):
        req = client.request_for(role, messages, system=system, tools=[RUN_SQL])
        res = client.generate(req, tag=tag)
        out.iterations += 1
        out.latency_s += res.response.latency_s
        uses = res.response.tool_uses
        messages.append({"role": "assistant", "content": res.response.content})
        if not uses:
            break
        results = []
        for block in uses:
            text, record = run_tool(sql, block)
            out.queries.append(record)
            results.append({"type": "tool_result", "tool_use_id": block["id"], "content": text})
        messages.append({"role": "user", "content": results})
    messages.append({"role": "user", "content": FINAL_REQUEST})
    final = client.generate_structured(
        client.request_for(role, messages, system=system), Briefing, tag=tag
    )
    out.latency_s += final.latency_s
    out.briefing = final.parsed
    if final.parsed is not None:
        out.checks, out.unsupported = verify(final.parsed, sql)
    return out
