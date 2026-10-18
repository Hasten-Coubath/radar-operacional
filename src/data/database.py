"""Banco SQLite do projeto: schema explícito, índices para o detector e o agente, carga.

Datas ficam como texto ISO (`YYYY-MM-DD HH:MM:SS`; semanas como `YYYY-MM-DD` da segunda-feira),
que o SQLite compara e agrupa corretamente.
"""

from __future__ import annotations

import math
import sqlite3
from pathlib import Path

import numpy as np
import pandas as pd

SCHEMA = """
CREATE TABLE meta (
    key   TEXT PRIMARY KEY,
    value TEXT NOT NULL
);

CREATE TABLE sellers (
    seller_id              TEXT PRIMARY KEY,
    seller_zip_code_prefix TEXT,
    seller_city            TEXT,
    seller_state           TEXT
);

CREATE TABLE products (
    product_id                 TEXT PRIMARY KEY,
    category                   TEXT NOT NULL,   -- 'sem_categoria' quando ausente no CSV
    category_en                TEXT,
    product_name_length        REAL,
    product_description_length REAL,
    product_photos_qty         REAL,
    product_weight_g           REAL,
    product_length_cm          REAL,
    product_height_cm          REAL,
    product_width_cm           REAL
);

CREATE TABLE orders (
    order_id                 TEXT PRIMARY KEY,
    customer_id              TEXT NOT NULL,
    customer_unique_id       TEXT,
    customer_zip_code_prefix TEXT,
    customer_city            TEXT,
    customer_state           TEXT,
    order_status             TEXT NOT NULL,
    purchase_ts              TEXT NOT NULL,
    approved_ts              TEXT,
    delivered_carrier_ts     TEXT,
    delivered_customer_ts    TEXT,
    estimated_delivery_date  TEXT NOT NULL,
    -- sinal objetivo de atraso (src/data/build.py:delay_signal)
    delay_days               INTEGER,           -- entrega - estimada, em dias; nulo se não entregue
    is_late                  INTEGER,           -- 1/0; nulo se não entregue
    delivery_days            REAL,              -- compra -> entrega
    purchase_week            TEXT NOT NULL,
    estimated_week           TEXT NOT NULL,
    delivered_week           TEXT,
    n_items                  INTEGER NOT NULL,
    n_sellers                INTEGER NOT NULL,
    n_categories             INTEGER NOT NULL,
    items_value              REAL,              -- soma de price dos itens
    freight_value            REAL,
    payment_value            REAL               -- soma dos pagamentos
);

CREATE TABLE order_items (
    order_id          TEXT NOT NULL REFERENCES orders(order_id),
    order_item_id     INTEGER NOT NULL,
    product_id        TEXT NOT NULL REFERENCES products(product_id),
    seller_id         TEXT NOT NULL REFERENCES sellers(seller_id),
    shipping_limit_ts TEXT,
    price             REAL NOT NULL,
    freight_value     REAL NOT NULL,
    PRIMARY KEY (order_id, order_item_id)
);

CREATE TABLE payments (
    order_id             TEXT NOT NULL REFERENCES orders(order_id),
    payment_sequential   INTEGER NOT NULL,
    payment_type         TEXT,
    payment_installments INTEGER,
    payment_value        REAL NOT NULL,
    PRIMARY KEY (order_id, payment_sequential)
);

CREATE TABLE reviews (
    review_id            TEXT PRIMARY KEY,
    review_score         INTEGER NOT NULL,
    comment_title        TEXT,
    comment_message      TEXT,               -- normalizado; nulo se vazio/sem letra ou dígito
    has_comment          INTEGER NOT NULL,   -- 1 = elegível para classificação
    comment_chars        INTEGER,
    comment_words        INTEGER,
    review_creation_date TEXT NOT NULL,      -- data de envio da pesquisa ao cliente
    review_answer_ts     TEXT NOT NULL,      -- quando o cliente respondeu
    created_week         TEXT NOT NULL,
    answered_week        TEXT NOT NULL,
    n_orders             INTEGER NOT NULL    -- pedidos cobertos por esta avaliação
);

-- vínculo N:N: uma avaliação pode cobrir vários pedidos e um pedido pode ter várias avaliações
CREATE TABLE review_orders (
    review_id TEXT NOT NULL REFERENCES reviews(review_id),
    order_id  TEXT NOT NULL REFERENCES orders(order_id),
    PRIMARY KEY (review_id, order_id)
);

-- segmentos de cada pedido: estado do cliente, categorias e vendedores dos itens
CREATE TABLE order_segments (
    order_id      TEXT NOT NULL REFERENCES orders(order_id),
    segment_type  TEXT NOT NULL CHECK (segment_type IN ('estado', 'categoria', 'vendedor')),
    segment_value TEXT NOT NULL,
    PRIMARY KEY (order_id, segment_type, segment_value)
);

-- cada avaliação conta uma vez por segmento, mesmo cobrindo vários pedidos do mesmo segmento
CREATE VIEW review_segments AS
SELECT DISTINCT ro.review_id, s.segment_type, s.segment_value
FROM review_orders ro
JOIN order_segments s ON s.order_id = ro.order_id;

CREATE INDEX ix_reviews_answered_week ON reviews(answered_week);
CREATE INDEX ix_reviews_created_week  ON reviews(created_week);
CREATE INDEX ix_reviews_score         ON reviews(review_score);
CREATE INDEX ix_review_orders_order   ON review_orders(order_id);
CREATE INDEX ix_segments_type_value   ON order_segments(segment_type, segment_value);
CREATE INDEX ix_orders_state          ON orders(customer_state);
CREATE INDEX ix_orders_status         ON orders(order_status);
CREATE INDEX ix_orders_purchase_week  ON orders(purchase_week);
CREATE INDEX ix_orders_estimated_week ON orders(estimated_week);
CREATE INDEX ix_orders_estimated_date ON orders(estimated_delivery_date);
CREATE INDEX ix_items_seller          ON order_items(seller_id);
CREATE INDEX ix_items_product         ON order_items(product_id);
CREATE INDEX ix_products_category     ON products(category);
"""

