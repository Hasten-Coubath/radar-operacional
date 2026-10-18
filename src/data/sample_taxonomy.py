"""Amostra estratificada de comentários para validar a taxonomia (Fase 1).

Uso: `python -m src.data.sample_taxonomy [--show]`. Grava só os IDs em
`data/samples/amostra_taxonomia.csv` (versionado, sem texto); `--show` imprime os textos para
leitura. Esses IDs são excluídos da amostragem do gold set (Fase 2): os exemplos da taxonomia
saem daqui e não podem contaminar a avaliação.
"""

from __future__ import annotations

import argparse
import sqlite3

import pandas as pd

from src.config import load_config, resolve_path

PER_SCORE = 20
SAMPLE_PATH = "data/samples/amostra_taxonomia.csv"


def draw_sample(con: sqlite3.Connection, seed: int, per_score: int = PER_SCORE) -> pd.DataFrame:
    """`per_score` avaliações com comentário por nota (1–5), sorteadas com semente fixa."""
    df = pd.read_sql(
        "SELECT review_id, review_score FROM reviews WHERE has_comment = 1 ORDER BY review_id",
        con,
    )
    parts = [
        g.sample(n=per_score, random_state=seed) for _, g in df.groupby("review_score", sort=True)
    ]
    return pd.concat(parts).reset_index(drop=True)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--show", action="store_true", help="imprime os textos da amostra")
    args = parser.parse_args()

    cfg = load_config()
    con = sqlite3.connect(f"file:{resolve_path(cfg['paths']['db_path'])}?mode=ro", uri=True)
    sample = draw_sample(con, seed=cfg["project"]["seed"])
    path = resolve_path(SAMPLE_PATH)
    path.parent.mkdir(parents=True, exist_ok=True)
    sample.to_csv(path, index=False, lineterminator="\n")
    print(f"{len(sample)} IDs gravados em {path}")

    if args.show:
        texts = pd.read_sql(
            f"""
            SELECT r.review_id, r.review_score, r.comment_title, r.comment_message,
                   o.order_status, o.is_late, o.delay_days,
                   r.review_creation_date < COALESCE(date(o.delivered_customer_ts), '9999')
                       AS pesquisa_antes_da_entrega
            FROM reviews r
            JOIN review_orders ro ON ro.review_id = r.review_id
            JOIN orders o ON o.order_id = ro.order_id
            WHERE r.review_id IN ({",".join("?" * len(sample))})
            GROUP BY r.review_id
            """,
            con,
            params=list(sample["review_id"]),
        ).set_index("review_id")
        for i, row in enumerate(sample.itertuples(), 1):
            t = texts.loc[row.review_id]
            title = f"[{t.comment_title}] " if isinstance(t.comment_title, str) else ""
            print(
                f"\n#{i:03d} {row.review_id[:8]} nota={row.review_score} status={t.order_status} "
                f"atraso={t.delay_days} antes_entrega={t.pesquisa_antes_da_entrega}\n"
                f"    {title}{t.comment_message}"
            )


if __name__ == "__main__":
    main()
