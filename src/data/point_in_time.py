"""Sinal objetivo de atraso sem vazamento temporal (point-in-time), para o backtest.

Regra: no instante `as_of`, um pedido está atrasado se a data estimada já passou e ele não
tinha sido entregue até `as_of`, ou se foi entregue com atraso antes de `as_of`. A data de
entrega só é usada se for anterior a `as_of`; o status final do pedido (`order_status`) nunca é
usado, porque não sabemos quando ele mudou.
"""

from __future__ import annotations

import sqlite3
from collections.abc import Sequence

import numpy as np
import pandas as pd

ONE_DAY = pd.Timedelta(days=1)
WEEK = pd.Timedelta(days=7)

NOT_YET_PURCHASED = "inexistente"
ON_TIME = "entregue_no_prazo"
DELIVERED_LATE = "entregue_atrasado"
OPEN_LATE = "atrasado_em_aberto"
OPEN_ON_TIME = "em_aberto_no_prazo"
LATE_STATUSES = (DELIVERED_LATE, OPEN_LATE)


def load_orders(con: sqlite3.Connection) -> pd.DataFrame:
    """Colunas necessárias do banco, com datas convertidas."""
    df = pd.read_sql(
        "SELECT order_id, customer_state, purchase_ts, delivered_customer_ts, "
        "estimated_delivery_date FROM orders",
        con,
    )
    for col in ("purchase_ts", "delivered_customer_ts", "estimated_delivery_date"):
        df[col] = pd.to_datetime(df[col])
    return df


def delay_status_as_of(orders: pd.DataFrame, as_of: pd.Timestamp) -> pd.Series:
    """Situação de entrega de cada pedido conhecida em `as_of` (instante exclusivo).

    - `inexistente`: comprado em `as_of` ou depois;
    - `entregue_no_prazo` / `entregue_atrasado`: entregue antes de `as_of`, no dia estimado ou
      antes / depois dele;
    - `atrasado_em_aberto`: não entregue até `as_of` e o dia estimado já terminou;
    - `em_aberto_no_prazo`: não entregue até `as_of` e o dia estimado ainda não terminou.
    """
    purchase = orders["purchase_ts"]
    delivered = orders["delivered_customer_ts"]
    estimated = orders["estimated_delivery_date"].dt.normalize()
    known_delivery = delivered.notna() & (delivered < as_of)
    late_delivery = delivered.dt.normalize() > estimated
    due_passed = estimated + ONE_DAY <= as_of
    status = np.select(
        [
            purchase >= as_of,
            known_delivery & ~late_delivery,
            known_delivery & late_delivery,
            due_passed,
        ],
        [NOT_YET_PURCHASED, ON_TIME, DELIVERED_LATE, OPEN_LATE],
        default=OPEN_ON_TIME,
    )
    return pd.Series(status, index=orders.index, name="status")


def weekly_due_late_rate(
    orders: pd.DataFrame, weeks: Sequence[str], group_col: str | None = None
) -> pd.DataFrame:
    """Taxa de atraso da coorte com data estimada em cada semana, conhecida ao fim da semana.

    Para a semana `t` (segunda-feira), `as_of = t + 7 dias`: os pedidos com data estimada de
    `t` a `t + 6` já estão resolvidos (entregues no prazo, ou atrasados, entregues ou não).
    Pedidos nunca entregues contam como atrasados, ao contrário de `orders.is_late`, que fica
    nulo para eles.
    """
    est = orders["estimated_delivery_date"].dt.normalize()
    keys = [group_col] if group_col else []
    rows = []
    for week in weeks:
        start = pd.Timestamp(week)
        as_of = start + WEEK
        cohort = orders[(est >= start) & (est < as_of)]
        status = delay_status_as_of(cohort, as_of)
        frame = pd.DataFrame({"late": status.isin(LATE_STATUSES), "open_late": status == OPEN_LATE})
        for k in keys:
            frame[k] = cohort[k]
        if keys:
            g = frame.groupby(keys).agg(
                due=("late", "size"), late=("late", "sum"), open_late=("open_late", "sum")
            )
            g = g.reset_index()
        else:
            g = pd.DataFrame(
                {
                    "due": [len(frame)],
                    "late": [int(frame["late"].sum())],
                    "open_late": [int(frame["open_late"].sum())],
                }
            )
        g.insert(0, "week", week)
        rows.append(g)
    out = pd.concat(rows, ignore_index=True)
    out["late_rate"] = out["late"] / out["due"].where(out["due"] > 0)
    return out