# ordem de inserção respeita as chaves estrangeiras
TABLE_ORDER = [
    "sellers",
    "products",
    "orders",
    "order_items",
    "payments",
    "reviews",
    "review_orders",
    "order_segments",
]


def write_database(
    tables: dict[str, pd.DataFrame], db_path: Path, meta: dict[str, str] | None = None
) -> None:
    """Recria o banco do zero com `SCHEMA` e insere as tabelas, checando chaves estrangeiras."""
    db_path.parent.mkdir(parents=True, exist_ok=True)
    tmp = db_path.with_suffix(".tmp")
    tmp.unlink(missing_ok=True)
    con = sqlite3.connect(tmp)
    try:
        con.executescript(SCHEMA)
        for name in TABLE_ORDER:
            _insert(con, name, tables[name])
        con.executemany("INSERT INTO meta VALUES (?, ?)", sorted((meta or {}).items()))
        violations = con.execute("PRAGMA foreign_key_check").fetchall()
        if violations:
            raise ValueError(f"Violação de chave estrangeira: {violations[:5]}")
        con.commit()
    finally:
        con.close()
    tmp.replace(db_path)


def _insert(con: sqlite3.Connection, table: str, df: pd.DataFrame) -> None:
    columns = [row[1] for row in con.execute(f"PRAGMA table_info({table})")]
    missing = set(columns) - set(df.columns)
    if missing:
        raise ValueError(f"Colunas ausentes para {table}: {sorted(missing)}")
    rows = _to_sql_values(df[columns])
    placeholders = ", ".join("?" * len(columns))
    con.executemany(f"INSERT INTO {table} ({', '.join(columns)}) VALUES ({placeholders})", rows)


def _to_sql_values(df: pd.DataFrame) -> list[tuple[object, ...]]:
    """Datas -> texto ISO; escalares numpy -> tipos Python; NaN/NaT/NA -> None."""
    out = df.copy()
    for col in out.columns:
        if pd.api.types.is_datetime64_any_dtype(out[col]):
            out[col] = out[col].dt.strftime("%Y-%m-%d %H:%M:%S")
    return [tuple(_py(v) for v in row) for row in out.itertuples(index=False, name=None)]


def _py(value: object) -> object:
    if value is None or value is pd.NA or value is pd.NaT:
        return None
    if isinstance(value, float) and math.isnan(value):
        return None
    if isinstance(value, np.generic):
        item = value.item()
        return None if isinstance(item, float) and math.isnan(item) else item
    return value
