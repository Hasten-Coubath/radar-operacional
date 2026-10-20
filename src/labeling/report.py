"""Relatório do gold set (taxonomia v1.1): classes por split, classes raras, composição por nota,
causa secundária, notas livres e a migração v1 → v1.1.

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
from src.labeling.migrate import QUALITY_NOTE, V1_FILE, read_labels_csv
from src.labeling.store import LabelStore
from src.taxonomy import AMBIGUOUS, AREA_BY_CAUSE, CAUSES

FEW_DEV = 5  # classe com menos exemplos que isso no dev é sinalizada
FEW_TEST = 8
LOW_SCORES = (1, 2, 3)  # recorte avaliado para a Fase 6: classificar só notas ≤ 3
SPLITS = ("dev", "test")


def score_weights(sample: pd.DataFrame, population_share: pd.Series) -> pd.Series:
    """Peso por nota = participação no universo / participação na amostra."""
    sample_share = sample["review_score"].value_counts(normalize=True)
    return (population_share / sample_share).rename("peso")


def ambiguity_line(df: pd.DataFrame) -> str:
    """Contagem e taxa de ambiguidade no total e por split."""
    amb = df["causa"] == AMBIGUOUS
    parts = [f"{int(amb.sum())} de {len(df)} ({pct(amb.mean())})"]
    for split in SPLITS:
        m = df["split"] == split
        if m.any():
            parts.append(f"{split} {int(amb[m].sum())}/{int(m.sum())} ({pct(amb[m].mean())})")
    return "; ".join(parts)


def class_table(df: pd.DataFrame, weights: pd.Series) -> pd.DataFrame:
    """Contagem por classe e split, mais a proporção reponderada (todos os itens não ambíguos)."""
    order = [*CAUSES, AMBIGUOUS]
    counts = df.groupby(["causa", "split"]).size().unstack(fill_value=0)
    counts = counts.reindex(index=order, columns=list(SPLITS), fill_value=0)
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


def composition_by_score(df: pd.DataFrame) -> pd.DataFrame:
    """Contagem e participação de cada classe dentro de cada nota ("n (x%)"; inclui ambíguos)."""
    counts = (
        df.groupby(["causa", "review_score"])
        .size()
        .unstack(fill_value=0)
        .reindex(index=[*CAUSES, AMBIGUOUS], columns=range(1, 6), fill_value=0)
    )
    totals = counts.sum()
    out = pd.DataFrame(index=counts.index)
    for s in counts.columns:
        out[f"nota {s}"] = [f"{n} ({pct(n / totals[s])})" if n else "0" for n in counts[s]]
    return out.reset_index().rename(columns={"causa": "classe"})


def low_score_coverage(df: pd.DataFrame, weights: pd.Series) -> pd.DataFrame:
    """Fração reponderada do volume de cada classe que está em notas ≤ 3, por split e total.

    É a parte da classe que uma classificação restrita a notas ≤ 3 alcançaria (sem ambíguos).
    """
    clear = df[df["causa"] != AMBIGUOUS]
    clear = clear.assign(
        w=clear["review_score"].map(weights), low=clear["review_score"].isin(LOW_SCORES)
    )
    groups: list[tuple[str, list[str]]] = [(c, [c]) for c in CAUSES]
    groups.append(("todas exceto elogio", [c for c in CAUSES if c != "elogio"]))
    parts = [(s, clear[clear["split"] == s]) for s in SPLITS] + [("total", clear)]
    rows = []
    for name, classes in groups:
        row = {"classe": name}
        for split, part in parts:
            sel = part[part["causa"].isin(classes)]
            if sel.empty:
                row[split] = "—"
            else:
                row[split] = (
                    f"{pct(sel.loc[sel['low'], 'w'].sum() / sel['w'].sum())} (n={len(sel)})"
                )
        rows.append(row)
    return pd.DataFrame(rows)


def by_split(df: pd.DataFrame, keys: list[str]) -> pd.DataFrame:
    """Contagem por `keys` com colunas dev, test e total, da maior para a menor."""
    if df.empty:
        return pd.DataFrame(columns=[*keys, *SPLITS, "total"])
    t = df.groupby([*keys, "split"]).size().unstack(fill_value=0)
    t = t.reindex(columns=list(SPLITS), fill_value=0)
    t["total"] = t.sum(axis=1)
    return t.sort_values("total", ascending=False, kind="stable").reset_index()


def secondary_table(df: pd.DataFrame) -> pd.DataFrame:
    """Pares causa principal → causa secundária."""
    sec = df[df["causa_secundaria"].notna()]
    return by_split(sec, ["causa", "causa_secundaria"])


def notes_table(df: pd.DataFrame) -> pd.DataFrame:
    """Notas livres (minúsculas, sem espaços nas pontas) por causa principal."""
    notes = df.assign(nota=df["nota_livre"].fillna("").str.strip().str.lower())
    return by_split(notes[notes["nota"] != ""], ["nota", "causa"])


def migration_table(v1: pd.DataFrame, v11: pd.DataFrame) -> pd.DataFrame:
    """Itens cuja causa principal mudou na migração v1 → v1.1, por par de classes e split."""
    m = v1[["review_id", "split", "causa"]].merge(
        v11[["review_id", "causa"]], on="review_id", suffixes=("_v1", "_v11")
    )
    changed = m[m["causa_v1"] != m["causa_v11"]].rename(
        columns={"causa_v1": "v1", "causa_v11": "v1.1"}
    )
    return by_split(changed, ["v1", "v1.1"])


def dev_evidence(v1: pd.DataFrame, delivered: pd.Series) -> pd.DataFrame:
    """Evidência da v1.1 calculada só no dev, com os rótulos v1 originais (D-034).

    `delivered`: por `review_id`, se algum pedido da avaliação tem data de entrega ao cliente.
    Serve só para auditar a fronteira atraso × não recebido; quem rotulou não via esse dado.
    """
    dev = v1[v1["split"] == "dev"]
    got = dev["review_id"].map(delivered).fillna(False).astype(bool)
    note = dev["nota_livre"].str.strip().str.lower()
    outro = dev["causa"] == "outro"
    rows = []
    for cause in ("nao_recebido", "atraso_entrega"):
        sel = dev["causa"] == cause
        rows.append(
            {
                "evidência (dev, rótulos v1)": f"`{cause}` com pedido entregue depois",
                "itens": f"{int(got[sel].sum())} de {int(sel.sum())}",
            }
        )
    for text in (QUALITY_NOTE, "embalagem danificada"):
        rows.append(
            {
                "evidência (dev, rótulos v1)": f'`outro` com nota "{text}"',
                "itens": f"{int((outro & (note == text)).sum())} de {int(outro.sum())}",
            }
        )
    return pd.DataFrame(rows)


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
    delivered = (
        pd.read_sql(
            "SELECT ro.review_id, MAX(o.delivered_customer_ts IS NOT NULL) AS entregue "
            "FROM review_orders ro JOIN orders o USING (order_id) GROUP BY ro.review_id",
            con,
        )
        .set_index("review_id")["entregue"]
        .astype(bool)
    )
    con.close()
    pop_share = pop / pop.sum()
    weights = score_weights(sample, pop_share)

    rows = [lb.model_dump() for lb in labels.values()]
    df = sample.merge(pd.DataFrame(rows), on="review_id", how="inner")
    v1 = sample.merge(read_labels_csv(gold_dir / V1_FILE), on="review_id", how="inner")
    missing = len(sample) - len(df)
    table = class_table(df, weights)
    few = table[
        table["classe"].isin(CAUSES) & ((table["dev"] < FEW_DEV) | (table["test"] < FEW_TEST))
    ]["classe"].tolist()
    n_sec = int(df["causa_secundaria"].notna().sum())
    n_notes = int((df["nota_livre"].fillna("").str.strip() != "").sum())
    weights_t = weights.reset_index()
    weights_t.columns = ["nota", "peso"]
    low_share = float(pop_share.loc[list(LOW_SCORES)].sum())

    out = [
        "# Gold set: distribuição dos rótulos (taxonomia v1.1)",
        "",
        "_Gerado por `python -m src.labeling.report`. Não edite à mão._",
        "",
        f"- Rotulados: **{len(df)} de {len(sample)}** (faltam {missing}).",
        f"- Ambíguos / não sei: {ambiguity_line(df)}. Ficam fora das métricas principais e "
        "são reportados à parte (D-031).",
        f"- Classes com poucos exemplos (< {FEW_DEV} no dev ou < {FEW_TEST} no test): "
        f"{', '.join(f'`{c}`' for c in few) or 'nenhuma'}.",
        "- Os rótulos v1.1 saem mecanicamente dos rótulos v1 (`data/gold/labels_v1.csv`) via "
        "`python -m src.labeling.migrate` (D-034); ver a última seção.",
        "",
        "## Classes por split",
        "",
        md_table(table),
        "",
        "Pesos por nota usados na reponderação (participação no universo / na amostra):",
        "",
        md_table(weights_t),
        "",
        "## Composição de classes por nota",
        "",
        "Contagem e participação de cada classe dentro de cada nota, com todos os rotulados "
        "(dev + test; 50 itens por nota).",
        "",
        md_table(composition_by_score(df)),
        "",
        "### Cobertura de uma classificação restrita a notas ≤ 3",
        "",
        f"Notas 1 a 3 são {pct(low_share)} dos comentários do universo. A tabela mostra a fração "
        "reponderada do volume de cada classe que está em notas ≤ 3 (sem ambíguos), ou seja, o "
        "que a Fase 6 alcançaria classificando só essas notas. `n` é o número de itens da "
        "classe; com n pequeno, a fração é instável.",
        "",
        md_table(low_score_coverage(df, weights)),
        "",
        "## Causa secundária",
        "",
        f"{n_sec} de {len(df)} itens têm causa secundária ({pct(n_sec / len(df))}). É "
        "informativa e não entra nas métricas (D-034).",
        "",
        md_table(secondary_table(df)),
        "",
        "## Notas livres",
        "",
        f"{n_notes} itens com nota livre, agrupadas pelo texto da nota (minúsculas).",
        "",
        md_table(notes_table(df)),
        "",
        "## Migração v1 → v1.1",
        "",
        "Itens cuja causa principal mudou (regras mecânicas de D-034; nenhum item rejulgado):",
        "",
        md_table(migration_table(v1, df)),
        "",
        "Evidência usada para justificar a v1.1, calculada **só no dev** com os rótulos v1:",
        "",
        md_table(dev_evidence(v1, delivered)),
        "",
    ]
    path = resolve_path(cfg["paths"]["reports_dir"]) / "gold_set.md"
    path.write_text("\n".join(out), encoding="utf-8", newline="\n")
    print(f"Relatório gravado em {path}")


if __name__ == "__main__":
    main()
