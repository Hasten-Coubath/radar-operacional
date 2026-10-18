"""Limpeza, junções e sinal objetivo de atraso: dos CSVs brutos às tabelas do banco.

Nenhuma linha é descartada em silêncio: inconsistências são contadas em `quality_checks` e as
linhas ficam no banco, com o efeito documentado em `docs/decisoes.md`.
"""

from __future__ import annotations

import re
from typing import Any

import pandas as pd

NO_CATEGORY = "sem_categoria"
SEGMENT_TYPES = ("estado", "categoria", "vendedor")
_HAS_ALNUM = re.compile(r"\w", flags=re.UNICODE)


def week_start(ts: pd.Series) -> pd.Series:
    """Segunda-feira da semana de cada data, como texto `YYYY-MM-DD` (nulo se a data for nula)."""
    day = ts.dt.normalize()
    monday = day - pd.to_timedelta(day.dt.weekday, unit="D")
    return monday.dt.strftime("%Y-%m-%d")


def normalize_comment(text: Any) -> str | None:
    """Quebras de linha unificadas e espaços aparados; texto sem letra nem dígito vira None."""
    if not isinstance(text, str):
        return None
    clean = text.replace("\r\n", "\n").replace("\r", "\n").strip()
    return clean if _HAS_ALNUM.search(clean) else None


def delay_signal(orders: pd.DataFrame) -> pd.DataFrame:
    """Sinal objetivo de atraso por pedido.

    `delay_days` = data de entrega ao cliente − data estimada, em dias de calendário (entregar
    no próprio dia estimado é pontual). `is_late` é 1 se `delay_days > 0`, 0 se não, e nulo
    quando o pedido não tem data de entrega. `delivery_days` é o tempo da compra à entrega.
    """
    delivered = orders["order_delivered_customer_date"]
    estimated = orders["order_estimated_delivery_date"].dt.normalize()
    delay = (delivered.dt.normalize() - estimated).dt.days
    return pd.DataFrame(
        {
            "delay_days": delay.astype("Int64"),
            "is_late": (delay > 0).astype("Int64").where(delay.notna()),
            "delivery_days": (
                (delivered - orders["order_purchase_timestamp"]).dt.total_seconds() / 86400
            ).round(2),
        },
        index=orders.index,
    )


def build_tables(raw: dict[str, pd.DataFrame]) -> dict[str, pd.DataFrame]:
    """Monta as tabelas do banco a partir dos DataFrames de `load_raw`."""
    products = _products(raw["products"], raw["translation"])
    items = _items(raw["items"])
    orders = _orders(raw["orders"], raw["customers"], items, products, raw["payments"])
    reviews, review_orders = _reviews(raw["reviews"])
    return {
        "orders": orders,
        "order_items": items,
        "products": products,
        "sellers": raw["sellers"].copy(),
        "payments": raw["payments"].copy(),
        "reviews": reviews,
        "review_orders": review_orders,
        "order_segments": _order_segments(orders, items, products),
    }


def _products(products: pd.DataFrame, translation: pd.DataFrame) -> pd.DataFrame:
    p = products.rename(
        columns={
            "product_category_name": "category",
            # nomes originais têm erro de grafia ("lenght")
            "product_name_lenght": "product_name_length",
            "product_description_lenght": "product_description_length",
        }
    )
    p["category"] = p["category"].fillna(NO_CATEGORY)
    en = translation.set_index("product_category_name")["product_category_name_english"]
    p["category_en"] = p["category"].map(en)
    return p


def _items(items: pd.DataFrame) -> pd.DataFrame:
    return items.rename(columns={"shipping_limit_date": "shipping_limit_ts"})


def _orders(
    orders: pd.DataFrame,
    customers: pd.DataFrame,
    items: pd.DataFrame,
    products: pd.DataFrame,
    payments: pd.DataFrame,
) -> pd.DataFrame:
    o = orders.merge(customers, on="customer_id", how="left", validate="one_to_one")
    o = pd.concat([o, delay_signal(o)], axis=1)
    o["purchase_week"] = week_start(o["order_purchase_timestamp"])
    o["estimated_week"] = week_start(o["order_estimated_delivery_date"])
    o["delivered_week"] = week_start(o["order_delivered_customer_date"])

    with_cat = items.merge(products[["product_id", "category"]], on="product_id", how="left")
    agg = with_cat.groupby("order_id").agg(
        n_items=("order_item_id", "size"),
        n_sellers=("seller_id", "nunique"),
        n_categories=("category", "nunique"),
        items_value=("price", "sum"),
        freight_value=("freight_value", "sum"),
    )
    paid = payments.groupby("order_id")["payment_value"].sum().rename("payment_value")
    o = o.merge(agg, on="order_id", how="left").merge(paid, on="order_id", how="left")
    for col in ("n_items", "n_sellers", "n_categories"):
        o[col] = o[col].fillna(0).astype("int64")
    return o.rename(
        columns={
            "order_purchase_timestamp": "purchase_ts",
            "order_approved_at": "approved_ts",
            "order_delivered_carrier_date": "delivered_carrier_ts",
            "order_delivered_customer_date": "delivered_customer_ts",
            "order_estimated_delivery_date": "estimated_delivery_date",
        }
    )


