"""Rótulos do gold set: modelo validado e armazenamento em CSV com escrita atômica."""

from __future__ import annotations

import csv
import os
import tempfile
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field, model_validator

from src.taxonomy import AMBIGUOUS, Cause

LABELS_FILE = "labels.csv"
MAX_NOTE_CHARS = 200


class Label(BaseModel):
    """Um rótulo manual (taxonomia v1.1). `causa = "ambiguo"` registra "ambíguo / não sei".

    A causa secundária é informativa e não entra nas métricas (D-034).
    """

    review_id: str
    causa: Cause | Literal["ambiguo"]
    causa_secundaria: Cause | None = None
    nota_livre: str = Field(default="", max_length=MAX_NOTE_CHARS)
    updated_at: str = ""

    @model_validator(mode="after")
    def _secondary_differs(self) -> Label:
        if self.causa_secundaria is not None and self.causa_secundaria == self.causa:
            raise ValueError("causa secundária igual à principal")
        return self


FIELDS = list(Label.model_fields)


class LabelStore:
    """Lê e grava `labels.csv`. Cada `save` reescreve o arquivo inteiro de forma atômica."""

    def __init__(self, gold_dir: Path) -> None:
        self.path = Path(gold_dir) / LABELS_FILE

    def load(self) -> dict[str, Label]:
        if not self.path.exists():
            return {}
        with open(self.path, encoding="utf-8", newline="") as f:
            rows = list(csv.DictReader(f))
        out = {}
        for row in rows:
            label = Label.model_validate(
                {**row, "causa_secundaria": row["causa_secundaria"] or None}
            )
            out[label.review_id] = label
        return out

    def save(self, label: Label, order: list[str]) -> Label:
        """Grava/atualiza um rótulo. `order` (IDs na ordem de apresentação) fixa a ordem do CSV."""
        stamped = label.model_copy(update={"updated_at": _now()})
        labels = self.load()
        labels[stamped.review_id] = stamped
        rank = {rid: i for i, rid in enumerate(order)}
        rows = sorted(labels.values(), key=lambda lb: rank.get(lb.review_id, len(rank)))
        self.path.parent.mkdir(parents=True, exist_ok=True)
        fd, tmp = tempfile.mkstemp(dir=self.path.parent, suffix=".tmp")
        try:
            with os.fdopen(fd, "w", encoding="utf-8", newline="") as f:
                writer = csv.DictWriter(f, fieldnames=FIELDS, lineterminator="\n")
                writer.writeheader()
                for lb in rows:
                    writer.writerow(_to_row(lb))
            os.replace(tmp, self.path)
        except BaseException:
            Path(tmp).unlink(missing_ok=True)
            raise
        return stamped


def _to_row(label: Label) -> dict[str, str]:
    return {
        "review_id": label.review_id,
        "causa": label.causa,
        "causa_secundaria": label.causa_secundaria or "",
        "nota_livre": label.nota_livre,
        "updated_at": label.updated_at,
    }


def _now() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


__all__ = ["AMBIGUOUS", "FIELDS", "Label", "LabelStore"]
