"""Testes do núcleo do detector com séries sintéticas (D-026, D-048)."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from src.detection.core import (
    anomalous_weeks,
    calibrate,
    complete,
    evaluate,
    incidents,
    mean_drop_signal,
    proportion_signal,
    runs_to_incidents,
    week_range,
    wilson_lower,
)

WEEKS = week_range("2017-01-02", "2017-12-25")


def series(rates: list[float], n: int = 100, seg: str = "SP") -> pd.DataFrame:
    w = WEEKS[: len(rates)]
    return pd.DataFrame(
        {
            "segment_type": "estado",
            "segment_value": seg,
            "week": w,
            "k": [round(r * n) for r in rates],
            "n": n,
        }
    )


def test_wilson_lower_matches_formula() -> None:
    # p = 0,5, n = 100: limite inferior conhecido ≈ 0,4038
    assert wilson_lower(np.array([0.5]), np.array([100]))[0] == pytest.approx(0.4038, abs=1e-4)
    assert np.isnan(wilson_lower(np.array([0.5]), np.array([0]))[0])


def test_junction_rule() -> None:
    w = list(WEEKS[:12])
    f = [True, True, False, True, True, False, False, True, False, False, True, False]
    # blocos: [0..4] (gaps de 1 semana unidos) → incidente; [7] isolado → não; [10] → não
    assert runs_to_incidents(w, f) == [(w[0], w[4])]
    # semanas isoladas unidas por gaps de 1 não viram incidente sem 2 consecutivas
    assert runs_to_incidents(w, [True, False, True, False, True] + [False] * 7) == []
    # bloco unido com isoladas antes: início é a 1ª anômala do bloco
    assert runs_to_incidents(w, [True, False, True, True] + [False] * 8) == [(w[0], w[3])]


def test_anomaly_is_point_in_time_and_needs_history() -> None:
    base = [0.05] * 20 + [0.30, 0.30] + [0.05] * 5
    t = anomalous_weeks(series(base), "k", "n", n_min=30)
    assert t["anom"].tolist()[20:22] == [True, True]
    assert not t["anom"].iloc[:8].any()  # sem 8 semanas de referência, nada é anômalo
    # mudar o futuro não muda a decisão em t (referência só olha para trás)
    future = base[:22] + [0.9] * 5
    t2 = anomalous_weeks(series(future), "k", "n", n_min=30)
    assert t2["anom"].iloc[:22].tolist() == t["anom"].iloc[:22].tolist()
    inc = incidents(t, "A")
    assert len(inc) == 1 and inc.iloc[0]["start"] == WEEKS[20]


def test_low_volume_weeks_are_never_anomalous() -> None:
    s = series([0.05] * 20 + [0.5, 0.5], n=20)
    assert not anomalous_weeks(s, "k", "n", n_min=30)["anom"].any()


def test_complete_fills_missing_weeks() -> None:
    s = series([0.1, 0.1, 0.1]).drop(index=1)
    c = complete(s, WEEKS[:3], {"k": 0, "n": 0})
    assert len(c) == 3 and c.loc[1, "n"] == 0


def test_signals_rise_on_spike_and_mean_drop() -> None:
    s = series([0.05] * 20 + [0.25])
    score = proportion_signal(s, "k", "n", n_min=20)
    assert score.iloc[:8].isna().all() and score.iloc[20] > 5
    m = pd.DataFrame(
        {
            "segment_type": "estado",
            "segment_value": "SP",
            "week": WEEKS[:21],
            "n": 50,
            "s": [50 * 4.2] * 20 + [50 * 3.0],
            "ss": [50 * (4.2**2 + 1.0)] * 20 + [50 * (9.0 + 1.0)],
        }
    )
    drop = mean_drop_signal(m, "n", "s", "ss", n_min=20)
    assert drop.iloc[20] > 5 and abs(drop.iloc[15]) < 1e-9


def test_matching_false_alarms_and_calibration() -> None:
    w = WEEKS
    inc = pd.DataFrame(
        {
            "segment_type": ["estado"],
            "segment_value": ["SP"],
            "tipo": ["A"],
            "start": [w[20]],
            "end": [w[22]],
        }
    )
    scores = pd.DataFrame(
        {
            "segment_type": "estado",
            "segment_value": "SP",
            "week": [w[17], w[21], w[24], w[40]],
            "score": [3.0, 6.0, 3.0, 2.0],
        }
    )
    # θ = 2,5: alertas em 17 (casa: início − 3), 21, 24 (fim + 2: não é falso)
    det, n_fa, fa_week = evaluate(scores[scores["score"] > 2.5], inc, w)
    assert det.iloc[0]["detected"] == w[17] and n_fa == 0
    # θ = 1: o alerta da semana 40 é falso
    _, n_fa1, _ = evaluate(scores[scores["score"] > 1], inc, w)
    assert n_fa1 == 1
    theta, curve = calibrate(scores, inc, w, grid=[1.0, 2.5, 5.0], budget=0.0)
    assert theta == 2.5
    assert curve.set_index("theta").loc[5.0, "recall_A"] == 1.0  # só o alerta da semana 21


def test_equal_fa_table_uses_smallest_theta_within_level() -> None:
    from src.detection.backtest import equal_fa_table

    curve = pd.DataFrame(
        {
            "theta": [1.0, 2.0, 3.0, 1.0, 2.0, 3.0],
            "fa_por_semana": [2.0, 0.6, 0.2, 0.9, 0.4, 0.1],
            "recall_A": [1.0, 0.75, 0.5, 1.0, 0.5, 0.25],
            "n_A": 4,
            "recall_B": float("nan"),
            "n_B": 0,
            "método": ["Radar"] * 3 + ["B1"] * 3,
        }
    )
    t = equal_fa_table(curve, levels=(0.5, 1.0)).set_index(["nível (FA/sem ≤)", "método"])
    assert t.loc[(0.5, "Radar"), "θ"] == 3.0 and t.loc[(0.5, "Radar"), "recall A"] == "2/4"
    assert t.loc[(0.5, "B1"), "θ"] == 2.0 and t.loc[(0.5, "B1"), "recall A"] == "2/4"
    assert t.loc[(1.0, "Radar"), "θ"] == 2.0 and t.loc[(1.0, "B1"), "θ"] == 1.0
    assert t.loc[(1.0, "B1"), "recall B"] == "0/0"
    none = equal_fa_table(curve, levels=(0.05,))
    assert (none["θ"] == "—").all()


def test_incident_table_lead_sign() -> None:
    from src.detection.backtest import incident_table

    w = WEEKS
    base = pd.DataFrame(
        {
            "segment_type": "estado",
            "segment_value": ["SP", "RJ"],
            "tipo": "A",
            "start": [w[10], w[20]],
            "end": [w[12], w[22]],
        }
    )
    det = {
        "Radar": base.assign(detected=[w[8], pd.NaT], familia=["entrega", None]),
        "B1": base.assign(detected=[w[11], w[21]]),
        "B2": base.assign(detected=[w[8], pd.NaT]),
    }
    t = incident_table(det).set_index("segment_value")
    assert t.loc["SP", "antecedência vs B1 (sem)"] == "+3"  # Radar 3 semanas antes
    assert t.loc["SP", "antecedência vs B2 (sem)"] == "0"
    assert t.loc["RJ", "Radar"] == "—" and t.loc["RJ", "antecedência vs B1 (sem)"] == ""
    assert t.loc["SP", "família (Radar)"] == "entrega"


def test_backtest_refuses_incomplete_batch() -> None:
    import sqlite3

    from src.detection.backtest import lote_missing

    con = sqlite3.connect(":memory:")
    con.execute(
        "CREATE TABLE reviews (review_id TEXT, has_comment INT, review_score INT, "
        "answered_week TEXT)"
    )
    con.executemany(
        "INSERT INTO reviews VALUES (?, ?, ?, ?)",
        [
            ("a", 1, 1, "2017-03-06"),
            ("b", 1, 5, "2017-03-06"),  # nota 5: não precisa estar no lote
            ("c", 1, 2, "2018-02-05"),
            ("d", 0, 1, "2017-03-06"),  # sem comentário
        ],
    )
    preds = pd.DataFrame({"review_id": ["a"], "status": ["classificado"]})
    assert lote_missing(con, None, "2017-12-31") == 1
    assert lote_missing(con, preds, "2017-12-31") == 0
    assert lote_missing(con, preds, "2018-08-13") == 1  # falta "c" para a avaliação


def test_diagnosis_base_rate_counts_all_radar_alerts() -> None:
    from src.detection.backtest import diagnosis_table

    det = {
        "Radar": pd.DataFrame(
            {
                "tipo": ["A", "A", "B"],
                "detected": [WEEKS[3], WEEKS[5], pd.NaT],
                "familia": ["entrega", "produto", None],
            }
        )
    }
    al = pd.DataFrame({"familia": ["entrega", "entrega", "entrega", "produto"]})
    t = diagnosis_table(det, al).set_index("tipo")
    assert t.loc["A", "família compatível"] == "1/2 (50%)"
    assert t.loc["A", "taxa de base (todos os alertas do Radar)"] == "3/4 (75%)"
    assert t.loc["B", "taxa de base (todos os alertas do Radar)"] == "1/4 (25%)"
