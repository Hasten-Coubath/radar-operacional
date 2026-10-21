"""Roda o agente investigador nos alertas do Radar e grava `reports/agente.md` e
`reports/briefings.json` (Fase 8; o JSON alimenta o painel).

Uso: `python -m src.agent.run --pilot` (estimativa) e `--confirm` (OK do usuário, D-013).
Os alertas vêm de `reports/agente_alvos.csv` (alertas do B2 em 2018, selecionados por
`src.agent.targets` com critério fixado antes de rodar, D-054). `--pilot` roda só os marcados
como piloto e grava `agente_piloto.md` / `briefings_piloto.json`. O agente recebe só o alerta
(segmento, semana, método, escore); critério e gabarito aparecem apenas no relatório.

Cada investigação usa um banco recortado no fim da semana do alerta (D-050), aberto com as
quatro camadas de somente leitura.
"""

from __future__ import annotations

import argparse
import json
import tempfile
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

import pandas as pd

from src.agent.classifications import db_path as classif_db
from src.agent.investigator import MAX_ITERATIONS, Alert, Investigation, investigate
from src.agent.snapshot import build_snapshot, cutoff_for_week
from src.agent.sql import ReadOnlySQL
from src.config import load_config, resolve_path
from src.data.stats import md_table, pct
from src.llm.client import LLMClient

TARGETS_FILE = "agente_alvos.csv"


@dataclass(frozen=True)
class Target:
    alert: Alert
    criterio: str
    gabarito: str


def load_targets(path: Path, pilot: bool) -> list[Target]:
    t = pd.read_csv(path, dtype={"week": str})
    if pilot:
        t = t[t["piloto"] == "sim"]
    return [
        Target(
            Alert(x.segment_type, x.segment_value, x.week, None, float(x.score), x.metodo),
            x.criterio,
            x.gabarito,
        )
        for x in t.itertuples(index=False)
    ]


def to_json(invs: list[Investigation]) -> list[dict[str, Any]]:
    """Briefings com a verificação de cada afirmação (entrada do painel, `src.app.data`)."""
    out = []
    for inv in invs:
        b = inv.briefing
        claims = b.afirmacoes if b else []
        out.append(
            {
                "alerta": asdict(inv.alert),
                "resumo": b.resumo if b else "",
                "causa_provavel": b.causa_provavel if b else "",
                "afirmacoes": [
                    {
                        "texto": c.texto,
                        "valor": chk.valor_citado,
                        "valor_recalculado": chk.valor_recalculado,
                        "status": chk.status,
                        "query_sql": c.query_sql,
                    }
                    for c, chk in zip(claims, inv.checks, strict=True)
                ],
                "numeros_sem_afirmacao": inv.unsupported,
            }
        )
    return out


def report(invs: list[Investigation], targets: list[Target]) -> list[str]:
    rows, claims = [], []
    for i, (inv, t) in enumerate(zip(invs, targets, strict=True), 1):
        a = inv.alert
        rows.append(
            {
                "#": i,
                "alerta": f"{a.metodo} {a.segment_type}={a.segment_value} {a.week}",
                "critério": t.criterio,
                "gabarito": t.gabarito,
                "iterações": inv.iterations,
                "consultas": len(inv.queries),
                "briefing válido": "sim" if inv.briefing else "não",
                "afirmações": len(inv.checks),
                "verificadas": sum(c.status == "verificada" for c in inv.checks),
                "números sem afirmação": len(inv.unsupported),
                "tempo (s)": round(inv.latency_s, 1),
            }
        )
        for c in inv.checks:
            claims.append(
                {
                    "#": i,
                    "afirmação": c.texto,
                    "citado": c.valor_citado,
                    "recalculado": c.valor_recalculado,
                    "status": c.status,
                }
            )
    n = sum(len(i.checks) for i in invs)
    ok = sum(c.status == "verificada" for i in invs for c in i.checks)
    out = [
        "# Agente investigador: briefings verificados",
        "",
        "_Gerado por `python -m src.agent.run`. Não edite à mão._",
        "",
        "Critério e gabarito vêm de `reports/agente_alvos.csv` (D-054); o agente não os vê.",
        "",
        f"- Alertas investigados: {len(invs)}; afirmações: {n}; verificadas: {ok}"
        + (f" ({pct(ok / n)})" if n else "")
        + ".",
        f"- Limite de {MAX_ITERATIONS} iterações por alerta; SQL somente leitura (D-049).",
        "",
        md_table(pd.DataFrame(rows)),
        "",
        "## Afirmações e verificação",
        "",
        md_table(pd.DataFrame(claims)) if claims else "_nenhuma_",
        "",
        "## Briefings",
        "",
    ]
    for i, inv in enumerate(invs, 1):
        b = inv.briefing
        out += [
            f"### {i}. {inv.alert.segment_type} = {inv.alert.segment_value}, {inv.alert.week}",
            "",
        ]
        if b is None:
            out += ["_sem briefing válido_", ""]
            continue
        out += [b.resumo, "", f"**Causa provável:** {b.causa_provavel}", ""]
        if inv.unsupported:
            out += [f"Números sem afirmação verificável: {inv.unsupported}", ""]
    return out


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--pilot", action="store_true")
    parser.add_argument("--confirm", action="store_true")
    args = parser.parse_args()
    cfg = load_config()
    reports = Path(resolve_path(cfg["paths"]["reports_dir"]))
    targets = load_targets(reports / TARGETS_FILE, args.pilot)
    alerts = [t.alert for t in targets]
    print(
        f"{len(alerts)} alertas; até {len(alerts) * (MAX_ITERATIONS + 2)} chamadas ao LLM "
        "(iterações + briefing com até 2 tentativas)"
    )
    if not args.confirm:
        raise SystemExit("Mostre a estimativa ao usuário e, com o OK, rode com --confirm.")
    client = LLMClient.from_config(cfg)
    source = resolve_path(cfg["paths"]["db_path"])
    suffix = "_piloto" if args.pilot else ""
    path = reports / f"agente{suffix}.md"
    invs: list[Investigation] = []
    for i, a in enumerate(alerts, 1):
        with tempfile.TemporaryDirectory() as tmp:
            snap = build_snapshot(
                source, Path(tmp) / "corte.db", cutoff_for_week(a.week), classif_db()
            )
            sql = ReadOnlySQL(snap)
            try:
                invs.append(investigate(client, sql, a))
            finally:
                sql.close()
        inv = invs[-1]
        print(
            f"{i}/{len(alerts)} {a.segment_type}={a.segment_value} {a.week}: "
            f"{inv.iterations} iterações, {len(inv.checks)} afirmações, {inv.latency_s:.0f} s",
            flush=True,
        )
        # grava a cada alerta: uma falha no meio não perde as investigações já feitas
        (reports / f"briefings{suffix}.json").write_text(
            json.dumps(to_json(invs), ensure_ascii=False, indent=2), encoding="utf-8"
        )
        path.write_text(
            "\n".join(report(invs, targets[: len(invs)])), encoding="utf-8", newline="\n"
        )
    print(f"Relatório gravado em {path}")


if __name__ == "__main__":
    main()
