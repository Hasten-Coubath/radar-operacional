"""Provas de que o acesso SQL do agente é somente leitura, com limite de tempo e de linhas."""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from src.agent.sql import QueryRejected, ReadOnlySQL


@pytest.fixture
def db(tmp_path: Path) -> Path:
    path = tmp_path / "t.db"
    con = sqlite3.connect(path)
    con.execute("CREATE TABLE reviews (review_id TEXT, review_score INT)")
    con.executemany("INSERT INTO reviews VALUES (?, ?)", [(f"r{i}", i % 5 + 1) for i in range(500)])
    con.commit()
    con.close()
    return path


def count(path: Path) -> int:
    con = sqlite3.connect(path)
    try:
        return int(con.execute("SELECT COUNT(*) FROM reviews").fetchone()[0])
    finally:
        con.close()


WRITES = [
    "INSERT INTO reviews VALUES ('x', 1)",
    "UPDATE reviews SET review_score = 0",
    "DELETE FROM reviews",
    "DROP TABLE reviews",
    "CREATE TABLE x (a INT)",
    "ALTER TABLE reviews ADD COLUMN x INT",
    "ATTACH DATABASE 'outro.db' AS o",
    "PRAGMA query_only = OFF",
    "VACUUM",
    "REPLACE INTO reviews VALUES ('x', 1)",
]


@pytest.mark.parametrize("sql", WRITES)
def test_writes_are_blocked_by_text_check(db: Path, sql: str) -> None:
    sq = ReadOnlySQL(db)
    with pytest.raises(QueryRejected):
        sq.query(sql)
    assert count(db) == 500


@pytest.mark.parametrize(
    "sql",
    [
        "WITH x AS (SELECT 1) DELETE FROM reviews",
        "WITH x AS (SELECT 1) INSERT INTO reviews VALUES ('x', 1)",
        "WITH x AS (SELECT 1) UPDATE reviews SET review_score = 0",
    ],
)
def test_writes_disguised_as_with_are_blocked_by_sqlite(db: Path, sql: str) -> None:
    """Passa na checagem de texto (começa com WITH), mas o banco recusa."""
    sq = ReadOnlySQL(db)
    with pytest.raises(QueryRejected):
        sq.query(sql)
    assert count(db) == 500


def test_each_layer_blocks_writes_on_its_own(db: Path) -> None:
    # sem a checagem de texto: o autorizador e o modo somente leitura ainda bloqueiam
    sq = ReadOnlySQL(db)
    for sql in (
        "DELETE FROM reviews",
        "ATTACH DATABASE ':memory:' AS m",
        "PRAGMA query_only = OFF",
    ):
        with pytest.raises(sqlite3.DatabaseError):
            sq.con.execute(sql)
    # só o modo ro do arquivo, sem autorizador nem query_only
    raw = sqlite3.connect(f"file:{db.as_posix()}?mode=ro", uri=True)
    with pytest.raises(sqlite3.OperationalError):
        raw.execute("DELETE FROM reviews")
    raw.close()
    assert count(db) == 500


def test_multiple_statements_and_comments(db: Path) -> None:
    sq = ReadOnlySQL(db)
    with pytest.raises(QueryRejected, match="uma instrução"):
        sq.query("SELECT 1; DELETE FROM reviews")
    with pytest.raises(QueryRejected):
        sq.query("/* SELECT */ DELETE FROM reviews")
    assert sq.query("-- comentário\nSELECT COUNT(*) FROM reviews;").scalar() == 500


def test_row_limit_and_scalar(db: Path) -> None:
    sq = ReadOnlySQL(db, max_rows=10)
    r = sq.query("SELECT review_id FROM reviews")
    assert len(r.rows) == 10 and r.truncated
    with pytest.raises(QueryRejected, match="único valor"):
        r.scalar()
    assert sq.query("SELECT AVG(review_score) FROM reviews").scalar() == pytest.approx(3.0)


def test_timeout_interrupts_long_query(db: Path) -> None:
    sq = ReadOnlySQL(db, timeout_s=0.2)
    slow = (
        "WITH RECURSIVE c(x) AS (SELECT 1 UNION ALL SELECT x + 1 FROM c WHERE x < 100000000) "
        "SELECT COUNT(*) FROM c"
    )
    with pytest.raises(QueryRejected, match="tempo limite"):
        sq.query(slow)
    assert sq.query("SELECT 1").scalar() == 1  # a conexão continua utilizável


def test_classifications_db_is_attached_read_only(db: Path, tmp_path: Path) -> None:
    import pandas as pd

    from src.agent.classifications import build

    lote = pd.DataFrame(
        {
            "review_id": ["r1", "r2"],
            "review_score": ["1", "5"],
            "answered_week": ["2018-04-02"] * 2,
            "status": ["classificado", "nao_classificado"],
            "causa": ["qualidade_insatisfatoria", ""],
            "area": ["vendedor", ""],
        }
    )
    cdb = tmp_path / "c.db"
    assert build(lote, cdb) == 2
    sq = ReadOnlySQL(db, attach={"c": cdb})
    assert (
        sq.query("SELECT familia FROM classificacoes WHERE review_id = 'r1'").scalar() == "produto"
    )
    with pytest.raises(QueryRejected):
        sq.query("WITH x AS (SELECT 1) DELETE FROM classificacoes")
    with pytest.raises(sqlite3.DatabaseError):
        sq.con.execute("DELETE FROM c.classificacoes")
