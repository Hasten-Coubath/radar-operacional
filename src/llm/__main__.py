"""`python -m src.llm`: imprime o custo acumulado a partir do log de uso."""

import json

from src.config import load_config, resolve_path
from src.llm.cost import summarize_usage

cfg = load_config()
summary = summarize_usage(resolve_path(cfg["llm"]["usage_log"]))
print(json.dumps(summary, indent=2, ensure_ascii=False))
