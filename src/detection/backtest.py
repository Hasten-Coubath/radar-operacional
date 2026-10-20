"""Backtest semanal do Radar contra as linhas de base (D-026, D-043, D-047, D-048).

Uso:
- `python -m src.detection.backtest --period calibracao`: só 2017. O gabarito é calculado com
  dados até 2017-12-31. Escolhe o θ de cada método e grava `reports/backtest_calibracao.json`.
- `python -m src.detection.backtest --period avaliacao`: 2018, uma única vez, com os θ gravados.
  Exige o lote da Fase 6 completo.

Métodos: Radar (maior escore entre as famílias de causa), B1 (queda da nota média), B2 (fração
de notas ≤ 2), B3 (atraso point-in-time, referência).
"""

from __future__ import annotations

import argparse
import json
import sqlite3
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from src.classifier.batch import CLASSIFIED, MAX_SCORE, SCHEMA_FAIL, output_path
from src.config import load_config, resolve_path
from src.data.stats import analysis_window, md_table
from src.detection.core import (
    KEYS,
    WEEK,
    alerts,
    anomalous_weeks,
    calibrate,
    evaluate,
    incidents,
    mean_drop_signal,
    proportion_signal,
    week_range,
)
from src.detection.data import (
    FAMILIES,
    monitored_segments,
    review_table,
    type_a_table,
    type_b_table,
)

HISTORY_START = "2016-08-01"
CAL = ("2017-02-06", "2017-12-25")
EVAL = ("2018-01-01", "2018-08-13")
N_MIN_REVIEWS, N_MIN_COHORT = 20, 30  # D-048
N_MIN_A, N_MIN_B = 30, 20  # D-026
METHODS = ("Radar", "B1", "B2", "B3")
CASE_SELLER = "5dceca12"  # D-026: caso a examinar na categoria do vendedor
THETA_FILE = "backtest_calibracao.json"
FA_LEVELS = (0.25, 0.5, 0.75, 1.0)  # níveis da comparação em FA/semana iguais (descritiva)


def load_predictions(path: Path) -> pd.DataFrame | None:
    if not path.exists():
        return None
    return pd.read_csv(path, dtype=str, keep_default_na=False)


def lote_missing(con: sqlite3.Connection, preds: pd.DataFrame | None, until: str) -> int:
    """Quantos comentários com nota ≤ 3 respondidos até `until` ainda não estão no lote."""
    need = pd.read_sql(
        "SELECT review_id FROM reviews WHERE has_comment = 1 AND review_score <= ? "
        "AND answered_week <= ?",
        con,
        params=(MAX_SCORE, until),
    )["review_id"]
    if preds is None:
        return len(need)
    done = set(preds.loc[preds["status"].isin([CLASSIFIED, SCHEMA_FAIL]), "review_id"])
    return int((~need.isin(done)).sum())


def ground_truth(
    con: sqlite3.Connection, segs: pd.DataFrame, weeks: pd.DatetimeIndex
) -> pd.DataFrame:
    """Incidentes tipo A e B (gabarito, D-026) com os dados das semanas em `weeks`."""
    a = anomalous_weeks(type_a_table(con, segs, weeks), "late", "due", N_MIN_A)
    b = anomalous_weeks(type_b_table(con, segs, weeks), "le2", "n", N_MIN_B)
    return pd.concat([incidents(a, "A"), incidents(b, "B")], ignore_index=True)


def method_scores(
    con: sqlite3.Connection, segs: pd.DataFrame, weeks: pd.DatetimeIndex, preds: pd.DataFrame
) -> dict[str, pd.DataFrame]:
    """Escore semanal de cada método por segmento (D-048); o Radar guarda a família do maior."""
    rev = review_table(con, segs, weeks, preds)
    base = rev[[*KEYS, "week"]].copy()
    fam_scores = pd.DataFrame(
        {f: proportion_signal(rev, f"fam_{f}", "n", N_MIN_REVIEWS) for f in FAMILIES}
    )
    radar = base.assign(
        score=fam_scores.max(axis=1, skipna=True),
        familia=fam_scores.fillna(-np.inf).idxmax(axis=1).where(fam_scores.notna().any(axis=1)),
    )
    b1 = base.assign(score=mean_drop_signal(rev, "n", "s", "ss", N_MIN_REVIEWS))
    b2 = base.assign(score=proportion_signal(rev, "le2", "n", N_MIN_REVIEWS))
    ta = type_a_table(con, segs, weeks)
    b3 = ta[[*KEYS, "week"]].assign(score=proportion_signal(ta, "late", "due", N_MIN_COHORT))
    return {"Radar": radar, "B1": b1, "B2": b2, "B3": b3}


