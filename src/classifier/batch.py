"""Fase 6: classificação em lote dos comentários com nota ≤ 3, retomável (D-039, D-042).

Uso: `python -m src.classifier.batch --confirm` (exige o OK do usuário à estimativa, D-013);
`--estimate` só mostra a contagem e a estimativa de tempo, sem chamar o modelo.

- Nota ≤ 3: LLM prompt v1 sem raciocínio. Nota 4–5: status `nao_classificado`, nunca `elogio`.
- Ordem: data de resposta crescente, para que as semanas de calibração (2017) fiquem prontas
  primeiro.
- Retomável: as linhas vão para `data/predictions/lote_v1.csv` em blocos. Ao reiniciar, os IDs
  já gravados são pulados, e cada chamada já feita é acerto de cache.
- O arquivo não tem texto (D-035).
"""

from __future__ import annotations

import argparse
import csv
import sqlite3
import time
from collections.abc import Iterator, Sequence
from pathlib import Path
from typing import Any

import pandas as pd

from src.classifier.llm import PROMPT_VERSION, Review, classify, load_prompt
from src.classifier.run import PREDICTIONS_DIR, warm_up
from src.config import load_config, resolve_path
from src.llm.client import LLMClient
from src.taxonomy import AREA_BY_CAUSE

ROLE = "classifier"
MAX_SCORE = 3
CHUNK = 100
FIELDS = [
    "review_id",
    "review_score",
    "answered_week",
    "status",
    "causa",
    "gravidade",
    "confianca",
    "area",
    "attempts",
    "cached",
    "latency_s",
    "prompt_version",
    "model",
    "cache_key",
]
CLASSIFIED, NOT_CLASSIFIED, SCHEMA_FAIL = "classificado", "nao_classificado", "falha_schema"


def output_path() -> Path:
    return Path(resolve_path(PREDICTIONS_DIR)) / f"lote_{PROMPT_VERSION}.csv"


def load_comments(con: sqlite3.Connection) -> pd.DataFrame:
    """Todas as avaliações com comentário, em ordem de resposta (estável por review_id)."""
    return pd.read_sql(
        "SELECT review_id, review_score, answered_week, comment_title, comment_message "
        "FROM reviews WHERE has_comment = 1 ORDER BY review_answer_ts, review_id",
        con,
    )


def done_ids(path: Path) -> set[str]:
    if not path.exists():
        return set()
    with open(path, encoding="utf-8", newline="") as f:
        return {row["review_id"] for row in csv.DictReader(f)}


def append_rows(path: Path, rows: Sequence[dict[str, Any]]) -> None:
    new = not path.exists()
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "a", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=FIELDS, lineterminator="\n")
        if new:
            writer.writeheader()
        writer.writerows(rows)


def not_classified_row(r: Any) -> dict[str, Any]:
    return {
        "review_id": r.review_id,
        "review_score": int(r.review_score),
        "answered_week": r.answered_week,
        "status": NOT_CLASSIFIED,
        "causa": "",
        "gravidade": "",
        "confianca": "",
        "area": "",
        "attempts": 0,
        "cached": "",
        "latency_s": "",
        "prompt_version": "",
        "model": "",
        "cache_key": "",
    }


def classify_rows(client: LLMClient, todo: pd.DataFrame, system: str) -> Iterator[dict[str, Any]]:
    model = client.roles[ROLE].model
    for r in todo.itertuples(index=False):
        if int(r.review_score) > MAX_SCORE:
            yield not_classified_row(r)
            continue
        review = Review(
            review_id=r.review_id,
            score=int(r.review_score),
            title=r.comment_title if isinstance(r.comment_title, str) else None,
            message=str(r.comment_message),
        )
        res = classify(client, review, role=ROLE, system=system, tag=f"lote_{PROMPT_VERSION}")
        p = res.parsed
        yield {
            "review_id": r.review_id,
            "review_score": int(r.review_score),
            "answered_week": r.answered_week,
            "status": CLASSIFIED if p else SCHEMA_FAIL,
            "causa": p.causa if p else "",
            "gravidade": p.gravidade if p else "",
            "confianca": p.confianca if p else "",
            "area": AREA_BY_CAUSE[p.causa] if p else "",
            "attempts": len(res.attempts),
            "cached": all(a.cached for a in res.attempts),
            "latency_s": round(res.latency_s, 3),
            "prompt_version": PROMPT_VERSION,
            "model": model,
            "cache_key": res.attempts[0].cache_key,
        }


