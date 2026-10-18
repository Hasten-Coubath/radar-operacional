"""Testes da camada de dados com DataFrames sintéticos (sem os CSVs reais)."""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pandas as pd
import pytest

from src.data.build import (
    NO_CATEGORY,
    build_tables,
    delay_signal,
    normalize_comment,
    quality_checks,
    week_start,
)
from src.data.database import write_database
from src.data.load import load_raw
from src.data.sample_taxonomy import draw_sample
from src.data.stats import late_window_end, md_table

T = pd.Timestamp


def make_raw() -> dict[str, pd.DataFrame]:
    """3 pedidos: o1 com 2 vendedores e entregue atrasado, o2 no prazo, o3 sem itens/entrega."""
    orders = pd.DataFrame(
        {
            "order_id": ["o1", "o2", "o3"],
            "customer_id": ["c1", "c2", "c3"],
            "order_status": ["delivered", "delivered", "canceled"],
            "order_purchase_timestamp": [
                T("2018-03-01 10:00"),
                T("2018-03-02 09:00"),
                T("2018-03-03"),
            ],
            "order_approved_at": [T("2018-03-01 11:00"), T("2018-03-02 10:00"), pd.NaT],
            "order_delivered_carrier_date": [T("2018-03-02"), T("2018-03-03"), pd.NaT],
            "order_delivered_customer_date": [T("2018-03-12 18:30"), T("2018-03-10 08:00"), pd.NaT],
            "order_estimated_delivery_date": [T("2018-03-10"), T("2018-03-10"), T("2018-03-20")],
        }
    )
    customers = pd.DataFrame(
        {
            "customer_id": ["c1", "c2", "c3"],
            "customer_unique_id": ["u1", "u1", "u3"],
            "customer_zip_code_prefix": ["01001", "01001", "20000"],
            "customer_city": ["sao paulo", "sao paulo", "rio de janeiro"],
            "customer_state": ["SP", "SP", "RJ"],
        }
    )
    items = pd.DataFrame(
        {
            "order_id": ["o1", "o1", "o2"],
            "order_item_id": [1, 2, 1],
            "product_id": ["p1", "p2", "p1"],
            "seller_id": ["s1", "s2", "s1"],
            "shipping_limit_date": [T("2018-03-05")] * 3,
            "price": [10.0, 20.0, 10.0],
            "freight_value": [1.0, 2.0, 1.0],
        }
    )
    products = pd.DataFrame(
        {
            "product_id": ["p1", "p2"],
            "product_category_name": ["beleza_saude", None],
            "product_name_lenght": [10.0, None],
            "product_description_lenght": [100.0, None],
            "product_photos_qty": [1.0, None],
            "product_weight_g": [100.0, 200.0],
            "product_length_cm": [10.0, 10.0],
            "product_height_cm": [10.0, 10.0],
            "product_width_cm": [10.0, 10.0],
        }
    )
    sellers = pd.DataFrame(
        {
            "seller_id": ["s1", "s2"],
            "seller_zip_code_prefix": ["01001", "30000"],
            "seller_city": ["sao paulo", "belo horizonte"],
            "seller_state": ["SP", "MG"],
        }
    )
    payments = pd.DataFrame(
        {
            "order_id": ["o1", "o1", "o2"],
            "payment_sequential": [1, 2, 1],
            "payment_type": ["credit_card", "voucher", "boleto"],
            "payment_installments": [1, 1, 1],
            "payment_value": [25.0, 8.0, 11.0],
        }
    )
    translation = pd.DataFrame(
        {"product_category_name": ["beleza_saude"], "product_category_name_english": ["health"]}
    )
    # r1 cobre o1 e o2 (mesmo cliente, conteúdo idêntico); r2 é sobre o3 e só tem "."
    reviews = pd.DataFrame(
        {
            "review_id": ["r1", "r1", "r2"],
            "order_id": ["o1", "o2", "o3"],
            "review_score": [2, 2, 1],
            "review_comment_title": [None, None, "Ruim"],
            "review_comment_message": ["Atrasou\r\nmuito ", "Atrasou\r\nmuito ", " . "],
            "review_creation_date": [T("2018-03-13"), T("2018-03-13"), T("2018-03-21")],
            "review_answer_timestamp": [T("2018-03-14 12:00")] * 2 + [T("2018-03-25 09:00")],
        }
    )
    return {
        "reviews": reviews,
        "orders": orders,
        "items": items,
        "products": products,
        "customers": customers,
        "sellers": sellers,
        "payments": payments,
        "translation": translation,
    }


