"""Roda o agente investigador nos alertas do Radar e grava `reports/agente.md` (Fase 8).

Uso: `python -m src.agent.run --top 5` (estimativa) e `--confirm` (OK do usuário, D-013).
Os alertas vêm de `reports/alertas_avaliacao.csv` (backtest de 2018): os de maior escore do
Radar, um por segmento. Só depois do lote da Fase 6 (a GPU fica livre).
"""

from __future__ import annotations

import argparse
from pathlib import Path

import pandas as pd

from src.agent.classifications import db_path as classif_db
from src.agent.investigator import MAX_ITERATIONS, Alert, Investigation, investigate
from src.agent.sql import ReadOnlySQL
from src.config import load_config, resolve_path
from src.data.stats import md_table, pct
from src.llm.client import LLMClient

ALERTS_FILE = "alertas_avaliacao.csv"


def pick_alerts(path: Path, top: int) -> list[Alert]:
    a = pd.read_csv(path)
    r = a[a["metodo"] == "Radar"].sort_values("score", ascending=False)
    r = r.drop_duplicates(["segment_type", "segment_value"]).head(top)
    return [
        Alert(x.segment_type, x.segment_value, x.week, x.familia, float(x.score))
        for x in r.itertuples(index=False)
    ]


def report(invs: list[Investigation]) -> list[str]:
    rows, claims = [], []
    for i, inv in enumerate(invs, 1):
        a = inv.alert
        rows.append(
            {
                "#": i,
                "alerta": f"{a.segment_type}={a.segment_value} {a.week} ({a.familia})",
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
    parser.add_argument("--top", type=int, default=5)
    parser.add_argument("--confirm", action="store_true")
    args = parser.parse_args()
    cfg = load_config()
    reports = Path(resolve_path(cfg["paths"]["reports_dir"]))
    alerts = pick_alerts(reports / ALERTS_FILE, args.top)
    print(
        f"{len(alerts)} alertas; até {len(alerts) * (MAX_ITERATIONS + 2)} chamadas ao LLM "
        "(iterações + briefing com até 2 tentativas)"
    )
    if not args.confirm:
        raise SystemExit("Mostre a estimativa ao usuário e, com o OK, rode com --confirm.")
    client = LLMClient.from_config(cfg)
    sql = ReadOnlySQL(resolve_path(cfg["paths"]["db_path"]), attach={"c": classif_db()})
    invs = [investigate(client, sql, a) for a in alerts]
    path = reports / "agente.md"
    path.write_text("\n".join(report(invs)), encoding="utf-8", newline="\n")
    print(f"Relatório gravado em {path}")


if __name__ == "__main__":
    main()
