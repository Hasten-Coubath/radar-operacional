"""Banco recortado no fim da semana do alerta: o agente só vê o que se sabia ali (D-050).

Não é só um filtro de linhas: o estado de cada pedido é o do corte.
- **Pedidos:** só os comprados antes do corte. Aprovação, envio e entrega posteriores ao corte
  viram nulo. Atraso, prazo de entrega e semana de entrega só existem se a entrega aconteceu
  antes do corte.
- **`order_status` final é substituído** por um status derivado das datas no corte
  (`created` / `approved` / `shipped` / `delivered`). Não se sabe quando o status mudou
  (D-025), então cancelamentos e indisponibilidades não aparecem.
- **`situacao_entrega`:** nova coluna com o estado point-in-time de
  `src.data.point_in_time.delay_status_as_of`.
- **Avaliações e classificações:** só as com `review_answer_ts` antes do corte (D-019).
- **Datas planejadas** (`estimated_delivery_date`, `estimated_week`, `shipping_limit_ts`) são
  conhecidas na compra e ficam, mesmo que caiam depois do corte.
- `products` e `sellers` não têm datas e vão inteiros.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pandas as pd

from src.data.database import SCHEMA
from src.data.point_in_time import delay_status_as_of

EVENT_COLUMNS: dict[str, tuple[str, ...]] = {
    "orders": ("purchase_ts", "approved_ts", "delivered_carrier_ts", "delivered_customer_ts"),
    "reviews": ("review_creation_date", "review_answer_ts"),
}
WEEK_COLUMNS: dict[str, tuple[str, ...]] = {
    "orders": ("purchase_week", "delivered_week"),
    "reviews": ("created_week", "answered_week"),
}
PLANNED_COLUMNS = {
    "orders": ("estimated_delivery_date", "estimated_week"),
    "order_items": ("shipping_limit_ts",),
}


def cutoff_for_week(week: str) -> pd.Timestamp:
    """Fim da semana do alerta (exclusivo): segunda-feira + 7 dias, 00:00."""
    return pd.Timestamp(week) + pd.Timedelta(days=7)


def build_snapshot(
    source_db: Path, out: Path, cutoff: pd.Timestamp, classif_db: Path | None = None
) -> Path:
    """Grava em `out` o banco recortado em `cutoff` (instante exclusivo)."""
    c = cutoff.strftime("%Y-%m-%d %H:%M:%S")
    out.unlink(missing_ok=True)
    con = sqlite3.connect(f"file:{out.as_posix()}", uri=True)  # URI: ATTACH em modo ro
    try:
        con.executescript(SCHEMA)
        con.execute("ALTER TABLE orders ADD COLUMN situacao_entrega TEXT")
        con.execute(f"ATTACH DATABASE 'file:{Path(source_db).as_posix()}?mode=ro' AS src")
        con.execute("INSERT INTO meta SELECT * FROM src.meta")
        con.execute("INSERT INTO meta VALUES ('corte', ?)", (c,))
        con.execute("INSERT INTO sellers SELECT * FROM src.sellers")
        con.execute("INSERT INTO products SELECT * FROM src.products")
        before = "datetime({col}) < datetime(:c)"
        known = {col: before.format(col=col) for col in EVENT_COLUMNS["orders"]}
        con.execute(
            f"""
            INSERT INTO orders (
                order_id, customer_id, customer_unique_id, customer_zip_code_prefix,
                customer_city, customer_state, order_status, purchase_ts, approved_ts,
                delivered_carrier_ts, delivered_customer_ts, estimated_delivery_date,
                delay_days, is_late, delivery_days, purchase_week, estimated_week,
                delivered_week, n_items, n_sellers, n_categories, items_value,
                freight_value, payment_value)
            SELECT order_id, customer_id, customer_unique_id, customer_zip_code_prefix,
                customer_city, customer_state,
                CASE WHEN {known["delivered_customer_ts"]} THEN 'delivered'
                     WHEN {known["delivered_carrier_ts"]} THEN 'shipped'
                     WHEN {known["approved_ts"]} THEN 'approved'
                     ELSE 'created' END,
                purchase_ts,
                CASE WHEN {known["approved_ts"]} THEN approved_ts END,
                CASE WHEN {known["delivered_carrier_ts"]} THEN delivered_carrier_ts END,
                CASE WHEN {known["delivered_customer_ts"]} THEN delivered_customer_ts END,
                estimated_delivery_date,
                CASE WHEN {known["delivered_customer_ts"]} THEN delay_days END,
                CASE WHEN {known["delivered_customer_ts"]} THEN is_late END,
                CASE WHEN {known["delivered_customer_ts"]} THEN delivery_days END,
                purchase_week, estimated_week,
                CASE WHEN {known["delivered_customer_ts"]} THEN delivered_week END,
                n_items, n_sellers, n_categories, items_value, freight_value, payment_value
            FROM src.orders WHERE {known["purchase_ts"]}
            """,
            {"c": c},
        )
        for table in ("order_items", "payments", "order_segments"):
            con.execute(
                f"INSERT INTO {table} SELECT * FROM src.{table} "
                "WHERE order_id IN (SELECT order_id FROM orders)"
            )
        con.execute(
            "INSERT INTO reviews SELECT * FROM src.reviews "
            f"WHERE {before.format(col='review_answer_ts')}",
            {"c": c},
        )
        con.execute(
            "INSERT INTO review_orders SELECT * FROM src.review_orders "
            "WHERE review_id IN (SELECT review_id FROM reviews) "
            "AND order_id IN (SELECT order_id FROM orders)"
        )
        _delivery_state(con, cutoff)
        if classif_db is not None:
            con.execute(f"ATTACH DATABASE 'file:{Path(classif_db).as_posix()}?mode=ro' AS cls")
            con.execute(
                "CREATE TABLE classificacoes AS SELECT * FROM cls.classificacoes "
                "WHERE review_id IN (SELECT review_id FROM reviews)"
            )
            con.commit()
            con.execute("DETACH DATABASE cls")
        con.commit()
        con.execute("DETACH DATABASE src")
    finally:
        con.close()
    return out


def _delivery_state(con: sqlite3.Connection, cutoff: pd.Timestamp) -> None:
    """Preenche `situacao_entrega` com a lógica point-in-time de D-025."""
    o = pd.read_sql(
        "SELECT order_id, purchase_ts, delivered_customer_ts, estimated_delivery_date FROM orders",
        con,
    )
    for col in ("purchase_ts", "delivered_customer_ts", "estimated_delivery_date"):
        o[col] = pd.to_datetime(o[col])
    status = delay_status_as_of(o, cutoff)
    con.executemany(
        "UPDATE orders SET situacao_entrega = ? WHERE order_id = ?",
        zip(status.tolist(), o["order_id"].tolist(), strict=True),
    )
