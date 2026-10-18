"""Relatório do gold set depois da rotulagem: distribuição de classes por split e classes raras.

Uso: `python -m src.labeling.report`. Gera `reports/gold_set.md`. A distribuição "reponderada"
estima a do universo de avaliações com comentário, pesando cada nota pela sua participação real
(a amostra tem 50 por nota, o universo não).
"""

from __future__ import annotations

import sqlite3

import pandas as pd

from src.config import load_config, resolve_path
from src.data.stats import md_table, pct
from src.labeling.gold import load_gold_sample
from src.labeling.store import LabelStore
from src.taxonomy import AMBIGUOUS, AREA_BY_CAUSE, CAUSES

FEW_DEV = 5  # classe com menos exemplos que isso no dev é sinalizada
FEW_TEST = 8


def score_weights(sample: pd.DataFrame, population_share: pd.Series) -> pd.Series:
    """Peso por nota = participação no universo / participação na amostra."""
    sample_share = sample["review_score"].value_counts(normalize=True)
    return (population_share / sample_share).rename("peso")


def ambiguity_line(df: pd.DataFrame) -> str:
    """Contagem e taxa de ambiguidade no total e por split."""
    amb = df["causa"] == AMBIGUOUS
    parts = [f"{int(amb.sum())} de {len(df)} ({pct(amb.mean())})"]
    for split in ("dev", "test"):
        m = df["split"] == split
        if m.any():
            parts.append(f"{split} {int(amb[m].sum())}/{int(m.sum())} ({pct(amb[m].mean())})")
    return "; ".join(parts)


def class_table(df: pd.DataFrame, weights: pd.Series) -> pd.DataFrame:
    """Contagem por classe e split, mais a proporção reponderada (todos os itens não ambíguos)."""
    order = [*CAUSES, AMBIGUOUS]
    counts = df.groupby(["causa", "split"]).size().unstack(fill_value=0)
    counts = counts.reindex(index=order, columns=["dev", "test"], fill_value=0)
    counts["total"] = counts.sum(axis=1)
    clear = df[df["causa"] != AMBIGUOUS]
    w = clear["review_score"].map(weights)
    reweighted = w.groupby(clear["causa"]).sum() / w.sum()
    counts["% amostra (não ambíguos)"] = (
        counts["total"] / counts.loc[list(CAUSES), "total"].sum()
    ).where(counts.index != AMBIGUOUS)
    counts["% reponderado"] = reweighted.reindex(counts.index)
    counts["área (D-027)"] = [AREA_BY_CAUSE[c] for c in counts.index]
    for col in ("% amostra (não ambíguos)", "% reponderado"):
        counts[col] = counts[col].map(lambda v: "" if pd.isna(v) else pct(v))
    return counts.reset_index().rename(columns={"causa": "classe"})


def main() -> None:
    cfg = load_config()
    gold_dir = resolve_path(cfg["paths"]["gold_dir"])
    sample = load_gold_sample(gold_dir)
    labels = LabelStore(gold_dir).load()
    con = sqlite3.connect(f"file:{resolve_path(cfg['paths']['db_path'])}?mode=ro", uri=True)
    pop = pd.read_sql(
        "SELECT review_score, COUNT(*) n FROM reviews WHERE has_comment = 1 GROUP BY review_score",
        con,
    ).set_index("review_score")["n"]
    weights = score_weights(sample, pop / pop.sum())

    rows = [lb.model_dump() for lb in labels.values()]
    df = sample.merge(pd.DataFrame(rows), on="review_id", how="inner")
    missing = len(sample) - len(df)
    table = class_table(df, weights)
    few = table[
        table["classe"].isin(CAUSES) & ((table["dev"] < FEW_DEV) | (table["test"] < FEW_TEST))
    ]["classe"].tolist()
    by_score = (
        df.groupby(["causa", "review_score"])
        .size()
        .unstack(fill_value=0)
        .reindex([*CAUSES, AMBIGUOUS], fill_value=0)
        .reset_index()
    )
    by_score.columns = ["classe", *[f"nota {c}" for c in by_score.columns[1:]]]
    flags = pd.DataFrame(
        {
            "campo": ["menciona_atraso", "pede_reembolso_troca", "com causa secundária"],
            "itens": [
                int(df["menciona_atraso"].sum()),
                int(df["pede_reembolso_troca"].sum()),
                int(df["causa_secundaria"].notna().sum()),
            ],
        }
    )
    flags["% dos rotulados"] = (flags["itens"] / len(df)).map(pct)
    weights_t = weights.reset_index()
    weights_t.columns = ["nota", "peso"]

    out = [
        "# Gold set: distribuição dos rótulos",
        "",
        "_Gerado por `python -m src.labeling.report`. Não edite à mão._",
        "",
        f"- Rotulados: **{len(df)} de {len(sample)}** (faltam {missing}).",
        f"- Ambíguos / não sei: {ambiguity_line(df)}. Ficam fora das métricas principais e "
        "são reportados à parte (D-028).",
        f"- Classes com poucos exemplos (< {FEW_DEV} no dev ou < {FEW_TEST} no test): "
        f"{', '.join(f'`{c}`' for c in few) or 'nenhuma'}.",
        "",
        "## Classes por split",
        "",
        md_table(table),
        "",
        "Pesos por nota usados na reponderação (participação no universo / na amostra):",
        "",
        md_table(weights_t),
        "",
        "## Classes × nota (todos os rotulados)",
        "",
        md_table(by_score),
        "",
        "## Campos auxiliares",
        "",
        md_table(flags),
        "",
    ]
    path = resolve_path(cfg["paths"]["reports_dir"]) / "gold_set.md"
    path.write_text("\n".join(out), encoding="utf-8", newline="\n")
    print(f"Relatório gravado em {path}")


if __name__ == "__main__":
    main()