def summary_at(
    scores: dict[str, pd.DataFrame],
    thetas: dict[str, float | None],
    inc_all: pd.DataFrame,
    weeks: pd.DatetimeIndex,
) -> tuple[pd.DataFrame, dict[str, pd.DataFrame]]:
    rows, detected = [], {}
    for m in METHODS:
        theta = thetas[m]
        if theta is None:
            rows.append({"método": m, "θ": "—"})
            continue
        al = alerts(scores[m], theta, weeks)
        inc, n_fa, fa_week = evaluate(al, inc_all, weeks)
        detected[m] = inc.merge(
            al, left_on=[*KEYS, "detected"], right_on=[*KEYS, "week"], how="left"
        )
        row: dict[str, Any] = {
            "método": m,
            "θ": theta,
            "alertas": len(al),
            "falsos alarmes": n_fa,
            "FA/semana": round(fa_week, 2),
        }
        for kind in ("A", "B"):
            sub = inc[inc["tipo"] == kind]
            row[f"recall {kind}"] = f"{int(sub['detected'].notna().sum())}/{len(sub)}"
        rows.append(row)
    return pd.DataFrame(rows), detected


def lead_table(detected: dict[str, pd.DataFrame]) -> pd.DataFrame:
    """Antecedência do Radar sobre B1 (e B2), em semanas: positivo = Radar antes (D-026)."""
    rows = []
    r = detected.get("Radar")
    for other in ("B1", "B2"):
        o = detected.get(other)
        if r is None or o is None:
            continue
        m = r[[*KEYS, "tipo", "start", "detected"]].merge(
            o[[*KEYS, "tipo", "start", "detected"]],
            on=[*KEYS, "tipo", "start"],
            suffixes=("_r", "_o"),
        )
        for kind in ("A", "B"):
            sub = m[m["tipo"] == kind]
            both = sub.dropna(subset=["detected_r", "detected_o"])
            lead = (both["detected_o"] - both["detected_r"]) / WEEK
            rows.append(
                {
                    "comparação": f"Radar vs {other}",
                    "tipo": kind,
                    "incidentes": len(sub),
                    "ambos detectam": len(both),
                    "só Radar": int((sub["detected_r"].notna() & sub["detected_o"].isna()).sum()),
                    "só o outro": int((sub["detected_r"].isna() & sub["detected_o"].notna()).sum()),
                    "antecedência mediana (sem)": float(lead.median())
                    if len(lead)
                    else float("nan"),
                    "antecedência média (sem)": float(lead.mean()) if len(lead) else float("nan"),
                }
            )
    return pd.DataFrame(rows)


def incident_table(detected: dict[str, pd.DataFrame]) -> pd.DataFrame:
    """Incidente por incidente: semana de detecção de cada método, família do alerta do Radar e
    antecedência do Radar sobre B1 e B2 (semanas; positivo = Radar antes)."""
    r = detected.get("Radar")
    if r is None:
        return pd.DataFrame()
    on = [*KEYS, "tipo", "start"]
    out = r[[*on, "end", "detected", "familia"]].rename(
        columns={"detected": "Radar", "familia": "família (Radar)"}
    )
    for m in ("B1", "B2", "B3"):
        if m in detected:
            d = detected[m][[*on, "detected"]].rename(columns={"detected": m})
            out = out.merge(d, on=on, how="left")
    for m in ("B1", "B2"):
        if m in out:
            lead = (out[m] - out["Radar"]) / WEEK
            out[f"antecedência vs {m} (sem)"] = [
                "" if pd.isna(x) else (f"{x:+.0f}" if x else "0") for x in lead
            ]
    out = out.sort_values(["start", *KEYS]).reset_index(drop=True)
    for c in ("start", "end", "Radar", "B1", "B2", "B3"):
        if c in out:
            out[c] = [("—" if pd.isna(x) else f"{x:%Y-%m-%d}") for x in out[c]]
    out["família (Radar)"] = out["família (Radar)"].fillna("")
    return out


