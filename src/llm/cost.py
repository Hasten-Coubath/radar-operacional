"""Preços por modelo, registro de uso (JSONL) e resumo de tempo de processamento e custo."""

from __future__ import annotations

import json
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from src.llm.types import LLMUsage


@dataclass(frozen=True)
class ModelPricing:
    """USD por milhão de tokens. Tokens de cache sem preço próprio pagam o preço de input."""

    input: float
    output: float
    cache_read: float | None = None
    cache_write: float | None = None

    def cost(self, usage: LLMUsage) -> float:
        read = self.cache_read if self.cache_read is not None else self.input
        write = self.cache_write if self.cache_write is not None else self.input
        total = (
            usage.input_tokens * self.input
            + usage.output_tokens * self.output
            + usage.cache_read_input_tokens * read
            + usage.cache_creation_input_tokens * write
        )
        return total / 1_000_000


class PriceTable:
    def __init__(self, prices: dict[str, ModelPricing]) -> None:
        self.prices = prices

    @classmethod
    def from_config(cls, raw: dict[str, dict[str, float]]) -> PriceTable:
        return cls({model: ModelPricing(**p) for model, p in raw.items()})

    def estimate(self, model: str, usage: LLMUsage) -> float | None:
        """Custo estimado em USD, ou None se o modelo não tem preço configurado."""
        pricing = self.prices.get(model)
        return pricing.cost(usage) if pricing else None


class UsageLogger:
    """Acrescenta um registro JSON por chamada (inclusive cache hits)."""

    def __init__(self, path: Path) -> None:
        self.path = Path(path)

    def log(self, record: dict[str, Any]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with open(self.path, "a", encoding="utf-8") as f:
            f.write(json.dumps(record, ensure_ascii=False) + "\n")


def _group() -> dict[str, Any]:
    return {"calls_live": 0, "processing_s": 0.0, "output_tokens": 0, "cost_usd_spent": 0.0}


def summarize_usage(path: Path) -> dict[str, Any]:
    """Totais do log: chamadas reais × cache, tempo de processamento, tokens e custo.

    O tempo de processamento (soma da latência das chamadas reais) é a métrica principal de
    custo com modelos locais; `processing_s_saved_by_cache` é o tempo original das respostas
    reaproveitadas do cache.
    """
    summary: dict[str, Any] = {
        "calls_live": 0,
        "calls_cached": 0,
        "processing_s_live": 0.0,
        "processing_s_saved_by_cache": 0.0,
        "input_tokens_live": 0,
        "output_tokens_live": 0,
        "cost_usd_spent": 0.0,
        "calls_without_price": 0,
        "by_model": defaultdict(_group),
        "by_tag": defaultdict(_group),
    }
    path = Path(path)
    if not path.exists():
        return summary
    with open(path, encoding="utf-8") as f:
        for line in f:
            if not line.strip():
                continue
            rec = json.loads(line)
            latency = rec.get("latency_s") or 0.0
            if rec["cached"]:
                summary["calls_cached"] += 1
                summary["processing_s_saved_by_cache"] += latency
                continue
            cost = rec.get("cost_usd_spent")
            summary["calls_live"] += 1
            summary["processing_s_live"] += latency
            summary["input_tokens_live"] += rec["input_tokens"]
            summary["output_tokens_live"] += rec["output_tokens"]
            if cost is None:
                summary["calls_without_price"] += 1
                cost = 0.0
            summary["cost_usd_spent"] += cost
            for group, name in (("by_model", rec["model"]), ("by_tag", rec.get("tag") or "-")):
                g = summary[group][name]
                g["calls_live"] += 1
                g["processing_s"] += latency
                g["output_tokens"] += rec["output_tokens"]
                g["cost_usd_spent"] += cost
    for group in ("by_model", "by_tag"):
        for g in summary[group].values():
            g["s_per_call"] = g["processing_s"] / g["calls_live"]
            g["output_tokens_per_s"] = (
                g["output_tokens"] / g["processing_s"] if g["processing_s"] else None
            )
        summary[group] = dict(summary[group])
    return summary
