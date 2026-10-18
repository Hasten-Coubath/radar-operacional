"""Carrega `config.yaml` e `.env`, aplicando sobrescritas por variáveis de ambiente."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import yaml
from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parent.parent

# variável de ambiente -> caminho da chave em config.yaml
ENV_OVERRIDES: dict[str, tuple[str, ...]] = {
    "RADAR_DB_PATH": ("paths", "db_path"),
    "RADAR_GOLD_DIR": ("paths", "gold_dir"),
    "RADAR_LLM_PROVIDER": ("llm", "provider"),
    "RADAR_LLM_MODE": ("llm", "mode"),
    # não usamos OLLAMA_HOST: o servidor o lê como endereço de bind (ex.: "0.0.0.0")
    "RADAR_OLLAMA_URL": ("llm", "providers", "ollama", "base_url"),
    "RADAR_CLASSIFIER_MODEL": ("llm", "roles", "classifier", "model"),
    "RADAR_AGENT_MODEL": ("llm", "roles", "agent", "model"),
}


def load_config(path: Path | None = None, *, load_env: bool = True) -> dict[str, Any]:
    """Lê o YAML de configuração e aplica as sobrescritas de `ENV_OVERRIDES`."""
    if load_env:
        load_dotenv(PROJECT_ROOT / ".env", override=False)
    path = path or PROJECT_ROOT / "config.yaml"
    with open(path, encoding="utf-8") as f:
        cfg: dict[str, Any] = yaml.safe_load(f)
    for var, keys in ENV_OVERRIDES.items():
        value = os.environ.get(var)
        if value:
            _set_nested(cfg, keys, value)
    return cfg


def resolve_path(path: str | Path) -> Path:
    """Resolve caminhos relativos a partir da raiz do projeto."""
    p = Path(path)
    return p if p.is_absolute() else PROJECT_ROOT / p


def _set_nested(cfg: dict[str, Any], keys: tuple[str, ...], value: Any) -> None:
    node = cfg
    for key in keys[:-1]:
        node = node.setdefault(key, {})
    node[keys[-1]] = value