def _reviews(raw: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Separa avaliação (única por `review_id`) do vínculo avaliação ↔ pedido (N:N).

    No CSV, 802 `review_id` aparecem ligados a 2–3 pedidos do mesmo cliente com conteúdo
    idêntico: é uma avaliação só, cobrindo vários pedidos.
    """
    links = raw[["review_id", "order_id"]].drop_duplicates().reset_index(drop=True)
    cols = [c for c in raw.columns if c != "order_id"]
    content = raw[cols].drop_duplicates()
    if content["review_id"].duplicated().any():
        raise ValueError("review_id com conteúdo divergente entre linhas do CSV")
    r = content.rename(
        columns={
            "review_comment_title": "comment_title",
            "review_comment_message": "comment_message",
            "review_answer_timestamp": "review_answer_ts",
        }
    ).reset_index(drop=True)
    r["comment_title"] = r["comment_title"].map(normalize_comment)
    r["comment_message"] = r["comment_message"].map(normalize_comment)
    r["has_comment"] = r["comment_message"].notna().astype("int64")
    r["comment_chars"] = r["comment_message"].str.len().astype("Int64")
    r["comment_words"] = r["comment_message"].str.split().str.len().astype("Int64")
    r["created_week"] = week_start(r["review_creation_date"])
    r["answered_week"] = week_start(r["review_answer_ts"])
    r["n_orders"] = r["review_id"].map(links["review_id"].value_counts()).astype("int64")
    return r, links


def _order_segments(
    orders: pd.DataFrame, items: pd.DataFrame, products: pd.DataFrame
) -> pd.DataFrame:
    """Segmentos de cada pedido: estado do cliente (1), categorias e vendedores distintos (0..n).

    Pedido com mais de um vendedor/categoria pertence a todos eles; pedido sem itens só tem
    estado.
    """
    estado = orders[["order_id", "customer_state"]].rename(
        columns={"customer_state": "segment_value"}
    )
    estado.insert(1, "segment_type", "estado")
    with_cat = items.merge(products[["product_id", "category"]], on="product_id", how="left")
    categoria = with_cat[["order_id", "category"]].rename(columns={"category": "segment_value"})
    categoria.insert(1, "segment_type", "categoria")
    vendedor = items[["order_id", "seller_id"]].rename(columns={"seller_id": "segment_value"})
    vendedor.insert(1, "segment_type", "vendedor")
    seg = pd.concat([estado, categoria, vendedor], ignore_index=True).drop_duplicates()
    return seg.sort_values(["order_id", "segment_type", "segment_value"]).reset_index(drop=True)


def quality_checks(raw: dict[str, pd.DataFrame], tables: dict[str, pd.DataFrame]) -> dict[str, int]:
    """Contagens de inconsistências encontradas (mantidas no banco, não descartadas)."""
    o, r = raw["orders"], raw["reviews"]
    delivered = o["order_delivered_customer_date"]
    rv = tables["reviews"]
    raw_msg = r.drop_duplicates("review_id")["review_comment_message"]
    return {
        "review_rows_csv": len(r),
        "reviews_unique": len(rv),
        "reviews_linked_to_multiple_orders": int((rv["n_orders"] > 1).sum()),
        "orders_with_multiple_reviews": int((r["order_id"].value_counts() > 1).sum()),
        "comments_raw_non_null": int(raw_msg.notna().sum()),
        "comments_without_alnum_dropped": int(raw_msg.notna().sum() - rv["has_comment"].sum()),
        "title_without_message": int(
            (rv["comment_title"].notna() & rv["comment_message"].isna()).sum()
        ),
        "orders_without_items": int((tables["orders"]["n_items"] == 0).sum()),
        "orders_delivered_status_without_date": int(
            ((o["order_status"] == "delivered") & delivered.isna()).sum()
        ),
        "orders_not_delivered_status_with_date": int(
            ((o["order_status"] != "delivered") & delivered.notna()).sum()
        ),
        "orders_carrier_after_customer_delivery": int(
            (o["order_delivered_carrier_date"] > delivered).sum()
        ),
        "products_without_category": int((tables["products"]["category"] == NO_CATEGORY).sum()),
        "categories_without_translation": int(
            tables["products"]
            .loc[tables["products"]["category"] != NO_CATEGORY, "category_en"]
            .isna()
            .groupby(tables["products"]["category"])
            .any()
            .sum()
        ),
    }
