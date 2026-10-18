"""Mede o tempo por chamada do modelo do classificador, com e sem raciocínio.

Uso: `python -m src.llm.bench`. Usa 5 textos sintéticos (não vêm do dataset) e um cache
temporário, para medir chamadas reais. A 1ª chamada (carga do modelo na GPU) é feita antes e
descartada. Serve de base para as estimativas de tempo antes de execuções com > 50 chamadas.
"""

from __future__ import annotations

import json
import statistics
import tempfile
from pathlib import Path
from typing import Literal

from pydantic import BaseModel

from src.config import load_config
from src.llm.client import LLMClient

TEXTS = [
    "Chegou quebrado, não liga.",
    "Adorei, chegou antes do prazo!",
    "Faz 20 dias e nada do pedido.",
    "O frete foi caro demais.",
    "Produto bom, mas a caixa veio amassada e faltou um item.",
]


class BenchOutput(BaseModel):
    causa: Literal["atraso_entrega", "produto_defeituoso", "pedido_incompleto", "elogio", "outro"]
    confianca: float


def main() -> None:
    cfg = load_config()
    system = "Classifique a causa da avaliação. Responda só com JSON: " + json.dumps(
        BenchOutput.model_json_schema(), ensure_ascii=False
    )
    with tempfile.TemporaryDirectory() as tmp:
        cfg["llm"].update(cache_dir=str(Path(tmp) / "c"), usage_log=str(Path(tmp) / "u.jsonl"))
        client = LLMClient.from_config(cfg)
        warmup = client.request_for("classifier", [{"role": "user", "content": "aquecimento"}])
        client.generate(warmup)
        print(f"modelo: {client.roles['classifier'].model} | {len(TEXTS)} textos sintéticos")
        for think in (False, True):
            wall, out_tokens, valid = [], [], 0
            for text in TEXTS:
                req = client.request_for(
                    "classifier", [{"role": "user", "content": f"Avaliação: {text}"}], system=system
                ).model_copy(update={"think": think, "max_tokens": 4096})
                res = client.generate_structured(req, BenchOutput, tag=f"bench_think_{think}")
                first = res.attempts[0].response
                wall.append(first.latency_s)
                out_tokens.append(first.usage.output_tokens)
                valid += res.parsed is not None
            print(
                f"think={think!s:<5} s/chamada: mediana {statistics.median(wall):.2f} "
                f"(mín {min(wall):.2f}, máx {max(wall):.2f}) | tokens de saída: mediana "
                f"{statistics.median(out_tokens):.0f} | JSON válido: {valid}/{len(TEXTS)}"
            )


if __name__ == "__main__":
    main()
