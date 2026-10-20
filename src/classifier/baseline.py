"""Baseline TF-IDF + regressão logística treinado no gold set do dev (D-036).

Uso: `python -m src.classifier.baseline` (dev) ou `--test` (Fase 5: ajuste nos não ambíguos do
dev inteiro e uma previsão do test, D-045). Previsões do dev por validação cruzada estratificada
de 5 partes (semente 42), com os itens não ambíguos. Os ambíguos do dev, que não entram no
treino, são previstos pelo modelo ajustado em todos os não ambíguos. Grava
`data/predictions/baseline_v1_dev_cv.csv`, sem texto (D-035).

Hiperparâmetros fixados a priori, sem busca: com 96 itens não há dados para validar escolhas.
"""

from __future__ import annotations

import argparse
import sqlite3
import time
import warnings
from typing import Any

import numpy as np
import pandas as pd
from sklearn.compose import ColumnTransformer
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import LogisticRegression
from sklearn.model_selection import StratifiedKFold
from sklearn.pipeline import FeatureUnion, Pipeline
from sklearn.preprocessing import OneHotEncoder

from src.classifier.run import PREDICTIONS_DIR
from src.config import load_config, resolve_path
from src.labeling.gold import load_gold_sample
from src.labeling.store import LabelStore
from src.taxonomy import AMBIGUOUS, AREA_BY_CAUSE

METHOD = "baseline_tfidf_lr_v1"
N_FOLDS = 5


def make_model(seed: int) -> Pipeline:
    """Texto: TF-IDF de palavras (1–2) e de caracteres (2–5, robusto a erro de digitação).
    Nota: one-hot (D-029). Regressão logística com pesos balanceados por classe."""
    text = FeatureUnion(
        [
            ("word", TfidfVectorizer(ngram_range=(1, 2), min_df=1, sublinear_tf=True)),
            (
                "char",
                TfidfVectorizer(
                    analyzer="char_wb", ngram_range=(2, 5), min_df=2, sublinear_tf=True
                ),
            ),
        ]
    )
    features = ColumnTransformer(
        [
            ("texto", text, "texto"),
            ("nota", OneHotEncoder(categories=[[1, 2, 3, 4, 5]]), ["review_score"]),
        ]
    )
    clf = LogisticRegression(C=10.0, class_weight="balanced", max_iter=5000, random_state=seed)
    return Pipeline([("features", features), ("clf", clf)])


def load_dev(con: sqlite3.Connection, gold_dir: Any, split: str = "dev") -> pd.DataFrame:
    """Itens do split com nota, texto (título + mensagem, minúsculas) e causa rotulada."""
    sample = load_gold_sample(gold_dir)
    labels = pd.DataFrame([lb.model_dump() for lb in LabelStore(gold_dir).load().values()])
    dev = sample[sample["split"] == split].merge(labels[["review_id", "causa"]], on="review_id")
    ids = dev["review_id"].tolist()
    texts = pd.read_sql(
        "SELECT review_id, COALESCE(comment_title, '') || ' ' || comment_message AS texto "
        f"FROM reviews WHERE review_id IN ({','.join('?' * len(ids))})",
        con,
        params=ids,
    )
    dev = dev.merge(texts, on="review_id")
    dev["texto"] = dev["texto"].str.lower().str.strip()
    return dev.sort_values("position").reset_index(drop=True)


