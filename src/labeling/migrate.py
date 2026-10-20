"""Migração mecânica dos rótulos do gold set da taxonomia v1 para a v1.1 (D-034).

Uso: `python -m src.labeling.migrate --force`. Lê `data/gold/labels_v1.csv` (rótulos originais,
congelados, sem as flags removidas em D-033) e grava `data/gold/labels.csv` em v1.1. Nenhum item
é rejulgado; as regras usam só a causa e a nota livre que o usuário gravou:

- `atraso_entrega` e `nao_recebido` viram `problema_entrega` (principal e secundária);
- causa principal `outro` com nota livre "qualidade ruim" vira `qualidade_insatisfatoria`;
- secundária que fica igual à principal depois da fusão é apagada.
"""

from __future__ import annotations

import argparse
from pathlib import Path

import pandas as pd

from src.config import load_config, resolve_path
from src.labeling.store import FIELDS, LABELS_FILE, Label

V1_FILE = "labels_v1.csv"
MERGED_INTO_DELIVERY = {"atraso_entrega": "problema_entrega", "nao_recebido": "problema_entrega"}
QUALITY_NOTE = "qualidade ruim"


def migrate_row(row: dict[str, str]) -> dict[str, str]:
    """Um rótulo v1 → v1.1. Campos ausentes da regra passam sem mudança."""
    causa = MERGED_INTO_DELIVERY.get(row["causa"], row["causa"])
    if row["causa"] == "outro" and row["nota_livre"].strip().lower() == QUALITY_NOTE:
        causa = "qualidade_insatisfatoria"
    sec = MERGED_INTO_DELIVERY.get(row["causa_secundaria"], row["causa_secundaria"])
    if sec == causa:
        sec = ""
    return {**row, "causa": causa, "causa_secundaria": sec}


def migrate(v1: pd.DataFrame) -> pd.DataFrame:
    """Tabela de rótulos v1 (strings, vazio = sem valor) → v1.1, validada pelo modelo `Label`."""
    rows = [migrate_row(r) for r in v1[FIELDS].to_dict("records")]
    for r in rows:
        Label.model_validate({**r, "causa_secundaria": r["causa_secundaria"] or None})
    return pd.DataFrame(rows, columns=FIELDS)


def read_labels_csv(path: Path) -> pd.DataFrame:
    return pd.read_csv(path, dtype=str, keep_default_na=False)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--force", action="store_true", help="sobrescreve labels.csv")
    args = parser.parse_args()
    gold_dir = resolve_path(load_config()["paths"]["gold_dir"])
    out = gold_dir / LABELS_FILE
    if out.exists() and not args.force:
        raise SystemExit(f"{out} já existe; use --force para regenerar a partir de {V1_FILE}.")
    new = migrate(read_labels_csv(gold_dir / V1_FILE))
    new.to_csv(out, index=False, lineterminator="\n")
    print(f"{len(new)} rótulos v1.1 gravados em {out}")


if __name__ == "__main__":
    main()
