"""Seleção dos alertas do B2 (2018) que o agente investiga (D-054). Critério fixado antes de rodar.

Uso: `python -m src.agent.targets` grava `reports/agente_alvos.csv`. Sem LLM.

O detector do desenho final é o B2 (D-053). A seleção busca variedade, não os melhores casos:
1. **Famílias diferentes:** incidentes de 2018 em que a família do alerta do Radar não é
   `entrega` (pista de causa diferente). Alerta = a primeira detecção do B2 no incidente.
2. **Incidente típico de entrega:** o primeiro incidente A de 2018 em SP (maior estado), na
   primeira detecção do B2.
3. **Fim dos dados:** o último incidente do período (SP, agosto), na primeira detecção do B2.
4. **Caso `5dceca12`** (D-026, item 3): o primeiro alerta do B2 em mar–mai/2018 na categoria do
   vendedor com mais pedidos dele entre as que tiveram alerta. O alerta não cita o vendedor.
5. **Falsos alarmes:** os 2 de maior escore, em segmentos distintos e ainda não escolhidos.

O piloto usa um de cada tipo diferente: o típico (2), o 1º falso alarme (5) e o caso (4).
O texto do alerta dado ao agente tem só segmento, semana, método e escore: nem o critério nem o
gabarito.
"""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any

import pandas as pd

from src.classifier.batch import output_path
from src.config import load_config, resolve_path
from src.data.stats import analysis_window
from src.detection.backtest import (
    EVAL,
    HISTORY_START,
    THETA_FILE,
    case_categories,
    ground_truth,
    load_predictions,
    method_scores,
    summary_at,
)
from src.detection.core import FA_AFTER, KEYS, MATCH_BEFORE, WEEK, alerts, week_range
from src.detection.data import monitored_segments

METHOD = "B2"
TYPICAL = ("estado", "SP")
CASE_WINDOW = ("2018-03-05", "2018-05-28")  # o mesmo de `case_section`
N_FALSE = 2
TARGETS_FILE = "agente_alvos.csv"


def label(al: pd.DataFrame, inc_all: pd.DataFrame) -> list[str]:
    """Situação de cada alerta no gabarito: incidente casado, pós-incidente ou falso alarme."""
    out = []
    for r in al.itertuples(index=False):
        same = inc_all[
            (inc_all["segment_type"] == r.segment_type)
            & (inc_all["segment_value"] == r.segment_value)
        ]
        hit = same[(same["start"] - MATCH_BEFORE * WEEK <= r.week) & (r.week <= same["end"])]
        if len(hit):
            out.append(
                "incidente "
                + "; ".join(
                    f"{t} {s:%Y-%m-%d}" for t, s in zip(hit["tipo"], hit["start"], strict=True)
                )
            )
            continue
        cov = same[
            (same["start"] - MATCH_BEFORE * WEEK <= r.week)
            & (r.week <= same["end"] + FA_AFTER * WEEK)
        ]
        out.append("pós-incidente" if len(cov) else "falso alarme")
    return out


def select(
    al: pd.DataFrame,
    det_radar: pd.DataFrame,
    det_b2: pd.DataFrame,
    seller_cats: pd.DataFrame,
) -> pd.DataFrame:
    """Aplica os critérios 1–5 (ver docstring do módulo). `al` já tem a coluna `gabarito`."""
    on = [*KEYS, "tipo", "start"]
    inc = det_radar[[*on, "end", "familia"]].merge(det_b2[[*on, "detected"]], on=on, how="left")
    inc = inc[inc["detected"].notna()].sort_values(["start", *KEYS])
    rows: list[dict[str, Any]] = []

    def add(seg_type: str, seg_value: str, week: pd.Timestamp, criterio: str) -> None:
        if any(
            (r["segment_type"], r["segment_value"], r["week"]) == (seg_type, seg_value, week)
            for r in rows
        ):
            return
        rows.append(
            {
                "criterio": criterio,
                "segment_type": seg_type,
                "segment_value": seg_value,
                "week": week,
            }
        )

    for r in inc[inc["familia"].notna() & (inc["familia"] != "entrega")].itertuples(index=False):
        add(
            r.segment_type,
            r.segment_value,
            r.detected,
            f"1. família do Radar = {r.familia} (incidente {r.tipo} {r.start:%Y-%m-%d})",
        )
    typ = inc[
        (inc["segment_type"] == TYPICAL[0])
        & (inc["segment_value"] == TYPICAL[1])
        & (inc["tipo"] == "A")
    ]
    if len(typ):
        t = typ.iloc[0]
        add(
            t.segment_type,
            t.segment_value,
            t.detected,
            f"2. incidente típico (A {t.start:%Y-%m-%d})",
        )
    last = inc.sort_values("start").iloc[-1]
    add(
        last.segment_type,
        last.segment_value,
        last.detected,
        f"3. último incidente do período ({last.tipo} {last.start:%Y-%m-%d})",
    )
    lo, hi = (pd.Timestamp(x) for x in CASE_WINDOW)
    case = al[(al["segment_type"] == "categoria") & al["week"].between(lo, hi)]
    for c in seller_cats.itertuples(index=False):
        hit = case[case["segment_value"] == c.segment_value].sort_values("week")
        if len(hit):
            add("categoria", c.segment_value, hit.iloc[0]["week"], "4. caso 5dceca12 (categoria)")
            break
    chosen = {(r["segment_type"], r["segment_value"]) for r in rows}
    fa = al[al["gabarito"] == "falso alarme"].sort_values("score", ascending=False)
    n = 0
    for r in fa.itertuples(index=False):
        if n == N_FALSE:
            break
        if (r.segment_type, r.segment_value) in chosen:
            continue
        add(r.segment_type, r.segment_value, r.week, "5. falso alarme de maior escore")
        chosen.add((r.segment_type, r.segment_value))
        n += 1
    out = pd.DataFrame(rows).merge(al, on=[*KEYS, "week"], how="left")
    pilot = {
        next(i for i, c in enumerate(out["criterio"]) if c.startswith(p))
        for p in ("2.", "5.", "4.")
    }
    out["piloto"] = ["sim" if i in pilot else "não" for i in range(len(out))]
    return out[["criterio", *KEYS, "week", "score", "gabarito", "piloto"]]


def main() -> None:
    cfg = load_config()
    con = sqlite3.connect(f"file:{resolve_path(cfg['paths']['db_path'])}?mode=ro", uri=True)
    reports = Path(resolve_path(cfg["paths"]["reports_dir"]))
    start, end = analysis_window(con)
    segs = monitored_segments(con, start, end)
    preds = load_predictions(output_path())
    assert preds is not None
    weeks, pweeks = week_range(HISTORY_START, EVAL[1]), week_range(*EVAL)
    inc_all = ground_truth(con, segs, weeks)
    scores = method_scores(con, segs, weeks, preds)
    seller_cats = case_categories(con)
    con.close()
    thetas = json.loads((reports / THETA_FILE).read_text(encoding="utf-8"))
    _, detected = summary_at(scores, thetas, inc_all, pweeks)
    al = alerts(scores[METHOD], thetas[METHOD], pweeks)
    al = al.assign(gabarito=label(al, inc_all))
    out = select(al, detected["Radar"], detected[METHOD], seller_cats)
    out = out.assign(
        metodo=METHOD, week=out["week"].dt.strftime("%Y-%m-%d"), score=out["score"].round(3)
    )
    path = reports / TARGETS_FILE
    out.to_csv(path, index=False, lineterminator="\n")
    print(out.to_string(index=False))
    print(f"\n{len(out)} alertas em {path}")


if __name__ == "__main__":
    main()
