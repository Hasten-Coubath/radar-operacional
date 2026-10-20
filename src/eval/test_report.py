"""Relatório da Fase 5: avaliação única no test set (D-045).

Uso: `python -m src.eval.test_report`. Mesmas métricas do dev (`src.eval.dev_report`). O
baseline foi ajustado nos não ambíguos do dev inteiro; o LLM é a configuração escolhida na Fase 4
(prompt v1, sem raciocínio). Nada é ajustado depois deste relatório.
"""

from __future__ import annotations

from src.eval.dev_report import Method, write_report

TEST_METHODS = (
    Method("baseline TF-IDF+LR (ajustado no dev)", "baseline_v1_test.csv"),
    Method("LLM v1 sem raciocínio", "classifier_v1_test.csv"),
    Method("LLM v1 com raciocínio (comparação, depois do lote)", "classifier_think_v1_test.csv"),
)


def main() -> None:
    write_report(
        split="test",
        methods=TEST_METHODS,
        title="# Fase 5: avaliação final no test set",
        filename="fase5_test.md",
        errors_of=None,
        intro=(
            "- **Avaliação única** (D-045): configuração escolhida no dev (Fase 4: prompt v1, sem "
            "raciocínio, sem limiar de confiança) e baseline ajustado nos 96 itens não ambíguos "
            "do dev. Nenhum ajuste depois deste relatório.",
            "- Sem métrica secundária: as anotações de D-041 são do dev.",
        ),
    )


if __name__ == "__main__":
    main()