def curve_wide(curve: pd.DataFrame) -> pd.DataFrame:
    """Curva completa na grade de θ: FA/semana e recall de cada método, lado a lado."""
    parts = []
    for m, c in curve.groupby("método", sort=False):
        parts.append(
            c.set_index("theta")[["fa_por_semana", "recall_A", "recall_B"]].rename(
                columns={
                    "fa_por_semana": f"{m} FA/sem",
                    "recall_A": f"{m} recall A",
                    "recall_B": f"{m} recall B",
                }
            )
        )
    return pd.concat(parts, axis=1).reset_index().rename(columns={"theta": "θ"})


def equal_fa_table(curve: pd.DataFrame, levels: tuple[float, ...] = FA_LEVELS) -> pd.DataFrame:
    """Recall em níveis iguais de FA/semana. Para cada método e nível, o menor θ da grade com
    FA/semana ≤ nível (a regra da calibração, D-048: o degrau que não ultrapassa o nível)."""
    rows: list[dict[str, Any]] = []
    for level in levels:
        for m, c in curve.groupby("método", sort=False):
            ok = c[c["fa_por_semana"] <= level]
            row: dict[str, Any] = {"nível (FA/sem ≤)": level, "método": m}
            if ok.empty:
                rows.append(row | {"θ": "—"})
                continue
            best = ok.loc[ok["theta"].idxmin()]
            row |= {"θ": float(best["theta"]), "FA/sem": float(best["fa_por_semana"])}
            for kind in ("A", "B"):
                n = int(best[f"n_{kind}"])
                hit = 0 if n == 0 else round(float(best[f"recall_{kind}"]) * n)
                row[f"recall {kind}"] = f"{hit}/{n}"
            rows.append(row)
    return pd.DataFrame(rows)


def onset_table(detected: dict[str, pd.DataFrame]) -> pd.DataFrame:
    """Início − semana de detecção, por método e tipo (positivo = antes do início)."""
    rows = []
    for m, d in detected.items():
        for kind in ("A", "B"):
            sub = d[(d["tipo"] == kind) & d["detected"].notna()]
            delta = (sub["start"] - sub["detected"]) / WEEK
            rows.append(
                {
                    "método": m,
                    "tipo": kind,
                    "detectados": len(sub),
                    "início − detecção, mediana (sem)": float(delta.median())
                    if len(sub)
                    else float("nan"),
                }
            )
    return pd.DataFrame(rows)


def diagnosis_table(detected: dict[str, pd.DataFrame]) -> pd.DataFrame:
    """Família do Radar no alerta de detecção × tipo do incidente (D-026, item 1)."""
    r = detected.get("Radar")
    if r is None:
        return pd.DataFrame()
    d = r[r["detected"].notna()]
    rows = []
    for kind, expected in (("A", {"entrega"}), ("B", set(FAMILIES) - {"entrega"})):
        sub = d[d["tipo"] == kind]
        ok = sub["familia"].isin(expected)
        rows.append(
            {
                "tipo": kind,
                "detectados pelo Radar": len(sub),
                "família compatível": f"{int(ok.sum())}/{len(sub)}",
                "famílias no alerta": ", ".join(
                    f"{k}: {v}" for k, v in sub["familia"].value_counts().items()
                ),
            }
        )
    return pd.DataFrame(rows)


def export_alerts(
    scores: dict[str, pd.DataFrame],
    thetas: dict[str, float | None],
    weeks: pd.DatetimeIndex,
    path: Path,
) -> None:
    """Alertas de cada método no θ escolhido, no período (sem texto; entrada do agente)."""
    parts = []
    for m in METHODS:
        theta = thetas.get(m)
        if theta is None:
            continue
        a = alerts(scores[m], theta, weeks).assign(metodo=m)
        parts.append(a)
    al = pd.concat(parts, ignore_index=True) if parts else pd.DataFrame()
    if not al.empty:
        al["week"] = al["week"].dt.strftime("%Y-%m-%d")
        al["score"] = al["score"].round(3)
    al.to_csv(path, index=False, lineterminator="\n")


