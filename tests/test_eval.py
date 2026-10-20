"""Testes das métricas do classificador e do baseline (dados sintéticos)."""

from __future__ import annotations

import pandas as pd
import pytest

from src.classifier.baseline import cross_validated
from src.eval.classification import FAIL, accuracy, align, confusion, macro_f1, per_class
from src.taxonomy import AMBIGUOUS


def gold_pred() -> tuple[pd.DataFrame, pd.DataFrame]:
    gold = pd.DataFrame(
        {
            "review_id": ["a", "b", "c", "d", "e"],
            "review_score": [1, 1, 5, 5, 3],
            "causa": ["problema_entrega", "problema_entrega", "elogio", "elogio", AMBIGUOUS],
        }
    )
    pred = pd.DataFrame(
        {
            "review_id": ["a", "b", "c", "d", "e"],
            "causa": ["problema_entrega", "", "elogio", "elogio", "outro"],
        }
    )
    return gold, pred


def test_schema_failure_counts_as_error_and_ambiguous_is_excluded() -> None:
    gold, pred = gold_pred()
    s = align(gold, pred, pd.Series({1: 1.0, 3: 1.0, 5: 3.0}))
    assert len(s.gold) == 4 and (s.pred == FAIL).sum() == 1
    assert accuracy(s, reweighted=False) == pytest.approx(0.75)
    # reponderado: erro em item de peso 1 contra acertos de peso 1 + 3 + 3
    assert accuracy(s, reweighted=True) == pytest.approx(7 / 8)
    t = per_class(s, reweighted=False).set_index("classe")
    assert t.loc["problema_entrega", "recall"] == pytest.approx(0.5)
    assert t.loc["problema_entrega", "precisão"] == pytest.approx(1.0)
    assert "FAIL" in confusion(s).columns
    # 8 classes no macro: as ausentes entram com F1 = 0
    assert macro_f1(s, reweighted=False) == pytest.approx((2 / 3 + 1.0) / 8)


def test_align_requires_a_prediction_for_every_item() -> None:
    gold, pred = gold_pred()
    with pytest.raises(ValueError):
        align(gold, pred.iloc[:3], pd.Series({1: 1.0, 3: 1.0, 5: 1.0}))


def test_baseline_cv_predicts_every_item_out_of_fold() -> None:
    rows = []
    for i in range(10):
        rows.append(("e", i, 1, "problema_entrega", "não chegou ainda pedido atrasado"))
        rows.append(("g", i, 5, "elogio", "ótimo produto recomendo"))
    rows.append(("x", 0, 3, AMBIGUOUS, "sei lá"))
    dev = pd.DataFrame(
        [(f"{p}{i}", i, s, c, t) for p, i, s, c, t in rows],
        columns=["review_id", "position", "review_score", "causa", "texto"],
    )
    preds, _ = cross_validated(dev, seed=42)
    assert preds["review_id"].tolist() == dev["review_id"].tolist()
    clear = preds[dev["causa"] != AMBIGUOUS]
    assert set(clear["fold"]) == {1, 2, 3, 4, 5}
    assert preds.loc[dev["causa"] == AMBIGUOUS, "fold"].tolist() == [0]
    assert (clear["causa"].values == dev.loc[dev["causa"] != AMBIGUOUS, "causa"].values).all()