# --- funções puras ---


def test_delay_signal_uses_calendar_days() -> None:
    orders = pd.DataFrame(
        {
            "order_purchase_timestamp": [T("2018-01-01")] * 4,
            "order_delivered_customer_date": [
                T("2018-01-10 23:59"),  # no dia estimado: pontual
                T("2018-01-11 00:01"),  # 1 dia depois: atrasado
                T("2018-01-05 12:00"),  # adiantado
                pd.NaT,  # não entregue
            ],
            "order_estimated_delivery_date": [T("2018-01-10")] * 4,
        }
    )
    sig = delay_signal(orders)
    assert sig["delay_days"].tolist()[:3] == [0, 1, -5]
    assert sig["is_late"].tolist()[:3] == [0, 1, 0]
    assert pd.isna(sig["delay_days"].iloc[3]) and pd.isna(sig["is_late"].iloc[3])
    assert sig["delivery_days"].iloc[2] == 4.5


def test_week_start_is_monday() -> None:
    s = pd.Series([T("2018-03-11 23:00"), T("2018-03-12"), T("2018-03-18"), pd.NaT])
    out = week_start(s)
    assert out.tolist()[:3] == ["2018-03-05", "2018-03-12", "2018-03-12"]
    assert pd.isna(out.iloc[3])


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("Atrasou\r\nmuito ", "Atrasou\nmuito"),
        ("  Bom ", "Bom"),
        ("NÃO RECEBI", "NÃO RECEBI"),
        (" . ", None),
        ("   ", None),
        (None, None),
        (float("nan"), None),
    ],
)
def test_normalize_comment(raw: object, expected: str | None) -> None:
    assert normalize_comment(raw) == expected


# --- montagem das tabelas ---


def test_review_covering_two_orders_is_one_review_with_two_links() -> None:
    tables = build_tables(make_raw())
    reviews = tables["reviews"].set_index("review_id")
    assert len(reviews) == 2
    assert reviews.loc["r1", "n_orders"] == 2
    assert reviews.loc["r1", "comment_message"] == "Atrasou\nmuito"
    assert reviews.loc["r1", "has_comment"] == 1 and reviews.loc["r2", "has_comment"] == 0
    assert reviews.loc["r1", "created_week"] == "2018-03-12"
    assert sorted(map(tuple, tables["review_orders"].to_numpy())) == [
        ("r1", "o1"),
        ("r1", "o2"),
        ("r2", "o3"),
    ]


def test_divergent_review_content_raises() -> None:
    raw = make_raw()
    raw["reviews"].loc[1, "review_score"] = 5
    with pytest.raises(ValueError, match="divergente"):
        build_tables(raw)


def test_orders_have_delay_signal_and_aggregates() -> None:
    o = build_tables(make_raw())["orders"].set_index("order_id")
    assert (o.loc["o1", "delay_days"], o.loc["o1", "is_late"]) == (2, 1)
    assert (o.loc["o2", "delay_days"], o.loc["o2", "is_late"]) == (0, 0)
    assert pd.isna(o.loc["o3", "is_late"])
    assert (o.loc["o1", "n_items"], o.loc["o1", "n_sellers"], o.loc["o1", "n_categories"]) == (
        2,
        2,
        2,
    )
    assert o.loc["o1", "items_value"] == 30.0 and o.loc["o1", "payment_value"] == 33.0
    assert o.loc["o3", "n_items"] == 0 and o.loc["o3", "customer_state"] == "RJ"