def case_categories(con: sqlite3.Connection) -> pd.DataFrame:
    """Categorias dos pedidos do vendedor do caso de D-026 (`5dceca12`), por nº de pedidos."""
    return pd.read_sql(
        "SELECT p.category AS segment_value, COUNT(DISTINCT oi.order_id) AS pedidos "
        "FROM order_items oi JOIN products p USING (product_id) "
        "WHERE oi.seller_id LIKE ? GROUP BY p.category ORDER BY pedidos DESC",
        con,
        params=(f"{CASE_SELLER}%",),
    )


def case_section(
    cats: pd.DataFrame,
    segs: pd.DataFrame,
    scores: dict[str, pd.DataFrame],
    theta: float | None,
    inc_all: pd.DataFrame,
) -> list[str]:
    """D-026, item 3: há alerta do Radar ou incidente na categoria do vendedor em mar–mai/2018?"""
    lo, hi = pd.Timestamp("2018-03-05"), pd.Timestamp("2018-05-28")
    monitored = set(segs.loc[segs["segment_type"] == "categoria", "segment_value"])
    rows = []
    for c in cats.itertuples(index=False):
        is_mon = c.segment_value in monitored
        r = scores["Radar"]
        sel = r[(r["segment_type"] == "categoria") & (r["segment_value"] == c.segment_value)]
        sel = sel[(sel["week"] >= lo) & (sel["week"] <= hi)]
        al = sel[sel["score"] > theta] if theta is not None else sel.iloc[0:0]
        inc = inc_all[
            (inc_all["segment_type"] == "categoria")
            & (inc_all["segment_value"] == c.segment_value)
            & (inc_all["end"] >= lo)
            & (inc_all["start"] <= hi)
        ]
        rows.append(
            {
                "categoria": c.segment_value,
                "pedidos do vendedor": int(c.pedidos),
                "monitorada": "sim" if is_mon else "não",
                "alertas do Radar (mar–mai/2018)": ", ".join(
                    f"{w:%Y-%m-%d} ({f})" for w, f in zip(al["week"], al["familia"], strict=True)
                )
                or "nenhum",
                "incidentes no período": ", ".join(
                    f"{t} {s:%Y-%m-%d}→{e:%Y-%m-%d}"
                    for t, s, e in zip(inc["tipo"], inc["start"], inc["end"], strict=True)
                )
                or "nenhum",
            }
        )
    return [
        f"## Caso `{CASE_SELLER}` (D-026, item 3)",
        "",
        "Vendedor não é segmento de detecção (D-021): o caso é examinado pelas categorias dos "
        "seus pedidos. Categoria não monitorada = limitação de cobertura.",
        "",
        md_table(pd.DataFrame(rows)) if rows else "_vendedor sem pedidos_",
        "",
    ]


def fmt_inc(inc: pd.DataFrame) -> pd.DataFrame:
    out = inc.copy()
    for c in ("start", "end"):
        out[c] = out[c].dt.strftime("%Y-%m-%d")
    return out