def cross_validated(dev: pd.DataFrame, seed: int) -> tuple[pd.DataFrame, list[str]]:
    """Previsões fora da parte de treino para os não ambíguos; ambíguos pelo modelo completo."""
    clear = dev[dev["causa"] != AMBIGUOUS].reset_index(drop=True)
    amb = dev[dev["causa"] == AMBIGUOUS].reset_index(drop=True)
    X, y = clear[["texto", "review_score"]], clear["causa"]
    folds = StratifiedKFold(n_splits=N_FOLDS, shuffle=True, random_state=seed)
    notes: list[str] = []
    rows: list[dict[str, Any]] = []
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        splits = list(folds.split(X, y))
    notes += sorted({str(w.message) for w in caught})

    def predict(model: Pipeline, part: pd.DataFrame, fold: int, fit_s: float) -> None:
        rows.extend(predict_rows(model, part, fold, fit_s, "dev"))

    for fold, (tr, te) in enumerate(splits, 1):
        model = make_model(seed)
        t0 = time.perf_counter()
        model.fit(X.iloc[tr], y.iloc[tr])
        predict(model, clear.iloc[te], fold, time.perf_counter() - t0)
    if not amb.empty:
        model = make_model(seed)
        t0 = time.perf_counter()
        model.fit(X, y)
        predict(model, amb, 0, time.perf_counter() - t0)
    out = pd.DataFrame(rows).set_index("review_id").loc[dev["review_id"]].reset_index()
    return out, notes


def fit_on_dev_predict(dev: pd.DataFrame, target: pd.DataFrame, seed: int) -> pd.DataFrame:
    """Fase 5: ajusta nos não ambíguos do dev inteiro e prevê todos os itens de `target`."""
    clear = dev[dev["causa"] != AMBIGUOUS]
    model = make_model(seed)
    t0 = time.perf_counter()
    model.fit(clear[["texto", "review_score"]], clear["causa"])
    split = str(target["split"].iloc[0])
    return pd.DataFrame(predict_rows(model, target, -1, time.perf_counter() - t0, split))


def predict_rows(
    model: Pipeline, part: pd.DataFrame, fold: int, fit_s: float, split: str
) -> list[dict[str, Any]]:
    """Uma linha de previsão por item, com o tempo de previsão por item e o de ajuste."""
    rows: list[dict[str, Any]] = []
    t0 = time.perf_counter()
    proba = model.predict_proba(part[["texto", "review_score"]])
    per_item = (time.perf_counter() - t0) / len(part)
    classes = model.classes_
    for rid, p in zip(part["review_id"], proba, strict=True):
        causa = str(classes[int(np.argmax(p))])
        rows.append(
            {
                "review_id": rid,
                "split": split,
                "method": METHOD,
                "fold": fold,
                "causa": causa,
                "confianca": round(float(np.max(p)), 4),
                "area": AREA_BY_CAUSE[causa],
                "schema_ok": True,
                "latency_s": per_item,
                "fit_s": round(fit_s, 3),
            }
        )
    return rows


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--test", action="store_true", help="Fase 5: avaliação única no test")
    args = parser.parse_args()
    cfg = load_config()
    seed = int(cfg["project"]["seed"])
    con = sqlite3.connect(f"file:{resolve_path(cfg['paths']['db_path'])}?mode=ro", uri=True)
    gold_dir = resolve_path(cfg["paths"]["gold_dir"])
    dev = load_dev(con, gold_dir)
    if args.test:
        test = load_dev(con, gold_dir, "test")
        con.close()
        preds = fit_on_dev_predict(dev, test, seed)
        out = resolve_path(PREDICTIONS_DIR) / "baseline_v1_test.csv"
        preds.to_csv(out, index=False, lineterminator="\n")
        print(f"{len(preds)} previsões do test em {out}")
        return
    con.close()
    preds, notes = cross_validated(dev, seed)
    out = resolve_path(PREDICTIONS_DIR) / "baseline_v1_dev_cv.csv"
    out.parent.mkdir(parents=True, exist_ok=True)
    preds.to_csv(out, index=False, lineterminator="\n")
    acc = (preds["causa"].values == dev["causa"].values)[dev["causa"].values != AMBIGUOUS].mean()
    print(f"{len(preds)} previsões em {out}; acurácia CV (não ambíguos): {acc:.3f}")
    for n in notes:
        print(f"aviso do scikit-learn: {n}")


if __name__ == "__main__":
    main()
