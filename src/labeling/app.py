"""Ferramenta de rotulagem manual do gold set (Fase 2).

Uso: `streamlit run src/labeling/app.py`. Mostra só título, mensagem e nota da avaliação; o sinal
objetivo de atraso e os dados do pedido ficam escondidos para não enviesar o rótulo. Cada
"salvar" grava `data/gold/labels.csv` na hora. Nenhum LLM é chamado aqui.
"""

from __future__ import annotations

import re
import sqlite3
import sys
from pathlib import Path
from typing import Any

import pandas as pd
import streamlit as st

# `streamlit run` executa este arquivo como script: garante que o pacote `src` seja importável
ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.config import load_config, resolve_path  # noqa: E402
from src.labeling.gold import SAMPLE_FILE, load_gold_sample  # noqa: E402
from src.labeling.store import MAX_NOTE_CHARS, Label, LabelStore  # noqa: E402
from src.taxonomy import AMBIGUOUS, CAUSES, TAXONOMY_VERSION, taxonomy_sections  # noqa: E402

CAUSE_KEYS = {c: str(i) for i, c in enumerate(CAUSES, 1)}  # 1..8
AMBIGUOUS_KEY = "9"
CAUSE_LABELS = {c: c.replace("_", " ") for c in CAUSES} | {AMBIGUOUS: "ambíguo / não sei"}
_MD_SPECIAL = re.compile(r"([\\`*_{}\[\]()#+\-.!|<>~$])")

SHORTCUTS_HELP = """
| Tecla | Ação |
|---|---|
| `1`–`8` | causa principal |
| `9` | ambíguo / não sei |
| `Alt+1`–`Alt+8` | causa secundária (liga/desliga) |
| `Alt+0` | limpa a causa secundária |
| `A` | menciona atraso |
| `E` | pede reembolso / troca |
| `S` | salvar e ir ao próximo |
| `←` / `→` | anterior / próximo (sem salvar) |
| `N` | próximo não rotulado |

Dentro do campo de nota as teclas digitam texto: clique fora dele antes de usar os atalhos.
"""


def escape_md(text: str) -> str:
    return _MD_SPECIAL.sub(r"\\\1", text).replace("\n", "  \n")


@st.cache_data
def load_texts(db_path: str, ids: tuple[str, ...]) -> pd.DataFrame:
    """Nota, título e mensagem: tudo o que quem rotula pode ver."""
    con = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    try:
        df = pd.read_sql(
            "SELECT review_id, review_score, comment_title, comment_message FROM reviews "
            f"WHERE review_id IN ({','.join('?' * len(ids))})",
            con,
            params=list(ids),
        )
    finally:
        con.close()
    return df.set_index("review_id")


def empty_draft() -> dict[str, Any]:
    return {
        "causa": None,
        "causa_secundaria": None,
        "menciona_atraso": False,
        "pede_reembolso_troca": False,
    }


