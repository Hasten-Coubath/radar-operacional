"""Testes do classificador LLM com provedor falso: nenhuma chamada real ao modelo."""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import pytest

from src.classifier.llm import Classification, Review, load_prompt, user_message
from src.classifier.run import estimate, run, select_ids
from src.llm.cache import DiskCache
from src.llm.client import LLMClient, RoleSettings
from src.llm.cost import ModelPricing, PriceTable, UsageLogger
from src.taxonomy import CAUSES
from tests.test_llm_client import FakeProvider

REVIEW = Review(review_id="r1", score=2, title=None, message=" Chegou quebrado. ")


def client_with(tmp_path: Path, texts: list[str]) -> LLMClient:
    return LLMClient(
        provider=FakeProvider(texts),
        cache=DiskCache(tmp_path / "cache"),
        prices=PriceTable({"m": ModelPricing(input=0, output=0)}),
        usage_logger=UsageLogger(tmp_path / "usage.jsonl"),
        roles={
            "classifier": RoleSettings(
                model="m", max_tokens=64, think=False, options={"num_ctx": 4096}
            )
        },
    )


def answer(causa: str = "produto_defeituoso_ou_danificado") -> str:
    return json.dumps(
        {"justificativa": "quebrou", "causa": causa, "gravidade": "media", "confianca": 0.9}
    )


def test_prompt_lists_every_class_and_input_has_only_score_title_message() -> None:
    prompt = load_prompt()
    assert all(c in prompt for c in CAUSES)
    assert "atraso_entrega" not in prompt and "nao_recebido" not in prompt  # classes da v1
    assert user_message(REVIEW) == "Nota: 2 de 5\nTítulo: (sem título)\nMensagem: Chegou quebrado."
    assert list(Classification.model_json_schema()["properties"]) == [
        "justificativa",
        "causa",
        "gravidade",
        "confianca",
    ]


def test_test_split_is_blocked_and_sampling_is_fixed() -> None:
    sample = pd.DataFrame(
        {
            "review_id": [f"d{i}" for i in range(10)] + ["t0", "t1"],
            "split": ["dev"] * 10 + ["test"] * 2,
            "position": list(range(12, 0, -1)),
        }
    )
    with pytest.raises(SystemExit, match="test set"):
        select_ids(sample, "test", None, 42)
    every = select_ids(sample, "dev", None, 42)
    assert every == [f"d{i}" for i in range(9, -1, -1)]  # ordem de apresentação
    five = select_ids(sample, "dev", 5, 42)
    assert five == select_ids(sample, "dev", 5, 42) and len(set(five)) == 5
    assert set(five) <= set(every)


def test_run_records_prediction_area_and_usage_without_text(tmp_path: Path) -> None:
    client = client_with(tmp_path, [answer()])
    df = run(client, [REVIEW], role="classifier", system=load_prompt(), split="dev")
    row = df.iloc[0]
    assert row["causa"] == "produto_defeituoso_ou_danificado" and row["area"] == "vendedor"
    assert row["schema_ok"] and row["attempts"] == 1 and not row["cached"]
    assert "justificativa" not in df.columns and "quebrado" not in df.to_csv()
    log = (tmp_path / "usage.jsonl").read_text(encoding="utf-8").splitlines()
    assert len(log) == 1 and json.loads(log[0])["tag"] == "classifier_v1"
    # repetição: cache hit, sem nova chamada
    again = run(client, [REVIEW], role="classifier", system=load_prompt(), split="dev")
    assert again.iloc[0]["cached"]


def test_invalid_output_twice_is_flagged_for_review(tmp_path: Path) -> None:
    client = client_with(tmp_path, ['{"causa": "atraso_entrega"}', "não é json"])
    df = run(client, [REVIEW], role="classifier", system=load_prompt(), split="dev")
    row = df.iloc[0]
    assert not row["schema_ok"] and row["attempts"] == 2 and row["causa"] == ""
    lines = estimate(df, 100, 4096)
    assert any("schema válido: 0/1" in line for line in lines)
    assert any("estimativa para 100 itens" in line for line in lines)


def test_batch_resumes_and_never_labels_high_scores(tmp_path: Path) -> None:
    import src.classifier.batch as batch

    comments = pd.DataFrame(
        {
            "review_id": [f"r{i}" for i in range(5)],
            "review_score": [1, 5, 3, 4, 2],
            "answered_week": ["2017-01-02"] * 5,
            "comment_title": [None] * 5,
            "comment_message": ["quebrou", "ótimo", "ok", "bom", "atrasou"],
        }
    )
    path = tmp_path / "lote.csv"
    client = client_with(tmp_path, [answer()])
    batch.append_rows(path, [batch.not_classified_row(next(comments.iloc[[1]].itertuples()))])
    n = batch.run_batch(client, comments, path, load_prompt())
    assert n == 4  # r1 já estava gravado
    out = pd.read_csv(path, keep_default_na=False).set_index("review_id")
    assert out.loc[["r1", "r3"], "status"].tolist() == ["nao_classificado"] * 2
    assert (out.loc[["r1", "r3"], "causa"] == "").all()  # nunca elogio por omissão
    assert (out.loc[["r0", "r2", "r4"], "status"] == "classificado").all()
    assert len(client.provider.calls) == 3  # type: ignore[attr-defined]  # só notas ≤ 3
    assert batch.run_batch(client, comments, path, load_prompt()) == 0  # retomada: nada a fazer
    assert len(client.provider.calls) == 3  # type: ignore[attr-defined]
