"""Grava as classificações do lote (Fase 6) num banco SQLite à parte, para o agente consultar.

Uso: `python -m src.agent.classifications`. Lê `data/predictions/lote_v1.csv` e grava
`data/processed/classificacoes.db` (não versionado), com a tabela `classificacoes`. O banco
principal não é alterado: ele é regenerado de forma determinística (D-023), e o agente anexa
este banco em modo somente leitura (`src.agent.sql.ReadOnlySQL(attach=...)`).
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pandas as pd

from src.classifier.batch import output_path
from src.config import load_config, resolve_path
from src.detection.data import FAMILY_OF

DB_NAME = "classificacoes.db"
COLUMNS = ["review_id", "review_score", "answered_week", "status", "causa", "familia", "area"]


def build(lote: pd.DataFrame, path: Path) -> int:
    df = lote.assign(familia=lote["causa"].map(FAMILY_OF).fillna(""))
    df = df.assign(review_score=df["review_score"].astype(int))[COLUMNS]
    path.unlink(missing_ok=True)
    con = sqlite3.connect(path)
    try:
        con.execute(
            "CREATE TABLE classificacoes (review_id TEXT PRIMARY KEY, review_score INTEGER, "
            "answered_week TEXT, status TEXT, causa TEXT, familia TEXT, area TEXT)"
        )
        con.executemany(
            "INSERT INTO classificacoes VALUES (?, ?, ?, ?, ?, ?, ?)", df.itertuples(index=False)
        )
        con.execute("CREATE INDEX ix_classif_week ON classificacoes(answered_week)")
        con.commit()
    finally:
        con.close()
    return len(df)


def db_path() -> Path:
    return Path(resolve_path(load_config()["paths"]["processed_dir"])) / DB_NAME


def main() -> None:
    lote = pd.read_csv(output_path(), dtype=str, keep_default_na=False)
    n = build(lote, db_path())
    print(f"{n} linhas em {db_path()}")


if __name__ == "__main__":
    main()
