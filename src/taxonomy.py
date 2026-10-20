"""Taxonomia de causas (v1.1, D-034): classes, mapeamento causa -> área e textos da doc.

As definições ficam só em `docs/taxonomia.md`; `taxonomy_sections` as lê de lá para exibição
(ferramenta de rotulagem), evitando duas cópias que possam divergir.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Final

TAXONOMY_VERSION = "v1.1"

CAUSES: tuple[str, ...] = (
    "problema_entrega",
    "produto_defeituoso_ou_danificado",
    "produto_diferente_do_anunciado",
    "pedido_incompleto_ou_errado",
    "qualidade_insatisfatoria",
    "problema_atendimento_ou_comunicacao",
    "elogio",
    "outro",
)
AMBIGUOUS: Final = "ambiguo"  # só na rotulagem humana: "ambíguo / não sei"

# Mapeamento fixo causa -> área responsável (D-027). Não é rotulado nem previsto.
AREA_BY_CAUSE: dict[str, str] = {
    "problema_entrega": "logistica",
    "produto_defeituoso_ou_danificado": "vendedor",
    "produto_diferente_do_anunciado": "vendedor",
    "pedido_incompleto_ou_errado": "vendedor",
    "qualidade_insatisfatoria": "vendedor",
    "problema_atendimento_ou_comunicacao": "atendimento",
    "elogio": "nenhuma",
    "outro": "indefinida",
    AMBIGUOUS: "indefinida",
}

_HEADING = re.compile(r"^(#{2,3}) (.+)$", flags=re.MULTILINE)


def area_for(cause: str) -> str:
    return AREA_BY_CAUSE[cause]


def taxonomy_sections(path: Path) -> dict[str, str]:
    """Seções de `docs/taxonomia.md`: 'Regras gerais' e uma por classe (chave = nome da classe)."""
    text = path.read_text(encoding="utf-8")
    matches = list(_HEADING.finditer(text))
    out: dict[str, str] = {}
    for i, m in enumerate(matches):
        end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
        title = m.group(2).strip().strip("`")
        body = text[m.end() : end].strip()
        if title in CAUSES or title == "Regras gerais":
            out[title] = body
    return out
