"""Cache em disco das chamadas ao LLM: um arquivo JSON por chave."""

from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path
from typing import Any


class DiskCache:
    """Armazena `{request, response}` em `<root>/<key[:2]>/<key>.json`."""

    def __init__(self, root: Path) -> None:
        self.root = Path(root)

    def _path(self, key: str) -> Path:
        return self.root / key[:2] / f"{key}.json"

    def get(self, key: str) -> dict[str, Any] | None:
        path = self._path(key)
        if not path.exists():
            return None
        with open(path, encoding="utf-8") as f:
            entry: dict[str, Any] = json.load(f)
        return entry

    def put(self, key: str, entry: dict[str, Any]) -> None:
        """Escrita atômica (arquivo temporário + rename) para não deixar JSON corrompido."""
        path = self._path(key)
        path.parent.mkdir(parents=True, exist_ok=True)
        fd, tmp = tempfile.mkstemp(dir=path.parent, suffix=".tmp")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                json.dump(entry, f, ensure_ascii=False, indent=1)
            os.replace(tmp, path)
        except BaseException:
            Path(tmp).unlink(missing_ok=True)
            raise

    def __contains__(self, key: str) -> bool:
        return self._path(key).exists()
