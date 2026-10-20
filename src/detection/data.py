"""Tabelas semanais por segmento para o backtest, lidas do banco e do lote da Fase 6 (D-048).

- `review_table`: avaliações respondidas por semana (todas, com ou sem comentário, D-043), soma
  e soma dos quadrados das notas, notas ≤ 2 e comentários por família de causa (D-047).
- `type_a_table`: coorte com data estimada na semana e atraso point-in-time (D-025, D-030).
- `type_b_table`: avaliações de pedidos entregues no prazo e quantas têm nota ≤ 2.
"""

from __future__ import annotations

import sqlite3

import pandas as pd

from src.data.point_in_time import load_orders, weekly_due_late_rate
from src.detection.core import KEYS, complete

MIN_WEEKLY_COMMENTS = 5  # segmento monitorado: média ≥ 5 comentários por semana (D-026)
FAMILIES: dict[str, tuple[str, ...]] = {
    "entrega": ("problema_entrega",),
    "produto": (
        "qualidade_insatisfatoria",
        "produto_defeituoso_ou_danificado",
        "produto_diferente_do_anunciado",
    ),
    "incompleto": ("pedido_incompleto_ou_errado",),
    "atendimento": ("problema_atendimento_ou_comunicacao",),
    "outro": ("outro",),
}
FAMILY_OF = {c: f for f, cs in FAMILIES.items() for c in cs}
SEGMENT_TYPES = ("estado", "categoria")


def monitored_segments(con: sqlite3.Connection, start: str, end: str) -> pd.DataFrame:
    """Estados e categorias com média ≥ 5 comentários por semana na janela (D-021, D-026)."""
    n_weeks = len(pd.date_range(start, end, freq="7D"))
    d = pd.read_sql(
        "SELECT rs.segment_type, rs.segment_value, SUM(r.has_comment) AS com "
        "FROM review_segments rs JOIN reviews r ON r.review_id = rs.review_id "
        "WHERE r.answered_week BETWEEN ? AND ? AND rs.segment_type IN ('estado', 'categoria') "
        "GROUP BY rs.segment_type, rs.segment_value",
        con,
        params=(start, end),
    )
    keep = d[d["com"] / n_weeks >= MIN_WEEKLY_COMMENTS]
    return keep[KEYS].sort_values(KEYS).reset_index(drop=True)


def _restrict(df: pd.DataFrame, segs: pd.DataFrame) -> pd.DataFrame:
    return df.merge(segs, on=KEYS, how="inner")


def review_table(
    con: sqlite3.Connection,
    segs: pd.DataFrame,
    weeks: pd.DatetimeIndex,
    predictions: pd.DataFrame | None,
) -> pd.DataFrame:
    """Uma linha por segmento × semana de resposta. `predictions`: review_id, status, causa."""
    r = pd.read_sql(
        "SELECT rs.segment_type, rs.segment_value, r.review_id, r.answered_week AS week, "
        "r.review_score AS score FROM review_segments rs JOIN reviews r "
        "ON r.review_id = rs.review_id WHERE rs.segment_type IN ('estado', 'categoria') "
        "AND r.answered_week BETWEEN ? AND ?",
        con,
        params=(str(weeks.min().date()), str(weeks.max().date())),
    )
    r = _restrict(r, segs)
    r["week"] = pd.to_datetime(r["week"])
    r["le2"] = r["score"] <= 2
    r["sq"] = r["score"] ** 2
    agg = r.groupby([*KEYS, "week"]).agg(
        n=("review_id", "size"), s=("score", "sum"), ss=("sq", "sum"), le2=("le2", "sum")
    )
    fam_cols = [f"fam_{f}" for f in FAMILIES]
    if predictions is not None:
        p = predictions[predictions["status"] == "classificado"][["review_id", "causa"]]
        p = p.assign(fam=p["causa"].map(FAMILY_OF)).dropna(subset=["fam"])
        rp = r[[*KEYS, "week", "review_id"]].merge(p[["review_id", "fam"]], on="review_id")
        fam = rp.groupby([*KEYS, "week", "fam"]).size().unstack(fill_value=0)
        fam.columns = [f"fam_{c}" for c in fam.columns]
        agg = agg.join(fam, how="left")
    for c in fam_cols:
        if c not in agg:
            agg[c] = 0
    fill = {c: 0 for c in ["n", "s", "ss", "le2", *fam_cols]}
    return complete(agg.reset_index(), weeks, fill)


def type_a_table(
    con: sqlite3.Connection, segs: pd.DataFrame, weeks: pd.DatetimeIndex
) -> pd.DataFrame:
    """Coorte com data estimada na semana: `due` pedidos, `late` atrasados point-in-time."""
    orders = load_orders(con)
    week_str = [str(w.date()) for w in weeks]
    parts = []
    st = weekly_due_late_rate(orders, week_str, group_col="customer_state")
    parts.append(
        st.rename(columns={"customer_state": "segment_value"}).assign(segment_type="estado")
    )
    cats = pd.read_sql(
        "SELECT order_id, segment_value AS categoria FROM order_segments "
        "WHERE segment_type = 'categoria'",
        con,
    )
    oc = orders.merge(cats, on="order_id")
    ct = weekly_due_late_rate(oc, week_str, group_col="categoria")
    parts.append(ct.rename(columns={"categoria": "segment_value"}).assign(segment_type="categoria"))
    t = pd.concat(parts, ignore_index=True)[[*KEYS, "week", "due", "late"]]
    t["week"] = pd.to_datetime(t["week"])
    return complete(_restrict(t, segs), weeks, {"due": 0, "late": 0})


def type_b_table(
    con: sqlite3.Connection, segs: pd.DataFrame, weeks: pd.DatetimeIndex
) -> pd.DataFrame:
    """Avaliações respondidas na semana ligadas a pedido entregue no prazo no segmento."""
    d = pd.read_sql(
        "SELECT DISTINCT s.segment_type, s.segment_value, r.review_id, r.answered_week AS week, "
        "r.review_score AS score FROM reviews r "
        "JOIN review_orders ro ON ro.review_id = r.review_id "
        "JOIN orders o ON o.order_id = ro.order_id AND o.is_late = 0 "
        "JOIN order_segments s ON s.order_id = o.order_id "
        "WHERE s.segment_type IN ('estado', 'categoria') AND r.answered_week BETWEEN ? AND ?",
        con,
        params=(str(weeks.min().date()), str(weeks.max().date())),
    )
    d = _restrict(d, segs)
    d["week"] = pd.to_datetime(d["week"])
    d["le2"] = d["score"] <= 2
    t = d.groupby([*KEYS, "week"]).agg(n=("review_id", "size"), le2=("le2", "sum")).reset_index()
    return complete(t, weeks, {"n": 0, "le2": 0})
