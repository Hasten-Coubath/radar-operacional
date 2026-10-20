"""Painel do Radar Operacional (Fase 9): linha do tempo de alertas, replay e briefings.

Uso: `streamlit run src/app/painel.py` (servidor só em 127.0.0.1, `.streamlit/config.toml`).
Modo replay: escolhida uma semana, todas as telas mostram só o que existia até o fim dela.
"""

from __future__ import annotations

import sys
from pathlib import Path

import altair as alt
import pandas as pd
import streamlit as st

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.app.data import PanelData, badge, load, replay, visible_briefings  # noqa: E402
from src.config import load_config, resolve_path  # noqa: E402


@st.cache_data
def get_data(reports_dir: str) -> PanelData:
    return load(Path(reports_dir))


def timeline(data: PanelData, week: pd.Timestamp) -> None:
    st.subheader("Linha do tempo de alertas")
    seen = replay(data.alerts, week)
    segs = sorted(
        {
            f"{t}: {v}"
            for t, v in zip(data.scores["segment_type"], data.scores["segment_value"], strict=True)
        }
    )
    seg = st.selectbox("Segmento", segs, key="seg")
    stype, sval = seg.split(": ", 1)
    s = replay(data.scores, week)
    s = s[(s["segment_type"] == stype) & (s["segment_value"] == sval)]
    a = seen[(seen["segment_type"] == stype) & (seen["segment_value"] == sval)]
    base = (
        alt.Chart(s)
        .mark_line()
        .encode(
            x=alt.X("week:T", title="semana"), y=alt.Y("score:Q", title="escore"), color="metodo:N"
        )
    )
    pts = (
        alt.Chart(a)
        .mark_point(size=80, filled=True)
        .encode(
            x="week:T",
            y="score:Q",
            color="metodo:N",
            tooltip=["week:T", "metodo", "score", "familia"],
        )
    )
    rules = (
        alt.Chart(pd.DataFrame({"theta": list(data.theta.values()), "metodo": list(data.theta)}))
        .mark_rule(strokeDash=[4, 4])
        .encode(y="theta:Q", color="metodo:N")
    )
    st.altair_chart(base + pts + rules, width="stretch")
    st.caption("Pontos = alertas (escore acima do θ calibrado, linha tracejada).")
    st.markdown(f"**Alertas na semana {week:%Y-%m-%d}** (todos os segmentos)")
    now = seen[pd.to_datetime(seen["week"]) == week]
    if now.empty:
        st.write("Nenhum alerta nesta semana.")
    else:
        st.dataframe(
            now[["metodo", "segment_type", "segment_value", "score", "familia"]],
            hide_index=True,
            width="stretch",
        )


def briefings(data: PanelData, week: pd.Timestamp) -> None:
    st.subheader("Briefings do agente")
    vis = visible_briefings(data.briefings, week)
    if not vis:
        st.write("Nenhum briefing até esta semana.")
        return
    labels = [
        f"{b['alerta']['week']} · {b['alerta']['segment_type']}={b['alerta']['segment_value']}"
        for b in vis
    ]
    i = st.selectbox("Alerta", range(len(vis)), format_func=lambda k: labels[k], key="brief")
    b = vis[i]
    st.markdown(b["resumo"])
    st.markdown(f"**Causa provável:** {b['causa_provavel']}")
    claims = b.get("afirmacoes", [])
    ok = sum(c["status"] == "verificada" for c in claims)
    st.markdown(f"**Afirmações verificadas: {ok} de {len(claims)}**")
    for c in claims:
        with st.expander(f"{badge(c['status'])} · {c['texto']} = {c['valor']}"):
            st.code(c["query_sql"], language="sql")
            st.write(f"Valor recalculado: {c['valor_recalculado']}")
    if b.get("numeros_sem_afirmacao"):
        st.warning(f"Números do resumo sem afirmação verificável: {b['numeros_sem_afirmacao']}")


def main() -> None:
    st.set_page_config(page_title="Radar Operacional", layout="wide")
    cfg = load_config()
    data = get_data(str(resolve_path(cfg["paths"]["reports_dir"])))
    st.title("Radar Operacional")
    if data.synthetic:
        st.warning(
            "**Dados sintéticos.** O backtest ainda não gerou alertas: estas telas usam séries "
            "inventadas para desenvolver o painel. Nada aqui é resultado."
        )
    weeks = sorted(pd.to_datetime(data.scores["week"]).unique())
    week = st.select_slider(
        "Replay: semana", options=weeks, value=weeks[-1], format_func=lambda w: f"{w:%Y-%m-%d}",
        key="week",
    )  # fmt: skip
    st.caption("Todas as telas mostram só o que existia até o fim da semana escolhida.")
    tab1, tab2 = st.tabs(["Alertas", "Briefings"])
    with tab1:
        timeline(data, pd.Timestamp(week))
    with tab2:
        briefings(data, pd.Timestamp(week))


main()
