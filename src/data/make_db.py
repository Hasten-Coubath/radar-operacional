"""Gera `data/processed/radar.db` a partir de `data/raw/`. Uso: `python -m src.data.make_db`."""

from __future__ import annotations

import json

from src.config import load_config, resolve_path
from src.data.build import build_tables, quality_checks
from src.data.database import write_database
from src.data.load import RAW_FILES, file_sha256, load_raw


def main() -> None:
    cfg = load_config()
    raw_dir = resolve_path(cfg["paths"]["raw_dir"])
    db_path = resolve_path(cfg["paths"]["db_path"])

    raw = load_raw(raw_dir)
    tables = build_tables(raw)
    checks = quality_checks(raw, tables)
    meta = {
        "source_sha256": json.dumps(
            {f: file_sha256(raw_dir / f) for f, _ in RAW_FILES.values()}, sort_keys=True
        ),
        "row_counts": json.dumps({k: len(v) for k, v in tables.items()}, sort_keys=True),
        "quality_checks": json.dumps(checks, sort_keys=True),
    }
    write_database(tables, db_path, meta)

    print(f"Banco gerado em {db_path}")
    for name, df in tables.items():
        print(f"  {name:<15} {len(df):>8} linhas")
    print("Checagens de qualidade (linhas mantidas, não descartadas):")
    for k, v in checks.items():
        print(f"  {k:<42} {v:>8}")


if __name__ == "__main__":
    main()
