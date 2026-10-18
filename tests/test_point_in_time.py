"""Testes do sinal de atraso point-in-time: nada posterior a `as_of` pode influenciar."""

from __future__ import annotations

import pandas as pd
import pytest

from src.data.point_in_time import (
    DELIVERED_LATE,
    NOT_YET_PURCHASED,
    ON_TIME,
    OPEN_LATE,
    OPEN_ON_TIME,
    delay_status_as_of,
    weekly_due_late_rate,
)

T = pd.Timestamp
AS_OF = T("2018-03-12")  # segunda-feira 00:00: fim da semana de 2018-03-05


def orders(rows: list[tuple[str, str, str | None, str]]) -> pd.DataFrame:
    """(order_id, compra, entrega ou None, data estimada)."""
    df = pd.DataFrame(
        rows,
        columns=["order_id", "purchase_ts", "delivered_customer_ts", "estimated_delivery_date"],
    )
    for col in ("purchase_ts", "delivered_customer_ts", "estimated_delivery_date"):
        df[col] = pd.to_datetime(df[col])
    df["customer_state"] = ["SP", "RJ"] * (len(df) // 2) + ["SP"] * (len(df) % 2)
    return df


@pytest.mark.parametrize(
    ("delivered", "estimated", "expected"),
    [
        ("2018-03-08 10:00", "2018-03-08", ON_TIME),  # entregue no próprio dia estimado
        ("2018-03-05 10:00", "2018-03-20", ON_TIME),  # adiantado, antes de vencer
        ("2018-03-09 10:00", "2018-03-08", DELIVERED_LATE),  # atrasado, já entregue
        (None, "2018-03-08", OPEN_LATE),  # venceu e não foi entregue
        ("2018-03-20 10:00", "2018-03-08", OPEN_LATE),  # entregue só depois de as_of
        ("2018-03-12 00:00", "2018-03-08", OPEN_LATE),  # entrega exatamente em as_of: não conta
        (None, "2018-03-11", OPEN_LATE),  # domingo estimado: o dia já terminou em as_of
        (None, "2018-03-12", OPEN_ON_TIME),  # vence hoje: ainda no prazo
        ("2018-03-25 10:00", "2018-03-20", OPEN_ON_TIME),  # atrasará, mas ainda não venceu
    ],
)
def test_status_as_of(delivered: str | None, estimated: str, expected: str) -> None:
    df = orders([("o", "2018-03-01", delivered, estimated)])
    assert delay_status_as_of(df, AS_OF).iloc[0] == expected


def test_order_purchased_after_as_of_does_not_exist_yet() -> None:
    df = orders([("o", "2018-03-12 08:00", None, "2018-03-20")])
    assert delay_status_as_of(df, AS_OF).iloc[0] == NOT_YET_PURCHASED


def test_future_deliveries_never_change_the_status() -> None:
    """Propriedade central: trocar entregas posteriores a as_of não muda nada em as_of."""
    base = orders(
        [
            ("a", "2018-03-01", "2018-03-14", "2018-03-08"),
            ("b", "2018-03-01", "2018-04-30", "2018-03-08"),
            ("c", "2018-03-01", None, "2018-03-08"),
            ("d", "2018-03-01", "2018-03-13", "2018-03-15"),
        ]
    )
    variant = base.copy()
    variant["delivered_customer_ts"] = pd.to_datetime(
        ["2018-06-01 00:00", None, "2018-03-12 00:00", None]
    )
    pd.testing.assert_series_equal(
        delay_status_as_of(base, AS_OF), delay_status_as_of(variant, AS_OF)
    )


def test_weekly_rate_counts_cohort_due_in_week_and_undelivered_as_late() -> None:
    df = orders(
        [
            ("a", "2018-03-01", "2018-03-06", "2018-03-07"),  # coorte 03-05, no prazo
            ("b", "2018-03-01", "2018-03-10", "2018-03-07"),  # coorte 03-05, atrasado
            ("c", "2018-03-01", None, "2018-03-09"),  # coorte 03-05, nunca entregue
            ("d", "2018-03-01", "2018-03-30", "2018-03-11"),  # coorte 03-05, aberto em as_of
            ("e", "2018-03-01", "2018-03-14", "2018-03-14"),  # coorte 03-12
        ]
    )
    out = weekly_due_late_rate(df, ["2018-03-05", "2018-03-12", "2018-03-19"]).set_index("week")
    assert out.loc["2018-03-05", ["due", "late", "open_late"]].tolist() == [4, 3, 2]
    assert out.loc["2018-03-05", "late_rate"] == 0.75
    assert out.loc["2018-03-12", "late_rate"] == 0.0
    assert out.loc["2018-03-19", "due"] == 0 and pd.isna(out.loc["2018-03-19", "late_rate"])


def test_weekly_rate_by_group() -> None:
    df = orders(
        [
            ("a", "2018-03-01", None, "2018-03-07"),  # SP, atrasado
            ("b", "2018-03-01", "2018-03-06", "2018-03-07"),  # RJ, no prazo
            ("c", "2018-03-01", "2018-03-06", "2018-03-07"),  # SP, no prazo
        ]
    )
    out = weekly_due_late_rate(df, ["2018-03-05"], group_col="customer_state")
    rates = dict(zip(out["customer_state"], out["late_rate"], strict=True))
    assert rates == {"RJ": 0.0, "SP": 0.5}
