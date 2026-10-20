"""Verificador do briefing do agente: cada afirmação numérica é reexecutada (Fase 8).

O briefing traz uma lista de afirmações, cada uma com o valor citado e a `query_sql` que o
produz. O verificador roda a consulta de novo na conexão somente leitura e compara. Números no
resumo que não correspondem a nenhuma afirmação também são apontados.
"""

from __future__ import annotations

import math
import re
from dataclasses import dataclass
from typing import Literal

from pydantic import BaseModel, Field

from src.agent.sql import QueryRejected, ReadOnlySQL

REL_TOL = 1e-3
DECIMALS = 2  # o valor citado pode estar arredondado em até 2 casas
MAX_CLAIMS = 12
_NUMBER = re.compile(r"(?<![\w.])\d+(?:[.,]\d+)?")
# heurística: datas e menções a nota ("nota 1", "notas ≤ 2") não são números a verificar
_IGNORED = re.compile(
    r"\d{4}-\d{2}-\d{2}"
    r"|notas?\s*(?:de\s*|foram\s*|igual a\s*)?(?:≤|<=|>=|≥|<|>)?\s*[1-5](?!\d)",
    flags=re.IGNORECASE,
)


class Claim(BaseModel):
    texto: str = Field(max_length=300, description="a afirmação, em uma frase")
    valor: float = Field(description="o número citado, exatamente como a consulta devolve")
    query_sql: str = Field(max_length=2000, description="SELECT que devolve esse único valor")


class Briefing(BaseModel):
    resumo: str = Field(max_length=1500)
    causa_provavel: str = Field(max_length=300)
    afirmacoes: list[Claim] = Field(max_length=MAX_CLAIMS)


Status = Literal["verificada", "divergente", "erro"]


@dataclass(frozen=True)
class ClaimCheck:
    texto: str
    valor_citado: float
    valor_recalculado: float | None
    status: Status
    detalhe: str


def same_value(cited: float, actual: float) -> bool:
    """Igual se bater com arredondamento de até 2 casas ou com tolerância relativa de 0,1%."""
    return round(actual, DECIMALS) == round(cited, DECIMALS) or math.isclose(
        actual, cited, rel_tol=REL_TOL
    )


def check_claim(claim: Claim, sql: ReadOnlySQL) -> ClaimCheck:
    try:
        value = sql.query(claim.query_sql).scalar()
    except QueryRejected as e:
        return ClaimCheck(claim.texto, claim.valor, None, "erro", str(e))
    if not isinstance(value, int | float) or isinstance(value, bool):
        return ClaimCheck(claim.texto, claim.valor, None, "erro", f"valor não numérico: {value!r}")
    ok = same_value(claim.valor, float(value))
    return ClaimCheck(
        claim.texto,
        claim.valor,
        float(value),
        "verificada" if ok else "divergente",
        "" if ok else f"a consulta devolve {value}",
    )


def numbers_in(text: str) -> list[float]:
    """Números do texto, sem datas nem menções a nota (heurística)."""
    clean = _IGNORED.sub(" ", text)
    return [float(m.replace(",", ".")) for m in _NUMBER.findall(clean)]


def unsupported_numbers(briefing: Briefing) -> list[float]:
    """Números do resumo e da causa provável que não aparecem em nenhuma afirmação."""
    cited = [c.valor for c in briefing.afirmacoes]
    free = numbers_in(briefing.resumo) + numbers_in(briefing.causa_provavel)
    return [x for x in free if not any(same_value(x, c) or same_value(x, 100 * c) for c in cited)]


def verify(briefing: Briefing, sql: ReadOnlySQL) -> tuple[list[ClaimCheck], list[float]]:
    return [check_claim(c, sql) for c in briefing.afirmacoes], unsupported_numbers(briefing)
