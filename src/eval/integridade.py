"""Checagem de integridade do lote da Fase 6 (D-051). Critérios fixados antes do fim do lote.

Uso: `python -m src.eval.integridade`. Sai com código 0 só se todas as verificações passarem;
a avaliação de 2018 (`src.detection.backtest --period avaliacao`) só roda depois disso.
Falhas de schema: aceitas até 1% das chamadas (notas ≤ 3).
"""

from __future__ import annotations

import sqlite3
import sys

import pandas as pd

from src.classifier.batch import output_path
from src.config import load_config, resolve_path
from src.detection.backtest import EVAL, load_predictions, lote_missing
from src.taxonomy import CAUSES

MAX_SCHEMA_FAIL = 0.01


def run_checks(con: sqlite3.Connection, p: pd.DataFrame) -> list[tuple[str, bool, str]]:
    c = pd.read_sql("SELECT review_id, review_score FROM reviews WHERE has_comment = 1", con)
    checks: list[tuple[str, bool, str]] = []

    def check(name: str, ok: bool, detail: str = "") -> None:
        checks.append((name, bool(ok), detail))

    low = c[c.review_score <= 3]
    check("linhas = comentários", len(p) == len(c), f"{len(p)} de {len(c)}")
    dup = int(p.review_id.duplicated().sum())
    check("sem review_id duplicado", dup == 0, f"{dup} duplicados")
    missing = set(c.review_id) - set(p.review_id)
    check("nenhum review_id faltando", not missing, f"{len(missing)} faltando")
    extra = set(p.review_id) - set(c.review_id)
    check("nenhum review_id estranho", not extra, f"{len(extra)} fora do banco")
    counts = p.status.value_counts().to_dict()
    n_fail = counts.get("falha_schema", 0)
    n_llm = counts.get("classificado", 0) + n_fail
    n_high = len(c) - len(low)
    check(
        "status conhecidos",
        set(counts) <= {"classificado", "nao_classificado", "falha_schema"},
        str(counts),
    )
    check(
        "nao_classificado = notas 4–5",
        counts.get("nao_classificado", 0) == n_high,
        f"{counts.get('nao_classificado', 0)} vs {n_high}",
    )
    check("classificado + falha = notas ≤ 3", n_llm == len(low), f"{n_llm} vs {len(low)}")
    score = p.review_score.astype(int)
    check(
        "nota ≤ 3 nunca nao_classificado",
        not ((score <= 3) & (p.status == "nao_classificado")).any(),
    )
    check(
        "nota ≥ 4 nunca classificada", not ((score >= 4) & (p.status != "nao_classificado")).any()
    )
    cl = p[p.status == "classificado"]
    check(
        "causas válidas",
        bool(cl.causa.isin(CAUSES).all()),
        str(sorted(set(cl.causa) - set(CAUSES))),
    )
    check(
        f"falhas de schema ≤ {MAX_SCHEMA_FAIL:.0%}",
        n_fail <= MAX_SCHEMA_FAIL * len(low),
        f"{n_fail} de {len(low)} ({n_fail / len(low):.2%})",
    )
    left = lote_missing(con, p, EVAL[1])
    check("lote_missing até o fim da avaliação = 0", left == 0, str(left))
    return checks


def main() -> None:
    con = sqlite3.connect(resolve_path(load_config()["paths"]["db_path"]))
    p = load_predictions(output_path())
    if p is None:
        raise SystemExit("Lote ausente.")
    checks = run_checks(con, p)
    con.close()
    for name, ok, detail in checks:
        print(f"[{'OK' if ok else 'FALHOU'}] {name}" + (f": {detail}" if detail else ""))
    print("status:", p.status.value_counts().to_dict())
    print("causas:", p.loc[p.status == "classificado", "causa"].value_counts().to_dict())
    ok = all(x[1] for x in checks)
    print("INTEGRIDADE:", "PASSOU" if ok else "FALHOU")
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
