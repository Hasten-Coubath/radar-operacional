"""Relatório da Fase 3: baseline e LLM v1 (com e sem raciocínio) contra o gold set do dev.

Uso: `python -m src.eval.dev_report`. Lê as previsões de `data/predictions/` e grava
`reports/fase3_dev.md`. Só o dev: o test set fica para a Fase 5. Métodos sem arquivo de
previsões aparecem como pendentes.
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from pathlib import Path

import pandas as pd

from src.classifier.run import PREDICTIONS_DIR
from src.config import load_config, resolve_path
from src.data.stats import md_table, pct
from src.eval.classification import (
    FAIL,
    SHORT,
    Scored,
    accuracy,
    align,
    bootstrap_macro_f1,
    confusion,
    macro_f1,
    per_class,
)
from src.labeling.gold import load_gold_sample
from src.labeling.report import score_weights
from src.labeling.store import LabelStore
from src.taxonomy import AMBIGUOUS


@dataclass(frozen=True)
class Method:
    name: str
    file: str


METHODS = (
    Method("baseline TF-IDF+LR (CV 5 partes)", "baseline_v1_dev_cv.csv"),
    Method("LLM v1 sem raciocínio", "classifier_v1_dev.csv"),
    Method("LLM v1 com raciocínio", "classifier_think_v1_dev.csv"),
)
ERRORS_OF = "classifier_v1_dev.csv"  # lista de erros para a análise da Fase 4


def summary_row(name: str, s: Scored, pred: pd.DataFrame) -> dict[str, str]:
    lo, hi = bootstrap_macro_f1(s)
    fails = int((pred["causa"].fillna("") == "").sum())
    lat = pred["latency_s"]
    row = {
        "método": name,
        "macro-F1": f"{macro_f1(s, reweighted=False):.3f} [{lo:.3f}; {hi:.3f}]",
        "macro-F1 reponderado": f"{macro_f1(s, reweighted=True):.3f}",
        "acurácia": f"{accuracy(s, reweighted=False):.3f}",
        "acurácia reponderada": f"{accuracy(s, reweighted=True):.3f}",
        "falha de schema": f"{fails}/{len(pred)} ({pct(fails / len(pred))})",
        "s/item, mediana (média)": f"{lat.median():.3g} ({lat.mean():.3g})",
    }
    if "attempts" in pred:
        row["itens com 2ª tentativa"] = str(int((pred["attempts"] > 1).sum()))
    else:
        row["itens com 2ª tentativa"] = "—"
    return row


def class_metrics(s: Scored) -> pd.DataFrame:
    plain = per_class(s, reweighted=False)
    rew = per_class(s, reweighted=True)
    out = plain[["classe", "n", "precisão", "recall", "F1"]].copy()
    out["F1 reponderado"] = rew["F1"]
    out["classe"] = out["classe"].map(SHORT)
    return out


def ambiguous_predictions(gold: pd.DataFrame, preds: dict[str, pd.DataFrame]) -> pd.DataFrame:
    amb = gold.loc[gold["causa"] == AMBIGUOUS, ["review_id", "review_score"]]
    out = amb.rename(columns={"review_score": "nota"}).copy()
    for name, p in preds.items():
        out[name] = out["review_id"].map(p.set_index("review_id")["causa"]).replace("", FAIL)
        out[name] = out[name].map(lambda c: SHORT.get(c, c))
    out["review_id"] = out["review_id"].str[:8]
    return out


def score_shortcut(gold: pd.DataFrame, preds: dict[str, pd.DataFrame]) -> pd.DataFrame:
    """D-029: acerto por nota e erros na direção "nota alta → elogio" / "nota baixa → problema"."""
    clear = gold[gold["causa"] != AMBIGUOUS]
    rows = []
    for name, p in preds.items():
        m = clear.merge(p[["review_id", "causa"]], on="review_id", suffixes=("", "_pred"))
        row: dict[str, str] = {"método": name}
        for s in range(1, 6):
            part = m[m["review_score"] == s]
            row[f"acerto nota {s}"] = f"{(part['causa'] == part['causa_pred']).mean():.2f}"
        hi = m[(m["review_score"] >= 4) & (m["causa"] != "elogio")]
        lo = m[(m["review_score"] <= 2) & (m["causa"] == "elogio")]
        row["nota 4–5, gold ≠ elogio, previsto elogio"] = (
            f"{int((hi['causa_pred'] == 'elogio').sum())}/{len(hi)}"
        )
        row["nota 1–2, gold = elogio, previsto ≠ elogio"] = (
            f"{int((lo['causa_pred'] != 'elogio').sum())}/{len(lo)}"
        )
        rows.append(row)
    return pd.DataFrame(rows)


def delivery_agreement(
    gold: pd.DataFrame, preds: dict[str, pd.DataFrame], late: pd.Series
) -> pd.DataFrame:
    """Observação: `problema_entrega` (gold ou previsto) × pedido atrasado ou não entregue.

    `late` é retrospectivo (data final de entrega, `orders.is_late`), não point-in-time: serve
    só para descrever a concordância, não entra em métrica nem em decisão.
    """
    sources = {"gold (não ambíguos)": gold[gold["causa"] != AMBIGUOUS][["review_id", "causa"]]}
    sources.update({name: p[["review_id", "causa"]] for name, p in preds.items()})
    rows = []
    for name, df in sources.items():
        entrega = df["causa"] == "problema_entrega"
        obj = df["review_id"].map(late).fillna(False).astype(bool)
        both = int((entrega & obj).sum())
        rows.append(
            {
                "fonte": name,
                "itens": len(df),
                "previsto/rotulado entrega": int(entrega.sum()),
                "com atraso ou sem entrega": f"{both}/{int(entrega.sum())}",
                "atrasados ou sem entrega no total": int(obj.sum()),
                "desses, com causa entrega": f"{both}/{int(obj.sum())}",
                "concordância (sim/sim + não/não)": pct(float((entrega == obj).mean())),
            }
        )
    return pd.DataFrame(rows)


def error_list(gold: pd.DataFrame, pred: pd.DataFrame) -> pd.DataFrame:
    m = gold[gold["causa"] != AMBIGUOUS].merge(
        pred[["review_id", "causa", "confianca"]], on="review_id", suffixes=("_gold", "_pred")
    )
    err = m[m["causa_gold"] != m["causa_pred"]].sort_values(["causa_gold", "causa_pred"])
    return pd.DataFrame(
        {
            "review_id": err["review_id"].str[:8],
            "nota": err["review_score"],
            "gold": err["causa_gold"].map(SHORT),
            "previsto": err["causa_pred"].replace("", FAIL).map(SHORT),
            "confiança": err["confianca"],
        }
    )


def main() -> None:
    cfg = load_config()
    gold_dir = resolve_path(cfg["paths"]["gold_dir"])
    sample = load_gold_sample(gold_dir)
    labels = pd.DataFrame([lb.model_dump() for lb in LabelStore(gold_dir).load().values()])
    gold = sample[sample["split"] == "dev"].merge(labels[["review_id", "causa"]], on="review_id")
    con = sqlite3.connect(f"file:{resolve_path(cfg['paths']['db_path'])}?mode=ro", uri=True)
    pop = pd.read_sql(
        "SELECT review_score, COUNT(*) n FROM reviews WHERE has_comment = 1 GROUP BY review_score",
        con,
    ).set_index("review_score")["n"]
    late = (
        pd.read_sql(
            "SELECT ro.review_id, MAX(o.is_late = 1 OR o.delivered_customer_ts IS NULL) AS late "
            "FROM review_orders ro JOIN orders o USING (order_id) GROUP BY ro.review_id",
            con,
        )
        .set_index("review_id")["late"]
        .astype(bool)
    )
    con.close()
    weights = score_weights(gold, pop / pop.sum())

    pred_dir = resolve_path(PREDICTIONS_DIR)
    preds: dict[str, pd.DataFrame] = {}
    missing: list[str] = []
    for m in METHODS:
        path = Path(pred_dir) / m.file
        if path.exists():
            preds[m.name] = pd.read_csv(path, dtype={"causa": str}, keep_default_na=False)
        else:
            missing.append(m.name)
    scored = {name: align(gold, p, weights) for name, p in preds.items()}
    n_clear = int((gold["causa"] != AMBIGUOUS).sum())

    out = [
        "# Fase 3: baseline e LLM v1 no dev",
        "",
        "_Gerado por `python -m src.eval.dev_report`. Não edite à mão._",
        "",
        f"- Dev: {len(gold)} itens, {n_clear} não ambíguos nas métricas (D-031). Taxonomia v1.1, "
        "8 classes.",
        "- Macro-F1 entre colchetes: IC 95% por bootstrap (1.000 reamostragens, semente 42). "
        "Reponderado: cada item pesa pela participação da sua nota no universo (D-028).",
        "- Falha de schema conta como erro (`FAIL`). Tempo do LLM: latência da chamada, com o "
        "modelo já carregado; do baseline: só a previsão (o ajuste está em `fit_s` no CSV).",
        "- Classes com poucos itens no dev (atendimento 3, outro 4) têm F1 instável.",
    ]
    if missing:
        out.append(f"- Pendente (sem previsões ainda): {', '.join(missing)}.")
    out += [
        "",
        "## Resumo",
        "",
        md_table(pd.DataFrame([summary_row(n, scored[n], preds[n]) for n in preds])),
        "",
        "## Métricas por classe",
        "",
    ]
    for name, s in scored.items():
        out += [f"### {name}", "", md_table(class_metrics(s)), ""]
    out += ["## Matrizes de confusão (linhas = gold, colunas = previsto)", ""]
    for name, s in scored.items():
        out += [f"### {name}", "", md_table(confusion(s)), ""]
    out += [
        "## Itens ambíguos (fora das métricas)",
        "",
        md_table(ambiguous_predictions(gold, preds)),
        "",
        "## A nota como atalho (D-029)",
        "",
        "Acerto por nota e erros na direção da nota. No gold set, todos os itens de nota 5 são "
        "`elogio`, então o atalho nota 5 → elogio não é penalizado aqui.",
        "",
        md_table(score_shortcut(gold, preds)),
        "",
        "## Observação: causa de entrega × sinal objetivo de entrega",
        "",
        "Só descritivo, sem métrica: a flag de atraso foi removida (D-033). O sinal objetivo é "
        "retrospectivo: pedido entregue depois da data estimada (`orders.is_late`) ou nunca "
        "entregue. Reclamação de demora dentro do prazo e atraso sem reclamação são esperados "
        "(taxonomia, `problema_entrega`).",
        "",
        md_table(delivery_agreement(gold, preds, late)),
        "",
    ]
    if ERRORS_OF in {m.file for m in METHODS if m.name in preds}:
        name = next(m.name for m in METHODS if m.file == ERRORS_OF)
        err = error_list(gold, preds[name])
        out += [
            f"## Erros do {name} (insumo da Fase 4)",
            "",
            f"{len(err)} erros em {n_clear} itens. Só IDs e rótulos; a leitura dos textos está "
            "em `docs/erros.md`.",
            "",
            md_table(err),
            "",
        ]
    path = resolve_path(cfg["paths"]["reports_dir"]) / "fase3_dev.md"
    path.write_text("\n".join(out), encoding="utf-8", newline="\n")
    print(f"Relatório gravado em {path}")


if __name__ == "__main__":
    main()