def run_batch(client: LLMClient, comments: pd.DataFrame, path: Path, system: str) -> int:
    """Classifica o que falta e grava em blocos de `CHUNK` linhas. Devolve o nº de linhas novas."""
    done = done_ids(path)
    todo = comments[~comments["review_id"].isin(done)]
    n_llm = int((todo["review_score"] <= MAX_SCORE).sum())
    print(f"faltam {len(todo)} linhas ({n_llm} para o LLM); já gravadas {len(done)}", flush=True)
    buf: list[dict[str, Any]] = []
    written, llm_done, t0 = 0, 0, time.perf_counter()
    for row in classify_rows(client, todo, system):
        buf.append(row)
        llm_done += row["status"] != NOT_CLASSIFIED
        if len(buf) >= CHUNK:
            append_rows(path, buf)
            written += len(buf)
            buf = []
            el = time.perf_counter() - t0
            eta = el / max(llm_done, 1) * (n_llm - llm_done) / 60
            print(
                f"{written}/{len(todo)} linhas | LLM {llm_done}/{n_llm} | "
                f"{el / 60:.1f} min | restam ~{eta:.0f} min",
                flush=True,
            )
    if buf:
        append_rows(path, buf)
        written += len(buf)
    return written


def estimate_lines(comments: pd.DataFrame, path: Path, s_med: float, s_mean: float) -> list[str]:
    done = done_ids(path)
    todo = comments[~comments["review_id"].isin(done)]
    n = int((todo["review_score"] <= MAX_SCORE).sum())
    return [
        f"comentários: {len(comments)}; nota ≤ {MAX_SCORE}: "
        f"{int((comments['review_score'] <= MAX_SCORE).sum())}; já gravados: {len(done)}",
        f"chamadas ao LLM a fazer: até {n} (itens do gold set com nota ≤ 3 saem do cache)",
        f"estimativa: {n * s_med / 3600:.1f} h pela mediana ({s_med:.2f} s), "
        f"{n * s_mean / 3600:.1f} h pela média ({s_mean:.2f} s); "
        f"pior caso com 2 tentativas por item: {2 * n * s_mean / 3600:.1f} h",
    ]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--confirm", action="store_true", help="roda o lote (OK do usuário)")
    parser.add_argument("--estimate", action="store_true", help="só a estimativa")
    parser.add_argument("--s-median", type=float, default=1.68, help="s/item medido (test)")
    parser.add_argument("--s-mean", type=float, default=1.80, help="s/item medido (test)")
    args = parser.parse_args()
    cfg = load_config()
    con = sqlite3.connect(f"file:{resolve_path(cfg['paths']['db_path'])}?mode=ro", uri=True)
    comments = load_comments(con)
    con.close()
    path = output_path()
    print("\n".join(estimate_lines(comments, path, args.s_median, args.s_mean)), flush=True)
    if args.estimate:
        return
    if not args.confirm:
        raise SystemExit("Mostre a estimativa ao usuário e, com o OK, rode com --confirm.")
    client = LLMClient.from_config(cfg)
    if client.mode == "live":
        warm_up(client, ROLE)
    n = run_batch(client, comments, path, load_prompt())
    print(f"{n} linhas novas em {path}", flush=True)


if __name__ == "__main__":
    main()
