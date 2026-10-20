"""Roda o classificador LLM num split do gold set e grava as previsões, sem texto (D-035).

Uso:
- `python -m src.classifier.run --role classifier --limit 5`: medição em 5 itens do dev,
  sorteados com a semente, com a estimativa de tempo para o dev inteiro;
- `python -m src.classifier.run --role classifier --confirm`: o dev inteiro. Acima de 50 itens o
  script exige `--confirm`, dado só depois do OK do usuário à estimativa (D-013).

O test set é recusado, salvo com `--allow-test`, reservado à avaliação única da Fase 5 (D-045).
`--prompt v2` escolhe outra versão do prompt. As previsões vão para `data/predictions/`; a
justificativa gerada pelo modelo fica só no cache, porque pode citar a avaliação.
"""

from __future__ import annotations

import argparse
import sqlite3
import statistics
from collections.abc import Sequence
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from src.classifier.llm import PROMPT_VERSION, Review, classify, load_prompt
from src.config import load_config, resolve_path
from src.labeling.gold import load_gold_sample
from src.llm.client import LLMClient
from src.taxonomy import AREA_BY_CAUSE

ALLOWED_SPLITS = ("dev",)  # o test só com allow_test=True, na Fase 5 (D-045)
MAX_UNCONFIRMED = 50
PREDICTIONS_DIR = "data/predictions"
CTX_WARN_SHARE = 0.9


def select_ids(
    sample: pd.DataFrame, split: str, limit: int | None, seed: int, *, allow_test: bool = False
) -> list[str]:
    """IDs do split na ordem de apresentação; com `limit`, um sorteio fixo pela semente."""
    if split not in ALLOWED_SPLITS and not (allow_test and split == "test"):
        raise SystemExit(f"Split {split!r} bloqueado: o test set só é usado na Fase 5.")
    part = sample[sample["split"] == split].sort_values("position")
    if limit is not None and limit < len(part):
        rng = np.random.default_rng(seed)
        part = part.iloc[np.sort(rng.choice(len(part), size=limit, replace=False))]
    return [str(r) for r in part["review_id"]]


def load_reviews(con: sqlite3.Connection, ids: Sequence[str]) -> list[Review]:
    df = pd.read_sql(
        "SELECT review_id, review_score, comment_title, comment_message FROM reviews "
        f"WHERE review_id IN ({','.join('?' * len(ids))})",
        con,
        params=list(ids),
    ).set_index("review_id")
    return [
        Review(
            review_id=rid,
            score=int(df.at[rid, "review_score"]),
            title=df.at[rid, "comment_title"]
            if isinstance(df.at[rid, "comment_title"], str)
            else None,
            message=str(df.at[rid, "comment_message"]),
        )
        for rid in ids
    ]


def warm_up(client: LLMClient, role: str) -> None:
    """Carrega o modelo na GPU com as mesmas opções do papel, fora do cache e do log de uso.

    A 1ª chamada inclui a carga do modelo (D-013) e não deve contar como custo por item.
    """
    req = client.request_for(role, [{"role": "user", "content": "ok"}])
    client.provider.generate(req.model_copy(update={"max_tokens": 1}))


def run(
    client: LLMClient,
    reviews: Sequence[Review],
    *,
    role: str,
    system: str,
    split: str,
    prompt_version: str = PROMPT_VERSION,
) -> pd.DataFrame:
    settings = client.roles[role]
    options = settings.options or {}
    rows: list[dict[str, Any]] = []
    for i, review in enumerate(reviews, 1):
        res = classify(client, review, role=role, system=system, tag=f"{role}_{prompt_version}")
        first = res.attempts[0]
        p = res.parsed
        rows.append(
            {
                "review_id": review.review_id,
                "split": split,
                "prompt_version": prompt_version,
                "model": settings.model,
                "think": settings.think,
                "num_ctx": options.get("num_ctx"),
                "temperature": options.get("temperature"),
                "causa": p.causa if p else "",
                "gravidade": p.gravidade if p else "",
                "confianca": p.confianca if p else None,
                "area": AREA_BY_CAUSE[p.causa] if p else "",
                "schema_ok": p is not None,
                "attempts": len(res.attempts),
                "cached": all(a.cached for a in res.attempts),
                "latency_s": round(res.latency_s, 3),
                "input_tokens": first.response.usage.input_tokens,
                "output_tokens": sum(a.response.usage.output_tokens for a in res.attempts),
                "stop_reason": res.attempts[-1].response.stop_reason,
                "cache_key": first.cache_key,
            }
        )
        print(
            f"[{i}/{len(reviews)}] {review.review_id[:8]} nota {review.score}: "
            f"{rows[-1]['causa'] or 'SCHEMA INVÁLIDO'} | {res.latency_s:.2f} s | "
            f"{rows[-1]['output_tokens']} tokens de saída | "
            f"{'cache' if rows[-1]['cached'] else 'chamada real'}"
        )
    return pd.DataFrame(rows)