def test_order_segments_multi_seller_and_missing_category() -> None:
    seg = build_tables(make_raw())["order_segments"]
    o1 = seg[seg["order_id"] == "o1"]
    assert set(o1["segment_value"][o1["segment_type"] == "vendedor"]) == {"s1", "s2"}
    assert set(o1["segment_value"][o1["segment_type"] == "categoria"]) == {
        "beleza_saude",
        NO_CATEGORY,
    }
    o3 = seg[seg["order_id"] == "o3"]
    assert o3[["segment_type", "segment_value"]].values.tolist() == [["estado", "RJ"]]


def test_quality_checks_count_without_dropping() -> None:
    raw = make_raw()
    checks = quality_checks(raw, build_tables(raw))
    assert checks["reviews_linked_to_multiple_orders"] == 1
    assert checks["comments_without_alnum_dropped"] == 1
    assert checks["orders_without_items"] == 1
    assert checks["products_without_category"] == 1


# --- banco ---


def test_database_roundtrip(tmp_path: Path) -> None:
    db = tmp_path / "radar.db"
    write_database(build_tables(make_raw()), db, {"versao": "teste"})
    con = sqlite3.connect(db)
    assert con.execute("SELECT value FROM meta WHERE key = 'versao'").fetchone() == ("teste",)
    assert con.execute("SELECT COUNT(*) FROM reviews").fetchone() == (2,)
    row = con.execute(
        "SELECT purchase_ts, is_late, delay_days FROM orders WHERE order_id = 'o1'"
    ).fetchone()
    assert row == ("2018-03-01 10:00:00", 1, 2)
    assert con.execute("SELECT is_late FROM orders WHERE order_id = 'o3'").fetchone() == (None,)
    # r1 cobre o1 e o2, ambos do vendedor s1: na view conta uma vez só
    n = con.execute(
        "SELECT COUNT(*) FROM review_segments WHERE review_id = 'r1' AND segment_value = 's1'"
    ).fetchone()
    assert n == (1,)
    indexes = {r[0] for r in con.execute("SELECT name FROM sqlite_master WHERE type = 'index'")}
    assert {"ix_reviews_answered_week", "ix_segments_type_value", "ix_items_seller"} <= indexes


def test_database_rejects_foreign_key_violation(tmp_path: Path) -> None:
    tables = build_tables(make_raw())
    tables["review_orders"].loc[0, "order_id"] = "inexistente"
    with pytest.raises(ValueError, match="chave estrangeira"):
        write_database(tables, tmp_path / "radar.db")
    assert not (tmp_path / "radar.db").exists()


def test_load_raw_reports_missing_files(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError, match="Baixe o dataset"):
        load_raw(tmp_path)


# --- amostra e estatísticas ---


def _reviews_db(tmp_path: Path) -> sqlite3.Connection:
    con = sqlite3.connect(tmp_path / "r.db")
    con.execute(
        "CREATE TABLE reviews (review_id TEXT, review_score INT, has_comment INT, "
        "review_creation_date TEXT)"
    )
    rows = [
        (f"r{s}_{i}", s, int(i % 3 != 0), "2018-08-31 00:00:00")
        for s in range(1, 6)
        for i in range(9)
    ]
    con.executemany("INSERT INTO reviews VALUES (?, ?, ?, ?)", rows)
    return con


def test_taxonomy_sample_is_stratified_and_deterministic(tmp_path: Path) -> None:
    con = _reviews_db(tmp_path)
    a = draw_sample(con, seed=42, per_score=3)
    b = draw_sample(con, seed=42, per_score=3)
    assert a.equals(b)
    assert a["review_score"].value_counts().to_dict() == {s: 3 for s in range(1, 6)}
    commented = {r[0] for r in con.execute("SELECT review_id FROM reviews WHERE has_comment")}
    assert set(a["review_id"]) <= commented


def test_late_window_end_leaves_margin_before_cutoff(tmp_path: Path) -> None:
    # corte em sexta 2018-08-31; menos 14 dias = 2018-08-17 (sexta) -> semana de 2018-08-13
    assert late_window_end(_reviews_db(tmp_path)) == "2018-08-13"


def test_md_table() -> None:
    df = pd.DataFrame({"a": [1, 2], "b": [0.5, float("nan")]})
    assert md_table(df) == "| a | b |\n|---|---|\n| 1 | 0.50 |\n| 2 |  |"
