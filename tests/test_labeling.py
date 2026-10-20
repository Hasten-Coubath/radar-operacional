"""Testes da Fase 2: amostra/divisão do gold set, armazenamento dos rótulos e a ferramenta."""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pandas as pd
import pytest
from pydantic import ValidationError
from streamlit.testing.v1 import AppTest

from src.config import PROJECT_ROOT
from src.labeling.gold import SAMPLE_FILE, build_gold_sample
from src.labeling.store import Label, LabelStore
from src.taxonomy import AMBIGUOUS, AREA_BY_CAUSE, CAUSES, taxonomy_sections


def make_db(path: Path, per_score: int = 30) -> sqlite3.Connection:
    con = sqlite3.connect(path)
    con.execute(
        "CREATE TABLE reviews (review_id TEXT PRIMARY KEY, review_score INT, has_comment INT, "
        "comment_title TEXT, comment_message TEXT)"
    )
    rows: list[tuple[str, int, int, str | None, str | None]] = []
    for s in range(1, 6):
        for i in range(per_score):
            rows.append((f"r{s}_{i:02d}", s, 1, None, f"texto {s}-{i}"))
        rows.append((f"sem_{s}", s, 0, None, None))
    con.executemany("INSERT INTO reviews VALUES (?, ?, ?, ?, ?)", rows)
    con.commit()
    return con


# --- amostra e divisão ---


def test_gold_sample_is_stratified_split_and_excludes_ids(tmp_path: Path) -> None:
    con = make_db(tmp_path / "r.db")
    exclude = {f"r1_{i:02d}" for i in range(15)}
    a = build_gold_sample(con, seed=42, exclude_ids=exclude, per_score=10, dev_per_score=4)
    counts = a.groupby(["split", "review_score"]).size().unstack()
    assert counts.loc["dev"].tolist() == [4] * 5 and counts.loc["test"].tolist() == [6] * 5
    assert not set(a["review_id"]) & exclude
    assert not a["review_id"].str.startswith("sem_").any()  # só avaliações com comentário
    assert sorted(a["position"]) == list(range(1, 51))
    # dev e test embaralhados juntos na ordem de apresentação
    assert a["split"].iloc[:25].nunique() == 2
    b = build_gold_sample(con, seed=42, exclude_ids=exclude, per_score=10, dev_per_score=4)
    pd.testing.assert_frame_equal(a, b)
    c = build_gold_sample(con, seed=7, exclude_ids=exclude, per_score=10, dev_per_score=4)
    assert set(c["review_id"]) != set(a["review_id"])


# --- rótulos ---


def test_label_store_roundtrip_update_and_order(tmp_path: Path) -> None:
    store = LabelStore(tmp_path)
    order = ["r3", "r1", "r2"]
    store.save(Label(review_id="r1", causa="elogio"), order)
    store.save(
        Label(
            review_id="r3",
            causa="atraso_entrega",
            causa_secundaria="problema_atendimento_ou_comunicacao",
            menciona_atraso=True,
            nota_livre='vírgula, "aspas"\ne quebra',
        ),
        order,
    )
    store.save(Label(review_id="r1", causa=AMBIGUOUS, pede_reembolso_troca=True), order)
    labels = store.load()
    assert set(labels) == {"r1", "r3"}
    assert labels["r1"].causa == AMBIGUOUS and labels["r1"].pede_reembolso_troca
    assert labels["r3"].menciona_atraso and labels["r3"].nota_livre == 'vírgula, "aspas"\ne quebra'
    assert labels["r3"].causa_secundaria == "problema_atendimento_ou_comunicacao"
    assert labels["r1"].updated_at != ""
    ids = pd.read_csv(store.path)["review_id"].tolist()
    assert ids == ["r3", "r1"]  # ordem de apresentação
    assert b"\r\n" not in store.path.read_bytes().split(b"\n", 1)[0] + b"\n"
    assert not list(tmp_path.glob("*.tmp"))


@pytest.mark.parametrize(
    "bad",
    [
        {"causa": "inexistente"},
        {"causa": "elogio", "causa_secundaria": "elogio"},
        {"causa": "elogio", "causa_secundaria": AMBIGUOUS},
        {"causa": "elogio", "nota_livre": "x" * 201},
    ],
)
def test_invalid_labels_are_rejected(bad: dict[str, str]) -> None:
    with pytest.raises(ValidationError):
        Label(review_id="r", **bad)  # type: ignore[arg-type]


# --- taxonomia ---


def test_taxonomy_docs_have_every_class_and_area_mapping_is_complete() -> None:
    sections = taxonomy_sections(PROJECT_ROOT / "docs" / "taxonomia.md")
    assert set(sections) == {*CAUSES, "Regras gerais"}
    assert all("Exemplos" in sections[c] for c in CAUSES)
    assert set(AREA_BY_CAUSE) == {*CAUSES, AMBIGUOUS}


# --- ferramenta (Streamlit sem navegador) ---


