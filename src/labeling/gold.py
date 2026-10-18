"""Amostra do gold set e divisão fixa dev/test, sorteadas antes da rotulagem.

Uso: `python -m src.labeling.gold`. Grava `data/gold/gold_sample.csv` (IDs, nota, split e ordem
de apresentação; sem texto) e se recusa a sobrescrever um arquivo existente: a divisão é
sorteada uma vez só.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

import numpy as np
import pandas as pd

from src.config import load_config, resolve_path
from src.data.sample_taxonomy import SAMPLE_PATH as TAXONOMY_SAMPLE_PATH

PER_SCORE = 50
DEV_PER_SCORE = 20  # 20 dev + 30 test por nota -> 100 dev, 150 test
SAMPLE_FILE = "gold_sample.csv"


def build_gold_sample(
    con: sqlite3.Connection,
    seed: int,
    exclude_ids: set[str],
    per_score: int = PER_SCORE,
    dev_per_score: int = DEV_PER_SCORE,
) -> pd.DataFrame:
    """`per_score` avaliações com comentário por nota, fora de `exclude_ids`, com split e ordem.

    A ordem de apresentação embaralha dev e test juntos, para que quem rotula não saiba o split.
    """
    df = pd.read_sql(
        "SELECT review_id, review_score FROM reviews WHERE has_comment = 1 ORDER BY review_id",
        con,
    )
    df = df[~df["review_id"].isin(exclude_ids)]
    rng = np.random.default_rng(seed)
    parts = []
    for _, g in df.groupby("review_score", sort=True):
        picked = g.iloc[rng.permutation(len(g))[:per_score]].copy()
        picked["split"] = ["dev"] * dev_per_score + ["test"] * (per_score - dev_per_score)
        parts.append(picked)
    sample = pd.concat(parts, ignore_index=True)
    sample["position"] = rng.permutation(len(sample)) + 1
    return sample.sort_values("position").reset_index(drop=True)


def main() -> None:
    cfg = load_config()
    out = resolve_path(cfg["paths"]["gold_dir"]) / SAMPLE_FILE
    if out.exists():
        raise SystemExit(f"{out} já existe: a divisão dev/test é fixa e não é sorteada de novo.")
    exclude = set(pd.read_csv(resolve_path(TAXONOMY_SAMPLE_PATH))["review_id"])
    con = sqlite3.connect(f"file:{resolve_path(cfg['paths']['db_path'])}?mode=ro", uri=True)
    sample = build_gold_sample(con, seed=cfg["project"]["seed"], exclude_ids=exclude)
    out.parent.mkdir(parents=True, exist_ok=True)
    sample.to_csv(out, index=False, lineterminator="\n")
    counts = sample.groupby(["split", "review_score"]).size().unstack(fill_value=0)
    print(f"{len(sample)} itens gravados em {out}\n{counts}")


def load_gold_sample(gold_dir: Path) -> pd.DataFrame:
    return pd.read_csv(gold_dir / SAMPLE_FILE).sort_values("position").reset_index(drop=True)


if __name__ == "__main__":
    main()