class LabelingApp:
    def __init__(self) -> None:
        cfg = load_config()
        self.gold_dir = resolve_path(cfg["paths"]["gold_dir"])
        self.db_path = resolve_path(cfg["paths"]["db_path"])
        self.docs = resolve_path("docs/taxonomia.md")
        self.store = LabelStore(self.gold_dir)
        self.sample = load_gold_sample(self.gold_dir)
        self.ids: list[str] = list(self.sample["review_id"])
        self.labels = self.store.load()
        self.state = st.session_state
        if "idx" not in self.state:
            self.load_item(self.first_unlabeled())

    # --- estado ---

    def first_unlabeled(self, start: int = 0) -> int:
        n = len(self.ids)
        for k in range(n):
            i = (start + k) % n
            if self.ids[i] not in self.labels:
                return i
        return start % n

    def load_item(self, i: int) -> None:
        i = max(0, min(i, len(self.ids) - 1))
        self.state["idx"] = i
        saved = self.store.load().get(self.ids[i])
        draft = empty_draft()
        if saved is not None:
            draft.update(saved.model_dump(include=set(draft)))
        self.state["draft"] = draft
        self.state["nota"] = saved.nota_livre if saved else ""
        self.state["goto"] = i + 1
        self.state.pop("error", None)

    @property
    def draft(self) -> dict[str, Any]:
        d: dict[str, Any] = self.state["draft"]
        return d

    # --- callbacks ---

    def set_cause(self, cause: str) -> None:
        self.draft["causa"] = cause
        if self.draft["causa_secundaria"] == cause:
            self.draft["causa_secundaria"] = None

    def toggle_secondary(self, cause: str | None) -> None:
        current = self.draft["causa_secundaria"]
        if cause is None or cause == current or cause == self.draft["causa"]:
            self.draft["causa_secundaria"] = None
        else:
            self.draft["causa_secundaria"] = cause

    def toggle(self, flag: str) -> None:
        self.draft[flag] = not self.draft[flag]

    def save_and_next(self) -> None:
        if self.draft["causa"] is None:
            self.state["error"] = "Escolha a causa principal (1–9) antes de salvar."
            return
        idx = self.state["idx"]
        label = Label(review_id=self.ids[idx], nota_livre=self.state.get("nota", ""), **self.draft)
        self.store.save(label, order=self.ids)
        self.state["saved_msg"] = f"Item {idx + 1} salvo."
        self.load_item(idx + 1)

    def go(self, delta: int) -> None:
        self.load_item(self.state["idx"] + delta)

    def go_next_unlabeled(self) -> None:
        self.labels = self.store.load()
        self.load_item(self.first_unlabeled(self.state["idx"] + 1))

    def go_to(self) -> None:
        self.load_item(int(self.state["goto"]) - 1)

    # --- tela ---

    def render(self) -> None:
        st.set_page_config(page_title="Rotulagem do gold set", layout="wide")
        self.render_sidebar()
        idx = self.state["idx"]
        rid = self.ids[idx]
        row = load_texts(str(self.db_path), tuple(self.ids)).loc[rid]
        done = sum(1 for i in self.ids if i in self.labels)

        st.progress(done / len(self.ids), text=f"{done} de {len(self.ids)} rotulados")
        if msg := self.state.pop("saved_msg", None):
            st.toast(msg)
        status = "✅ rotulado" if rid in self.labels else "○ não rotulado"
        st.markdown(f"#### Item {idx + 1} de {len(self.ids)} · {status}")

        with st.container(border=True):
            score = int(row["review_score"])
            st.markdown(f"**Nota:** {'★' * score}{'☆' * (5 - score)} ({score})")
            if isinstance(row["comment_title"], str):
                st.markdown(f"**Título:** {escape_md(row['comment_title'])}")
            st.markdown(escape_md(str(row["comment_message"])))
            st.caption(f"review_id {rid}")

        self.render_cause_buttons()
        self.render_secondary_and_flags()
        st.text_input("Nota livre (opcional)", key="nota", max_chars=MAX_NOTE_CHARS)
        if err := self.state.get("error"):
            st.error(err)
        self.render_navigation()

    def render_cause_buttons(self) -> None:
        st.markdown("**Causa principal**")
        options = [*CAUSES, AMBIGUOUS]
        for row_start in (0, 3, 6):
            cols = st.columns(3)
            for col, cause in zip(cols, options[row_start : row_start + 3], strict=False):
                key = CAUSE_KEYS.get(cause, AMBIGUOUS_KEY)
                col.button(
                    f"{key} · {CAUSE_LABELS[cause]}",
                    key=f"cause_{cause}",
                    shortcut=key,
                    type="primary" if self.draft["causa"] == cause else "secondary",
                    on_click=self.set_cause,
                    args=(cause,),
                    width="stretch",
                )

    def render_secondary_and_flags(self) -> None:
        with st.expander(
            f"Causa secundária (opcional): **{self.draft['causa_secundaria'] or 'nenhuma'}**",
            expanded=self.draft["causa_secundaria"] is not None,
        ):
            cols = st.columns(4)
            for i, cause in enumerate(CAUSES):
                cols[i % 4].button(
                    f"Alt+{CAUSE_KEYS[cause]} · {CAUSE_LABELS[cause]}",
                    key=f"sec_{cause}",
                    shortcut=f"Alt+{CAUSE_KEYS[cause]}",
                    type="primary" if self.draft["causa_secundaria"] == cause else "secondary",
                    on_click=self.toggle_secondary,
                    args=(cause,),
                    width="stretch",
                )
            st.button(
                "Alt+0 · limpar",
                key="sec_none",
                shortcut="Alt+0",
                on_click=self.toggle_secondary,
                args=(None,),
            )
        c1, c2 = st.columns(2)
        for col, flag, key, text in (
            (c1, "menciona_atraso", "A", "menciona atraso"),
            (c2, "pede_reembolso_troca", "E", "pede reembolso / troca"),
        ):
            on = self.draft[flag]
            col.button(
                f"{key} · {text}: {'SIM' if on else 'não'}",
                key=f"flag_{flag}",
                shortcut=key,
                type="primary" if on else "secondary",
                on_click=self.toggle,
                args=(flag,),
                width="stretch",
            )

    def render_navigation(self) -> None:
        c1, c2, c3, c4, c5 = st.columns([1, 2, 1, 1.4, 1])
        c1.button("← anterior", key="prev", shortcut="Left", on_click=self.go, args=(-1,))
        c2.button(
            "S · salvar e próximo",
            key="save",
            shortcut="S",
            type="primary",
            on_click=self.save_and_next,
            width="stretch",
        )
        c3.button("próximo →", key="next", shortcut="Right", on_click=self.go, args=(1,))
        c4.button(
            "N · próximo não rotulado",
            key="next_unlabeled",
            shortcut="N",
            on_click=self.go_next_unlabeled,
        )
        c5.number_input(
            "ir para item",
            min_value=1,
            max_value=len(self.ids),
            key="goto",
            on_change=self.go_to,
            label_visibility="collapsed",
        )

    def render_sidebar(self) -> None:
        sections = taxonomy_sections(self.docs)
        with st.sidebar:
            st.markdown(f"### Taxonomia {TAXONOMY_VERSION}")
            with st.expander("Regras gerais"):
                st.markdown(sections.get("Regras gerais", "_não encontrada em docs_"))
            for cause in CAUSES:
                with st.expander(f"{CAUSE_KEYS[cause]} · {cause}"):
                    st.markdown(sections.get(cause, "_definição não encontrada em docs_"))
            with st.expander("Atalhos de teclado"):
                st.markdown(SHORTCUTS_HELP)


def main() -> None:
    try:
        app = LabelingApp()
    except FileNotFoundError as e:
        st.error(
            f"Arquivo não encontrado: {e.filename}. Gere a amostra com "
            f"`python -m src.labeling.gold` (cria data/gold/{SAMPLE_FILE})."
        )
        return
    app.render()


main()
