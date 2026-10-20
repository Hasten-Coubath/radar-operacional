"""Classificador de causa com LLM: schema da saída, prompt versionado e uma chamada por avaliação.

A área responsável não é prevista: vem da causa (`src.taxonomy.AREA_BY_CAUSE`, D-027/D-034).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from pydantic import BaseModel, Field

from src.config import load_config, resolve_path
from src.llm.client import LLMClient, StructuredResult
from src.taxonomy import Cause

PROMPT_VERSION = "v1"
MAX_JUSTIFICATION_CHARS = 300


class Classification(BaseModel):
    """Saída do classificador. A justificativa vem primeiro: o modelo explica antes de decidir."""

    justificativa: str = Field(max_length=MAX_JUSTIFICATION_CHARS)
    causa: Cause
    gravidade: Literal["baixa", "media", "alta"]
    confianca: float = Field(ge=0, le=1)


@dataclass(frozen=True)
class Review:
    review_id: str
    score: int
    title: str | None
    message: str


def load_prompt(version: str = PROMPT_VERSION) -> str:
    path = resolve_path(load_config()["paths"]["prompts_dir"]) / f"classifier_{version}.md"
    return path.read_text(encoding="utf-8").strip()


def user_message(review: Review) -> str:
    """Entrada do modelo: nota, título e mensagem (D-029). Nada do pedido entra."""
    title = review.title.strip() if review.title and review.title.strip() else "(sem título)"
    return f"Nota: {review.score} de 5\nTítulo: {title}\nMensagem: {review.message.strip()}"


def classify(
    client: LLMClient, review: Review, *, role: str, system: str, tag: str | None = None
) -> StructuredResult[Classification]:
    request = client.request_for(
        role, [{"role": "user", "content": user_message(review)}], system=system
    )
    return client.generate_structured(request, Classification, tag=tag)
