"""Acesso SQL somente leitura para o agente investigador (Fase 8).

Quatro camadas, cada uma suficiente para bloquear escrita:
1. o arquivo é aberto com `mode=ro` (URI do SQLite);
2. `PRAGMA query_only = ON`;
3. um autorizador do SQLite que só permite leitura (SELECT, leitura de colunas, funções e CTE
   recursiva) e nega todo o resto, inclusive ATTACH e PRAGMA;
4. o texto precisa começar com SELECT ou WITH, e só uma instrução por chamada.

Cada consulta tem limite de tempo (via progress handler) e de linhas devolvidas.
"""

from __future__ import annotations

import re
import sqlite3
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

MAX_ROWS = 200
TIMEOUT_S = 5.0
_ALLOWED_ACTIONS = {
    sqlite3.SQLITE_SELECT,
    sqlite3.SQLITE_READ,
    sqlite3.SQLITE_FUNCTION,
    getattr(sqlite3, "SQLITE_RECURSIVE", 33),
}
_COMMENTS = re.compile(r"(--[^\n]*|/\*.*?\*/)", flags=re.DOTALL)
_FIRST_WORD = re.compile(r"^\s*(\w+)", flags=re.IGNORECASE)


class QueryRejected(ValueError):
    """Consulta recusada antes ou durante a execução (não é leitura, tempo, sintaxe)."""


@dataclass
class QueryResult:
    columns: list[str]
    rows: list[tuple[Any, ...]]
    truncated: bool
    elapsed_s: float
    extra: dict[str, Any] = field(default_factory=dict)

    def scalar(self) -> Any:
        """Valor único (1 linha × 1 coluna); erro se o formato for outro."""
        if len(self.rows) != 1 or len(self.columns) != 1:
            raise QueryRejected(
                f"a consulta devolveu {len(self.rows)} linha(s) × {len(self.columns)} coluna(s); "
                "uma afirmação precisa de um único valor"
            )
        return self.rows[0][0]


def _authorizer(action: int, *_: Any) -> int:
    return sqlite3.SQLITE_OK if action in _ALLOWED_ACTIONS else sqlite3.SQLITE_DENY


def check_text(sql: str) -> str:
    """Rejeita o que não começa com SELECT/WITH ou tem mais de uma instrução."""
    body = _COMMENTS.sub(" ", sql).strip().rstrip(";").strip()
    m = _FIRST_WORD.match(body)
    if not m or m.group(1).upper() not in {"SELECT", "WITH"}:
        raise QueryRejected("só consultas SELECT (ou WITH ... SELECT) são permitidas")
    if ";" in body:
        raise QueryRejected("só uma instrução por consulta")
    return body


class ReadOnlySQL:
    """Conexão somente leitura ao banco do projeto, opcionalmente com o banco de classificações."""

    def __init__(
        self,
        db_path: Path,
        *,
        attach: dict[str, Path] | None = None,
        max_rows: int = MAX_ROWS,
        timeout_s: float = TIMEOUT_S,
    ) -> None:
        self.max_rows = max_rows
        self.timeout_s = timeout_s
        self.con = sqlite3.connect(f"file:{Path(db_path).as_posix()}?mode=ro", uri=True)
        for alias, path in (attach or {}).items():
            # anexado antes do autorizador; depois dele, ATTACH é negado
            self.con.execute(f"ATTACH DATABASE 'file:{Path(path).as_posix()}?mode=ro' AS {alias}")
        self.con.execute("PRAGMA query_only = ON")
        self.con.set_authorizer(_authorizer)
        self._deadline = 0.0
        self.con.set_progress_handler(self._progress, 1000)

    def _progress(self) -> int:
        return 1 if time.perf_counter() > self._deadline else 0

    def query(self, sql: str) -> QueryResult:
        body = check_text(sql)
        self._deadline = time.perf_counter() + self.timeout_s
        t0 = time.perf_counter()
        try:
            cur = self.con.execute(body)
            rows = cur.fetchmany(self.max_rows + 1)
        except sqlite3.DatabaseError as e:
            msg = str(e)
            if "interrupted" in msg:
                msg = f"tempo limite de {self.timeout_s:.0f} s excedido"
            raise QueryRejected(msg) from e
        cols = [d[0] for d in cur.description or []]
        return QueryResult(
            columns=cols,
            rows=[tuple(r) for r in rows[: self.max_rows]],
            truncated=len(rows) > self.max_rows,
            elapsed_s=time.perf_counter() - t0,
        )

    def close(self) -> None:
        self.con.close()
