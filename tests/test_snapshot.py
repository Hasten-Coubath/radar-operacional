"""Banco recortado do agente (D-050): estado point-in-time e nada depois do corte."""

from __future__ import annotations

import re
import sqlite3
from pathlib import Path

import pandas as pd
import pytest

from src.agent.snapshot import PLANNED_COLUMNS, build_snapshot, cutoff_for_week
from src.agent.sql import QueryRejected, ReadOnlySQL
from src.data.database import SCHEMA

ALERT_WEEK = "2018-04-02"
CUTOFF = cutoff_for_week(ALERT_WEEK)  # 2018-04-09 00:00
_DATE = re.compile(r"^\d{4}-\d{2}-\d{2}")


def order(
    oid: str, purchase: str, delivered: str | None, estimated: str, late: int | None
) -> tuple[object, ...]:
    return (
        oid, f"c_{oid}", None, None, None, "SP", "delivered" if delivered else "canceled",
        purchase, purchase, delivered, delivered, estimated,
        None if delivered is None else 3, late, None if delivered is None else 5.0,
        purchase[:10], estimated[:10], None if delivered is None else delivered[:10],
        1, 1, 1, 10.0, 1.0, 11.0,
    )  # fmt: skip


@pytest.fixture
def source(tmp_path: Path) -> Path:
    path = tmp_path / "radar.db"
    con = sqlite3.connect(path)
    con.executescript(SCHEMA)
    con.execute("INSERT INTO meta VALUES ('versao', 'teste')")
    con.execute("INSERT INTO sellers VALUES ('s1', '0', 'x', 'SP')")
    con.execute(
        "INSERT INTO products VALUES "
        "('p1', 'cama', 'bed', NULL, NULL, NULL, NULL, NULL, NULL, NULL)"
    )
    orders = [
        order("antes", "2018-03-01 10:00:00", "2018-03-10 10:00:00", "2018-03-20 00:00:00", 0),
        # comprado antes do corte, entregue (atrasado) depois do corte
        order("depois", "2018-03-20 10:00:00", "2018-04-20 10:00:00", "2018-04-05 00:00:00", 1),
        order("futuro", "2018-04-15 10:00:00", "2018-04-25 10:00:00", "2018-05-01 00:00:00", 0),
    ]
    con.executemany(f"INSERT INTO orders VALUES ({','.join('?' * 24)})", orders)
    for oid, ship in (("antes", "2018-03-03"), ("depois", "2018-04-12"), ("futuro", "2018-04-20")):
        con.execute(
            "INSERT INTO order_items VALUES (?, 1, 'p1', 's1', ?, 10, 1)", (oid, ship + " 00:00:00")
        )
        con.execute("INSERT INTO payments VALUES (?, 1, 'boleto', 1, 11)", (oid,))
        con.execute("INSERT INTO order_segments VALUES (?, 'estado', 'SP')", (oid,))

    def review(rid: str, score: int, sent: str, answered: str) -> tuple[object, ...]:
        week = pd.Timestamp(answered[:10])
        monday = (week - pd.Timedelta(days=week.weekday())).strftime("%Y-%m-%d")
        sent_monday = pd.Timestamp(sent[:10])
        sent_monday -= pd.Timedelta(days=sent_monday.weekday())
        return (rid, score, None, "texto", 1, 5, 1, sent, answered,
                sent_monday.strftime("%Y-%m-%d"), monday, 1)  # fmt: skip

    reviews = [
        review("r_antes", 5, "2018-03-11 00:00:00", "2018-03-12 10:00:00"),
        # respondida no último minuto da semana do alerta: entra
        review("r_tarde", 1, "2018-04-06 00:00:00", "2018-04-08 23:59:00"),
        review("r_depois", 1, "2018-04-21 00:00:00", "2018-04-22 10:00:00"),
    ]
    con.executemany(f"INSERT INTO reviews VALUES ({','.join('?' * 12)})", reviews)
    con.executemany(
        "INSERT INTO review_orders VALUES (?, ?)",
        [("r_antes", "antes"), ("r_tarde", "depois"), ("r_depois", "depois")],
    )
    con.commit()
    con.close()
    return path