def estimate(df: pd.DataFrame, n_total: int, num_ctx: int | None) -> list[str]:
    """Resumo de tempo das chamadas reais e estimativa para `n_total` itens."""
    live = df[~df["cached"]]
    lines = [f"itens: {len(df)} ({len(live)} com chamada real, {len(df) - len(live)} do cache)"]
    if live.empty:
        return [*lines, "sem chamadas reais: nada a medir"]
    lat = live["latency_s"].tolist()
    med, worst = statistics.median(lat), max(lat)
    lines += [
        f"s/item (chamadas reais): mediana {med:.2f}, média {statistics.mean(lat):.2f}, "
        f"mín {min(lat):.2f}, máx {worst:.2f}",
        f"tokens de saída por item: mediana {statistics.median(live['output_tokens']):.0f}, "
        f"máx {live['output_tokens'].max()}",
        f"tokens de entrada (1ª tentativa): máx {df['input_tokens'].max()}"
        + (f" de num_ctx {num_ctx}" if num_ctx else ""),
        f"schema válido: {int(df['schema_ok'].sum())}/{len(df)}; "
        f"itens com 2ª tentativa: {int((df['attempts'] > 1).sum())}",
        f"estimativa para {n_total} itens: {n_total * med / 60:.1f} min pela mediana; "
        f"pior caso (máx observado × 2 tentativas) {n_total * worst * 2 / 60:.1f} min",
    ]
    if num_ctx and (df["input_tokens"] + df["output_tokens"]).max() > CTX_WARN_SHARE * num_ctx:
        lines.append(f"ALERTA: entrada + saída passou de {CTX_WARN_SHARE:.0%} de num_ctx")
    return lines


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--role", default="classifier", help="papel em config.yaml")
    parser.add_argument("--split", default="dev")
    parser.add_argument("--limit", type=int, default=None, help="sorteia N itens do split")
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--prompt", default=PROMPT_VERSION, help="versão em prompts/")
    parser.add_argument("--allow-test", action="store_true", help="só na Fase 5 (D-045)")
    parser.add_argument(
        "--confirm", action="store_true", help=f"exigido acima de {MAX_UNCONFIRMED}"
    )
    args = parser.parse_args()

    cfg = load_config()
    sample = load_gold_sample(resolve_path(cfg["paths"]["gold_dir"]))
    ids = select_ids(sample, args.split, args.limit, args.seed, allow_test=args.allow_test)
    if len(ids) > MAX_UNCONFIRMED and not args.confirm:
        raise SystemExit(
            f"{len(ids)} itens (> {MAX_UNCONFIRMED}): mostre a estimativa ao usuário e, com o OK, "
            "rode de novo com --confirm."
        )
    con = sqlite3.connect(f"file:{resolve_path(cfg['paths']['db_path'])}?mode=ro", uri=True)
    reviews = load_reviews(con, ids)
    con.close()

    client = LLMClient.from_config(cfg)
    settings = client.roles[args.role]
    print(
        f"papel {args.role}: {settings.model}, think={settings.think}, "
        f"options={settings.options}, max_tokens={settings.max_tokens}, prompt {args.prompt}"
    )
    if client.mode == "live":
        warm_up(client, args.role)
    df = run(
        client,
        reviews,
        role=args.role,
        system=load_prompt(args.prompt),
        split=args.split,
        prompt_version=args.prompt,
    )

    suffix = f"_n{args.limit}" if args.limit is not None else ""
    out = resolve_path(PREDICTIONS_DIR) / f"{args.role}_{args.prompt}_{args.split}{suffix}.csv"
    Path(out).parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(out, index=False, lineterminator="\n")
    n_split = int((sample["split"] == args.split).sum())
    num_ctx = (settings.options or {}).get("num_ctx")
    print("\n".join(["", *estimate(df, n_split, num_ctx), f"previsões em {out}"]))


if __name__ == "__main__":
    main()