@pytest.fixture
def app(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> AppTest:
    con = make_db(tmp_path / "radar.db", per_score=3)
    gold = tmp_path / "gold"
    gold.mkdir()
    build_gold_sample(con, seed=42, exclude_ids=set(), per_score=2, dev_per_score=1).to_csv(
        gold / SAMPLE_FILE, index=False
    )
    monkeypatch.setenv("RADAR_DB_PATH", str(tmp_path / "radar.db"))
    monkeypatch.setenv("RADAR_GOLD_DIR", str(gold))
    at = AppTest.from_file(str(PROJECT_ROOT / "src" / "labeling" / "app.py"), default_timeout=60)
    at.run()
    assert not at.exception
    return at


def test_app_saves_label_and_allows_going_back(app: AppTest, tmp_path: Path) -> None:
    store = LabelStore(tmp_path / "gold")
    assert app.session_state["idx"] == 0

    app.button(key="save").click().run()  # sem causa: não salva
    assert app.error and not store.path.exists()

    app.button(key="cause_produto_defeituoso_ou_danificado").click().run()
    app.button(key="sec_pedido_incompleto_ou_errado").click().run()
    app.button(key="flag_pede_reembolso_troca").click().run()
    app.text_input(key="nota").input("caixa amassada").run()
    app.button(key="save").click().run()
    assert app.session_state["idx"] == 1

    labels = store.load()
    assert len(labels) == 1
    (label,) = labels.values()
    assert label.causa == "produto_defeituoso_ou_danificado"
    assert label.causa_secundaria == "pedido_incompleto_ou_errado"
    assert label.pede_reembolso_troca and not label.menciona_atraso
    assert label.nota_livre == "caixa amassada"

    app.button(key="prev").click().run()  # volta e carrega o rótulo salvo para corrigir
    assert app.session_state["draft"]["causa"] == "produto_defeituoso_ou_danificado"
    assert app.session_state["nota"] == "caixa amassada"
    app.button(key=f"cause_{AMBIGUOUS}").click().run()
    app.button(key="save").click().run()
    assert next(iter(store.load().values())).causa == AMBIGUOUS


def test_app_shows_only_text_title_and_score(app: AppTest) -> None:
    shown = " ".join(m.value for m in app.main.markdown)  # a lateral é a taxonomia
    assert "Nota:" in shown and "texto" in shown
    for hidden in ("atraso_dias", "delay", "is_late", "order_status", "entregue"):
        assert hidden not in shown
    assert len(app.sidebar.expander) == len(CAUSES) + 2  # regras + classes + atalhos


# --- relatório ---


def test_report_reweights_by_population_score_share() -> None:
    from src.labeling.report import class_table, score_weights

    sample = pd.DataFrame({"review_score": [1, 1, 5, 5], "split": ["dev", "test", "dev", "test"]})
    weights = score_weights(sample, pd.Series({1: 0.2, 5: 0.8}))
    assert weights.to_dict() == pytest.approx({1: 0.4, 5: 1.6})

    df = sample.assign(causa=["atraso_entrega", "atraso_entrega", "elogio", AMBIGUOUS])
    t = class_table(df, weights).set_index("classe")
    assert t.loc["atraso_entrega", ["dev", "test", "total"]].tolist() == [1, 1, 2]
    assert t.loc[AMBIGUOUS, "total"] == 1 and t.loc[AMBIGUOUS, "% reponderado"] == ""
    # sem ambíguos: 2 × 0,4 (atraso) contra 1 × 1,6 (elogio)
    assert t.loc["atraso_entrega", "% reponderado"] == "33.3%"
    assert t.loc["elogio", "% reponderado"] == "66.7%"
    assert t.loc["atraso_entrega", "área (D-027)"] == "logistica"


def test_report_ambiguity_rate_overall_and_by_split() -> None:
    from src.labeling.report import ambiguity_line

    df = pd.DataFrame(
        {"split": ["dev", "dev", "test", "test"], "causa": [AMBIGUOUS, "elogio", "elogio", "outro"]}
    )
    assert ambiguity_line(df) == "1 de 4 (25.0%); dev 1/2 (50.0%); test 0/2 (0.0%)"


def test_report_secondary_notes_and_consistency() -> None:
    from src.labeling.report import consistency_table, notes_table, secondary_table

    df = pd.DataFrame(
        {
            "split": ["dev", "test", "test", "dev"],
            "causa": ["atraso_entrega", "outro", "outro", "nao_recebido"],
            "causa_secundaria": [None, None, "elogio", "problema_atendimento_ou_comunicacao"],
            "menciona_atraso": [False, False, False, True],
            "pede_reembolso_troca": [False, False, False, False],
            "nota_livre": ["", " Qualidade ruim", "qualidade ruim", ""],
        }
    )
    text = pd.Series(["está demorando", "não atrasou", "quero o estorno", "não chegou"])
    sec = secondary_table(df).set_index("causa_secundaria")
    assert sec["total"].to_dict() == {"elogio": 1, "problema_atendimento_ou_comunicacao": 1}
    notes = notes_table(df)
    assert notes[["nota", "causa", "dev", "test", "total"]].values.tolist() == [
        ["qualidade ruim", "outro", 0, 2, 2]
    ]
    c = consistency_table(df, text).set_index("verificação")["total"].tolist()
    # atraso sem flag; termo de atraso sem flag (inclui o falso positivo "não atrasou");
    # termo de reembolso sem flag; elogio como secundária
    assert c == [1, 2, 1, 1]