def run(period: str) -> Path:
    cfg = load_config()
    con = sqlite3.connect(f"file:{resolve_path(cfg['paths']['db_path'])}?mode=ro", uri=True)
    start, end = analysis_window(con)
    segs = monitored_segments(con, start, end)
    preds = load_predictions(output_path())
    reports = Path(resolve_path(cfg["paths"]["reports_dir"]))
    if period == "calibracao":
        until, pweeks = "2017-12-31", week_range(*CAL)
    else:
        until, pweeks = EVAL[1], week_range(*EVAL)
    missing = lote_missing(con, preds, until)
    if missing:
        raise SystemExit(f"Lote incompleto: faltam {missing} comentários com nota ≤ 3 até {until}.")
    weeks = week_range(HISTORY_START, str(min(pd.Timestamp(until), pweeks.max()).date()))
    assert preds is not None
    inc_all = ground_truth(con, segs, weeks)
    scores = method_scores(con, segs, weeks, preds)
    seller_cats = case_categories(con)
    con.close()

    if period == "calibracao":
        thetas: dict[str, float | None] = {}
        curves = []
        for m in METHODS:
            thetas[m], curve = calibrate(scores[m], inc_all, pweeks)
            curves.append(curve.assign(método=m))
        (reports / THETA_FILE).write_text(json.dumps(thetas, indent=2), encoding="utf-8")
    else:
        thetas = json.loads((reports / THETA_FILE).read_text(encoding="utf-8"))
        curves = []
        for m in METHODS:
            curves.append(calibrate(scores[m], inc_all, pweeks)[1].assign(método=m))
    summary, detected = summary_at(scores, thetas, inc_all, pweeks)
    export_alerts(scores, thetas, pweeks, reports / f"alertas_{period}.csv")
    period_inc = inc_all[(inc_all["start"] >= pweeks.min()) & (inc_all["start"] <= pweeks.max())]
    curve_t = pd.concat(curves, ignore_index=True)
    curve_t.to_csv(reports / f"curva_{period}.csv", index=False, lineterminator="\n")
    title = "calibração (2017)" if period == "calibracao" else "avaliação (2018)"
    out = [
        f"# Backtest: {title}",
        "",
        "_Gerado por `python -m src.detection.backtest`. Não edite à mão._",
        "",
        f"- Segmentos monitorados: {len(segs)} ({int((segs['segment_type'] == 'estado').sum())} "
        f"estados, {int((segs['segment_type'] == 'categoria').sum())} categorias).",
        f"- Semanas do período: {len(pweeks)} ({pweeks.min().date()} a {pweeks.max().date()}).",
        f"- Incidentes com início no período: tipo A {int((period_inc['tipo'] == 'A').sum())}, "
        f"tipo B {int((period_inc['tipo'] == 'B').sum())}.",
        "- θ: menor valor da grade com ≤ 1 falso alarme por semana na calibração (D-026, D-048)"
        + ("." if period == "calibracao" else "; aplicado aqui sem mudança."),
        "",
        "## Resultado no θ calibrado",
        "",
        md_table(summary),
        "",
        "## Antecedência",
        "",
        md_table(lead_table(detected)),
        "",
        md_table(onset_table(detected)),
        "",
        "### Incidente por incidente",
        "",
        "Semana da primeira detecção de cada método (— = não detectou). Antecedência = detecção "
        "do outro método − detecção do Radar, em semanas (positivo = Radar antes).",
        "",
        md_table(incident_table(detected)),
        "",
        "## Diagnóstico de causa do Radar",
        "",
        md_table(diagnosis_table(detected)),
        "",
        "## Recall em níveis iguais de falsos alarmes",
        "",
        "Comparação descritiva: o resultado principal é o do θ calibrado, acima. Para cada "
        "método e nível, o menor θ da grade cuja curva **deste período** fica em FA/semana ≤ "
        "nível (o degrau que não ultrapassa o nível, sem interpolar)"
        + (
            "."
            if period == "calibracao"
            else "; esse θ é escolhido olhando 2018, por isso não é um resultado de previsão."
        ),
        "",
        md_table(equal_fa_table(curve_t)),
        "",
        "## Curva recall × falsos alarmes (grade completa)",
        "",
        f"Também em `reports/curva_{period}.csv` (com os falsos alarmes absolutos e o nº de "
        "incidentes).",
        "",
        md_table(curve_wide(curve_t)),
        "",
        "## Incidentes do período",
        "",
        md_table(fmt_inc(period_inc.sort_values(["start", *KEYS]))),
        "",
    ]
    if period == "avaliacao":
        out += case_section(seller_cats, segs, scores, thetas.get("Radar"), inc_all)
    name = "backtest_calibracao.md" if period == "calibracao" else "backtest.md"
    path = reports / name
    path.write_text("\n".join(out), encoding="utf-8", newline="\n")
    print(f"Relatório gravado em {path}")
    return path


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--period", choices=["calibracao", "avaliacao"], required=True)
    args = parser.parse_args()
    run(args.period)


if __name__ == "__main__":
    main()
