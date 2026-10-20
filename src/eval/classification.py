"""Métricas do classificador de causa contra o gold set: por classe, macro-F1 com e sem
reponderação pela nota, matriz de confusão, falha de schema e tempo por item.

Itens "ambíguo" ficam fora das métricas principais (D-031). Falha de schema conta como erro,
com o rótulo `FAIL`, para não melhorar a métrica descartando os itens difíceis.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd
from sklearn.metrics import confusion_matrix, f1_score, precision_recall_fscore_support

from src.taxonomy import AMBIGUOUS, CAUSES

FAIL = "FAIL"  # previsão sem JSON válido depois das tentativas
SHORT = {
    "problema_entrega": "entrega",
    "produto_defeituoso_ou_danificado": "defeito",
    "produto_diferente_do_anunciado": "diferente",
    "pedido_incompleto_ou_errado": "incompleto",
    "qualidade_insatisfatoria": "qualidade",
    "problema_atendimento_ou_comunicacao": "atendimento",
    "elogio": "elogio",
    "outro": "outro",
    FAIL: FAIL,
}


@dataclass(frozen=True)
class Scored:
    """Gold e previsão alinhados (só não ambíguos), com o peso da nota de cada item."""

    gold: pd.Series
    pred: pd.Series
    weight: pd.Series


def align(gold: pd.DataFrame, pred: pd.DataFrame, weights: pd.Series) -> Scored:
    """`gold`: review_id, review_score, causa. `pred`: review_id, causa ("" = falha de schema)."""
    m = gold.merge(pred[["review_id", "causa"]], on="review_id", suffixes=("_gold", "_pred"))
    if len(m) != len(gold):
        raise ValueError(f"previsões para {len(m)} de {len(gold)} itens do gold")
    m = m[m["causa_gold"] != AMBIGUOUS]
    p = m["causa_pred"].replace("", FAIL).fillna(FAIL)
    return Scored(
        gold=m["causa_gold"].reset_index(drop=True),
        pred=p.reset_index(drop=True),
        weight=m["review_score"].map(weights).reset_index(drop=True),
    )


def per_class(s: Scored, *, reweighted: bool) -> pd.DataFrame:
    w = s.weight if reweighted else None
    prec, rec, f1, _ = precision_recall_fscore_support(
        s.gold, s.pred, labels=list(CAUSES), sample_weight=w, zero_division=0
    )
    support = s.gold.value_counts().reindex(CAUSES, fill_value=0)
    return pd.DataFrame(
        {"classe": CAUSES, "precisão": prec, "recall": rec, "F1": f1, "n": support.values}
    )


def macro_f1(s: Scored, *, reweighted: bool) -> float:
    w = s.weight if reweighted else None
    return float(
        f1_score(
            s.gold, s.pred, labels=list(CAUSES), average="macro", sample_weight=w, zero_division=0
        )
    )


def accuracy(s: Scored, *, reweighted: bool) -> float:
    hit = (s.gold == s.pred).astype(float)
    return float(np.average(hit, weights=s.weight if reweighted else None))


def bootstrap_macro_f1(s: Scored, *, n: int = 1000, seed: int = 42) -> tuple[float, float]:
    """IC 95% percentil do macro-F1 sem reponderação, reamostrando itens."""
    rng = np.random.default_rng(seed)
    vals = []
    for _ in range(n):
        idx = rng.integers(0, len(s.gold), len(s.gold))
        b = Scored(s.gold.iloc[idx], s.pred.iloc[idx], s.weight.iloc[idx])
        vals.append(macro_f1(b, reweighted=False))
    lo, hi = np.percentile(vals, [2.5, 97.5])
    return float(lo), float(hi)


def confusion(s: Scored) -> pd.DataFrame:
    """Linhas = gold, colunas = previsão (com `FAIL` se houver), nomes curtos."""
    cols = [*CAUSES, FAIL] if (s.pred == FAIL).any() else list(CAUSES)
    cm = confusion_matrix(s.gold, s.pred, labels=cols)[: len(CAUSES)]
    df = pd.DataFrame(cm, columns=[SHORT[c] for c in cols])
    df.insert(0, "gold \\ previsto", [SHORT[c] for c in CAUSES])
    return df
