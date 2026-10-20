"""Dados do painel (Fase 9): arquivos reais quando existem, senão dados sintéticos rotulados.

Arquivos reais:
- `reports/alertas_avaliacao.csv` (ou `alertas_calibracao.csv`), gerado pelo backtest;
- `reports/briefings.json`, gerado pelo agente (`src.agent.run`).

Os dados sintéticos servem só para desenvolver o painel enquanto o lote e o backtest não
terminam. Toda tela que os usa mostra um aviso.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from src.detection.data import FAMILIES

SEED = 42
BADGES = {
    "verificada": ("✅", "verificada"),
    "divergente": ("❌", "divergente"),
    "erro": ("⚠️", "não verificável"),
}


@dataclass(frozen=True)
class PanelData:
    scores: pd.DataFrame  # segment_type, segment_value, week, metodo, score
    alerts: pd.DataFrame  # segment_type, segment_value, week, metodo, score, familia
    briefings: list[dict[str, Any]]
    theta: dict[str, float]
    synthetic: bool


def badge(status: str) -> str:
    icon, text = BADGES.get(status, ("❔", status))
    return f"{icon} {text}"


def replay(df: pd.DataFrame, week: pd.Timestamp, col: str = "week") -> pd.DataFrame:
    """Só o que já existia ao fim da semana escolhida (modo replay)."""
    return df[pd.to_datetime(df[col]) <= week]


def visible_briefings(briefings: list[dict[str, Any]], week: pd.Timestamp) -> list[dict[str, Any]]:
    return [b for b in briefings if pd.Timestamp(b["alerta"]["week"]) <= week]


def synthetic(seed: int = SEED) -> PanelData:
    """Séries, alertas e briefings inventados, com incidentes injetados. NÃO são resultados."""
    rng = np.random.default_rng(seed)
    weeks = pd.date_range("2017-02-06", "2018-08-13", freq="7D")
    segs = [("estado", "SP"), ("estado", "RJ"), ("estado", "MG"), ("categoria", "cama_mesa_banho"),
            ("categoria", "beleza_saude")]  # fmt: skip
    fams = list(FAMILIES)
    rows = []
    for st, sv in segs:
        spikes = rng.choice(len(weeks), size=2, replace=False)
        for m in ("Radar", "B1", "B2"):
            s = rng.normal(0, 1, len(weeks))
            for k in spikes:
                lag = 0 if m == "Radar" else 1
                s[min(k + lag, len(weeks) - 1) : min(k + lag + 2, len(weeks))] += 5
            rows += [(st, sv, w, m, float(x)) for w, x in zip(weeks, s, strict=True)]
    scores = pd.DataFrame(
        rows, columns=["segment_type", "segment_value", "week", "metodo", "score"]
    )
    theta = {"Radar": 3.0, "B1": 3.0, "B2": 3.0}
    alerts = scores[scores["score"] > scores["metodo"].map(theta)].copy()
    alerts["familia"] = np.where(alerts["metodo"] == "Radar", rng.choice(fams, len(alerts)), None)
    briefings = []
    for a in alerts[alerts["metodo"] == "Radar"].head(3).itertuples(index=False):
        briefings.append(
            {
                "alerta": {"segment_type": a.segment_type, "segment_value": a.segment_value,
                           "week": f"{a.week:%Y-%m-%d}", "familia": a.familia, "escore": a.score},
                "resumo": "[SINTÉTICO] Exemplo de briefing para desenvolver o painel.",
                "causa_provavel": f"[SINTÉTICO] família {a.familia}",
                "afirmacoes": [
                    {"texto": "[SINTÉTICO] avaliações na semana", "valor": 120.0,
                     "valor_recalculado": 120.0, "status": "verificada",
                     "query_sql": "SELECT COUNT(*) FROM reviews WHERE answered_week = '...'"},
                    {"texto": "[SINTÉTICO] fração de notas ≤ 2", "valor": 0.31,
                     "valor_recalculado": 0.27, "status": "divergente",
                     "query_sql": "SELECT AVG(review_score <= 2) FROM reviews WHERE ..."},
                    {"texto": "[SINTÉTICO] vendedor com mais reclamações", "valor": 14.0,
                     "valor_recalculado": None, "status": "erro",
                     "query_sql": "SELECT seller_id, COUNT(*) FROM ... GROUP BY 1"},
                ],
                "numeros_sem_afirmacao": [],
            }
        )  # fmt: skip
    return PanelData(scores, alerts.reset_index(drop=True), briefings, theta, synthetic=True)


def load(reports_dir: Path) -> PanelData:
    """Arquivos reais do backtest e do agente; sem eles, dados sintéticos."""
    alerts_path = next(
        (p for p in (reports_dir / "alertas_avaliacao.csv", reports_dir / "alertas_calibracao.csv")
         if p.exists()),
        None,
    )  # fmt: skip
    if alerts_path is None:
        return synthetic()
    alerts = pd.read_csv(alerts_path, parse_dates=["week"])
    theta_path = reports_dir / "backtest_calibracao.json"
    theta = json.loads(theta_path.read_text(encoding="utf-8")) if theta_path.exists() else {}
    br_path = reports_dir / "briefings.json"
    briefings = json.loads(br_path.read_text(encoding="utf-8")) if br_path.exists() else []
    # sem as séries completas, a linha do tempo mostra só os escores das semanas com alerta
    scores = alerts[["segment_type", "segment_value", "week", "metodo", "score"]]
    return PanelData(scores, alerts, briefings, {k: v for k, v in theta.items() if v}, False)
