"""Carga dos CSVs brutos da Olist com tipos e datas explícitos."""

from __future__ import annotations

import hashlib
from pathlib import Path

import pandas as pd

# nome lógico -> (arquivo, colunas de data)
RAW_FILES: dict[str, tuple[str, list[str]]] = {
    "reviews": (
        "olist_order_reviews_dataset.csv",
        ["review_creation_date", "review_answer_timestamp"],
    ),
    "orders": (
        "olist_orders_dataset.csv",
        [
            "order_purchase_timestamp",
            "order_approved_at",
            "order_delivered_carrier_date",
            "order_delivered_customer_date",
            "order_estimated_delivery_date",
        ],
    ),
    "items": ("olist_order_items_dataset.csv", ["shipping_limit_date"]),
    "products": ("olist_products_dataset.csv", []),
    "customers": ("olist_customers_dataset.csv", []),
    "sellers": ("olist_sellers_dataset.csv", []),
    "payments": ("olist_order_payments_dataset.csv", []),
    "translation": ("product_category_name_translation.csv", []),
}

# CEPs como texto: preservam zeros à esquerda
_STR_COLUMNS = {"customer_zip_code_prefix": str, "seller_zip_code_prefix": str}


def load_raw(raw_dir: Path) -> dict[str, pd.DataFrame]:
    """Lê todos os CSVs de `RAW_FILES`. Falha com mensagem clara se faltar algum."""
    missing = [f for f, _ in RAW_FILES.values() if not (raw_dir / f).exists()]
    if missing:
        raise FileNotFoundError(
            f"CSVs ausentes em {raw_dir}: {missing}. Baixe o dataset da Olist manualmente."
        )
    out: dict[str, pd.DataFrame] = {}
    for name, (filename, date_cols) in RAW_FILES.items():
        df = pd.read_csv(raw_dir / filename, dtype=_STR_COLUMNS, encoding="utf-8")
        for col in date_cols:
            df[col] = pd.to_datetime(df[col], format="%Y-%m-%d %H:%M:%S")
        out[name] = df
    return out


def file_sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()
