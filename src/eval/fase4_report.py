"""Relatório da Fase 4: regra de aceite v1 → v2, comparação item a item e limiar de confiança.

Uso: `python -m src.eval.fase4_report`. Só o dev. A regra de aceite e a regra de escolha do
limiar foram fixadas antes de rodar a v2 (D-044); este script só as aplica.
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd

from src.classifier.run import PREDICTIONS_DIR
from src.config import load_config, resolve_path
from src.data.stats import md_table, pct
from src.eval.classification import SHORT, align, macro_f1
from src.eval.dev_report import load_split
from src.taxonomy import AMBIGUOUS

V1, V2 = "classifier_v1_dev.csv", "classifier_v2_dev.csv"
RARE = ("produto_diferente_do_anunciado", "problema_atendimento_ou_comunicacao", "outro")
MAX_SENT = 0.15  # no máximo 15% dos itens para revisão humana
MIN_GAIN = 0.02  # ganho mínimo de acurácia do restante para usar limiar


def acceptance(
    gold: pd.DataFrame, v1: pd.DataFrame, v2: pd.DataFrame, w: pd.Series
) -> pd.DataFrame:
    s1, s2 = align(gold, v1, w), align(gold, v2, w)
    f1, f2 = macro_f1(s1, reweighted=False), macro_f1(s2, reweighted=False)
    m = item_table(gold, v1, v2)
    rare_lost = m[m["gold"].isin(RARE) & m["acerto_v1"] & ~m["acerto_v2"]]
    fail1 = int((v1["causa"] == "").sum())
    fail2 = int((v2["causa"] == "").sum())
    return pd.DataFrame(
        [
            {
                "condição": "1. macro-F1 principal v2 ≥ v1",
                "v1": f"{f1:.3f}",
                "v2": f"{f2:.3f}",
                "passa": "sim" if f2 >= f1 else "não",
            },
            {
                "condição": "2. nenhum acerto perdido em classe rara",
                "v1": "—",
                "v2": f"{len(rare_lost)} perdidos",
                "passa": "sim" if rare_lost.empty else "não",
            },
            {
                "condição": "3. falhas de schema v2 ≤ v1",
                "v1": str(fail1),
                "v2": str(fail2),
                "passa": "sim" if fail2 <= fail1 else "não",
            },
        ]
    )


def item_table(gold: pd.DataFrame, v1: pd.DataFrame, v2: pd.DataFrame) -> pd.DataFrame:
    clear = gold[gold["causa"] != AMBIGUOUS][["review_id", "review_score", "causa"]]
    m = clear.rename(columns={"causa": "gold"})
    m = m.merge(v1[["review_id", "causa"]].rename(columns={"causa": "v1"}), on="review_id")
    m = m.merge(v2[["review_id", "causa"]].rename(columns={"causa": "v2"}), on="review_id")
    m["acerto_v1"] = m["v1"] == m["gold"]
    m["acerto_v2"] = m["v2"] == m["gold"]
    return m


def changes(m: pd.DataFrame) -> pd.DataFrame:
    """Itens em que a previsão mudou entre v1 e v2."""
    ch = m[m["v1"] != m["v2"]].copy()
    ch["efeito"] = [
        "ganho" if b and not a else "perda" if a and not b else "erro trocado por outro erro"
        for a, b in zip(ch["acerto_v1"], ch["acerto_v2"], strict=True)
    ]
    return pd.DataFrame(
        {
            "review_id": ch["review_id"].str[:8],
            "nota": ch["review_score"],
            "gold": ch["gold"].map(SHORT),
            "v1": ch["v1"].map(SHORT),
            "v2": ch["v2"].map(SHORT),
            "efeito": ch["efeito"],
        }
    )


def threshold_curve(gold: pd.DataFrame, pred: pd.DataFrame) -> pd.DataFrame:
    """Para cada limiar c: % com confiança < c (revisão humana) e acurácia do restante."""
    clear = gold[gold["causa"] != AMBIGUOUS][["review_id", "causa"]]
    m = clear.merge(pred[["review_id", "causa", "confianca"]], on="review_id", suffixes=("", "_p"))
    m["acerto"] = m["causa"] == m["causa_p"]
    rows = []
    for c in [0.0, *sorted(m["confianca"].unique())]:
        sent = m["confianca"] < c
        rest = m[~sent]
        rows.append(
            {
                "limiar": c,
                "enviados": int(sent.sum()),
                "% enviada": float(sent.mean()),
                "acurácia do restante": float(rest["acerto"].mean()) if len(rest) else float("nan"),
                "erros entre os enviados": int((~m.loc[sent, "acerto"]).sum()),
            }
        )
    return pd.DataFrame(rows)


def choose_threshold(curve: pd.DataFrame) -> tuple[float, str]:
    """Regra de D-044: maior acurácia do restante com ≤ 15% enviados; empate, o que envia menos;
    sem ganho ≥ 2 p.p. sobre não enviar nada, não usa limiar."""
    base = float(curve.loc[curve["limiar"] == 0.0, "acurácia do restante"].iloc[0])
    ok = curve[curve["% enviada"] <= MAX_SENT].sort_values(
        ["acurácia do restante", "% enviada"], ascending=[False, True]
    )
    best = ok.iloc[0]
    gain = float(best["acurácia do restante"]) - base
    if gain < MIN_GAIN:
        return 0.0, (
            f"sem limiar: o melhor limiar com ≤ {MAX_SENT:.0%} enviados ganha "
            f"{100 * gain:.1f} p.p. "
            f"(< {100 * MIN_GAIN:.0f} p.p.) sobre não enviar nada; dentro desse orçamento "
            "a confiança não separa os erros"
        )
    return float(best["limiar"]), (
        f"limiar {best['limiar']:.2f}: envia {pct(float(best['% enviada']))} e a acurácia do "
        f"restante vai de {pct(base)} para {pct(float(best['acurácia do restante']))}"
    )


def main() -> None:
    cfg = load_config()
    gold, weights, _ = load_split(cfg, "dev")
    d = Path(resolve_path(PREDICTIONS_DIR))
    v1 = pd.read_csv(d / V1, keep_default_na=False)
    v2 = pd.read_csv(d / V2, keep_default_na=False)
    acc = acceptance(gold, v1, v2, weights)
    accepted = bool((acc["passa"] == "sim").all())
    chosen, chosen_file = ("v2", v2) if accepted else ("v1", v1)
    m = item_table(gold, v1, v2)
    ch = changes(m)
    curve = threshold_curve(gold, chosen_file)
    limiar, why = choose_threshold(curve)
    shown = curve.assign(
        **{
            "% enviada": curve["% enviada"].map(pct),
            "acurácia do restante": curve["acurácia do restante"].map(pct),
        }
    )
    out = [
        "# Fase 4: LLM v1 → v2 no dev",
        "",
        "_Gerado por `python -m src.eval.fase4_report`. Não edite à mão._",
        "",
        "Protocolo fixado antes de rodar a v2 (D-044): uma única iteração, regra de aceite e "
        "regra do limiar definidas a priori. A v2 (`prompts/classifier_v2.md`) só mexe nas "
        "categorias 2 a 5 de `docs/erros.md` e não muda definições de classe (D-041). Métricas "
        "completas dos dois prompts em `reports/fase3_dev.md`.",
        "",
        "## Regra de aceite",
        "",
        md_table(acc),
        "",
        f"**Resultado: {'a v2 substitui a v1' if accepted else 'a v1 continua'}** "
        f"(configuração escolhida: prompt {chosen}, sem raciocínio).",
        "",
        "## Comparação item a item (itens em que a previsão mudou)",
        "",
        f"{len(ch)} de {len(m)} itens não ambíguos mudaram: "
        f"{int((ch['efeito'] == 'ganho').sum())} ganhos, "
        f"{int((ch['efeito'] == 'perda').sum())} perdas, "
        f"{int((ch['efeito'] == 'erro trocado por outro erro').sum())} erros trocados. "
        f"Acertos: v1 {int(m['acerto_v1'].sum())}, v2 {int(m['acerto_v2'].sum())}.",
        "",
        md_table(ch) if len(ch) else "_nenhum_",
        "",
        f"## Limiar de confiança para revisão humana (prompt {chosen})",
        "",
        "Itens com confiança abaixo do limiar iriam para revisão humana. Regra de escolha "
        f"(D-044): maior acurácia do restante com no máximo {MAX_SENT:.0%} enviados; em empate, "
        f"o que envia menos; sem ganho de pelo menos {100 * MIN_GAIN:.0f} p.p., não usar limiar.",
        "",
        md_table(shown),
        "",
        f"**Proposta: {why}.**",
        "",
    ]
    path = resolve_path(cfg["paths"]["reports_dir"]) / "fase4_dev.md"
    path.write_text("\n".join(out), encoding="utf-8", newline="\n")
    print(f"Relatório gravado em {path}")


if __name__ == "__main__":
    main()