@pytest.fixture
def classif(tmp_path: Path) -> Path:
    path = tmp_path / "c.db"
    con = sqlite3.connect(path)
    con.execute(
        "CREATE TABLE classificacoes (review_id TEXT, review_score INT, answered_week TEXT, "
        "status TEXT, causa TEXT, familia TEXT, area TEXT)"
    )
    con.executemany(
        "INSERT INTO classificacoes VALUES (?, ?, ?, ?, ?, ?, ?)",
        [
            (
                "r_tarde",
                1,
                "2018-04-02",
                "classificado",
                "problema_entrega",
                "entrega",
                "logistica",
            ),
            (
                "r_depois",
                1,
                "2018-04-16",
                "classificado",
                "problema_entrega",
                "entrega",
                "logistica",
            ),
        ],
    )
    con.commit()
    con.close()
    return path


@pytest.fixture
def snap(tmp_path: Path, source: Path, classif: Path) -> Path:
    return build_snapshot(source, tmp_path / "snap.db", CUTOFF, classif)


def test_no_event_date_after_cutoff_in_any_table(snap: Path) -> None:
    con = sqlite3.connect(snap)
    tables = [r[0] for r in con.execute("SELECT name FROM sqlite_master WHERE type = 'table'")]
    checked = 0
    for t in tables:
        df = pd.read_sql(f"SELECT * FROM {t}", con)
        for col in df.columns:
            if col in PLANNED_COLUMNS.get(t, ()) or t == "meta":
                continue  # datas planejadas, conhecidas na compra (D-050)
            values = df[col].dropna().astype(str)
            dates = values[values.str.match(_DATE)]
            if dates.empty:
                continue
            checked += 1
            assert (pd.to_datetime(dates) < CUTOFF).all(), f"{t}.{col} tem data depois do corte"
    assert checked >= 8
    # as datas planejadas podem cair depois do corte, e caem neste exemplo
    est = con.execute("SELECT MAX(estimated_delivery_date) FROM orders").fetchone()[0]
    assert pd.Timestamp(est) < CUTOFF  # "depois" tinha estimativa 2018-04-05
    ship = con.execute("SELECT MAX(shipping_limit_ts) FROM order_items").fetchone()[0]
    assert pd.Timestamp(ship) >= CUTOFF  # prazo de envio futuro, conhecido na compra
    con.close()


def test_order_delivered_after_cutoff_is_not_delivered(snap: Path) -> None:
    con = sqlite3.connect(snap)
    row = con.execute(
        "SELECT order_status, delivered_customer_ts, delivered_carrier_ts, is_late, delay_days, "
        "delivered_week, situacao_entrega FROM orders WHERE order_id = 'depois'"
    ).fetchone()
    # aprovado em 2018-03-20; entrega em 2018-04-20 anulada; estimativa 2018-04-05 já vencida
    assert row == ("approved", None, None, None, None, None, "atrasado_em_aberto")
    before = con.execute(
        "SELECT order_status, is_late, situacao_entrega FROM orders WHERE order_id = 'antes'"
    ).fetchone()
    assert before == ("delivered", 0, "entregue_no_prazo")
    ids = {r[0] for r in con.execute("SELECT order_id FROM orders")}
    assert ids == {"antes", "depois"}  # "futuro" foi comprado depois do corte
    con.close()


def test_agent_query_after_cutoff_returns_nothing(snap: Path) -> None:
    sq = ReadOnlySQL(snap)  # as 4 camadas de somente leitura valem no banco recortado
    after = "WHERE answered_week >= '2018-04-09'"
    assert sq.query(f"SELECT COUNT(*) FROM reviews {after}").scalar() == 0
    assert sq.query(f"SELECT review_id FROM reviews {after}").rows == []
    assert sq.query(f"SELECT review_id FROM classificacoes {after}").rows == []
    assert sq.query("SELECT COUNT(*) FROM orders WHERE purchase_ts >= '2018-04-09'").scalar() == 0
    assert sq.query("SELECT COUNT(*) FROM classificacoes").scalar() == 1  # só r_tarde
    # a resposta de 23:59 do último dia da semana entra; a da semana seguinte, não
    assert {r[0] for r in sq.query("SELECT review_id FROM reviews").rows} == {"r_antes", "r_tarde"}
    with pytest.raises(QueryRejected):
        sq.query("WITH x AS (SELECT 1) DELETE FROM reviews")
