"""Figura da curva recall × falsos alarmes (Fase 7), a partir dos CSVs do backtest.

Uso: `python -m src.detection.plot_curve`. Lê `reports/curva_{calibracao,avaliacao}.csv` e
`reports/backtest_calibracao.json` e grava `reports/figures/curva_backtest.png`. Não recalcula
nada: só desenha o que o backtest gravou. O ponto cheio de cada método é o θ calibrado em 2017.
"""

from __future__ import annotations

import json
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import pandas as pd  # noqa: E402

from src.config import load_config, resolve_path  # noqa: E402
from src.detection.backtest import METHODS, THETA_FILE  # noqa: E402

COLORS = {"Radar": "#c44e52", "B1": "#4c72b0", "B2": "#55a868", "B3": "#8172b2"}
LABELS = {
    "Radar": "Radar (causas do LLM)",
    "B1": "B1 (queda da nota média)",
    "B2": "B2 (fração de notas ≤ 2)",
    "B3": "B3 (atraso, referência)",
}
PERIODS = (("calibracao", "Calibração (2017)"), ("avaliacao", "Avaliação (2018)"))
X_MAX = 3.0


def plot(reports: Path, out: Path) -> None:
    thetas = json.loads((reports / THETA_FILE).read_text(encoding="utf-8"))
    fig, axes = plt.subplots(1, 2, figsize=(11, 4.2), sharey=True)
    for ax, (period, title) in zip(axes, PERIODS, strict=True):
        c = pd.read_csv(reports / f"curva_{period}.csv")
        n_a = int(c["n_A"].iloc[0])
        for m in METHODS:
            # em ordem de FA/semana: o recall possível com até x falsos alarmes por semana
            s = c[c["método"] == m].sort_values(["fa_por_semana", "recall_A"])
            ax.step(
                s["fa_por_semana"], s["recall_A"], where="post", color=COLORS[m], label=LABELS[m]
            )
            sel = s[s["theta"] == thetas[m]]
            ax.plot(sel["fa_por_semana"], sel["recall_A"], "o", color=COLORS[m], ms=7)
        ax.axvline(1.0, color="grey", ls=":", lw=1)
        ax.set_xlim(0, X_MAX)
        ax.set_ylim(0, 1.03)
        ax.set_xlabel("falsos alarmes por semana")
        ax.set_title(f"{title}: {n_a} incidentes de entrega (tipo A)")
        ax.grid(alpha=0.3)
    axes[0].set_ylabel("recall dos incidentes tipo A")
    axes[1].legend(loc="lower right", fontsize=8)
    fig.suptitle("Recall × falsos alarmes na grade de θ (ponto cheio = θ calibrado em 2017)")
    fig.tight_layout()
    out.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out, dpi=110)
    plt.close(fig)


def main() -> None:
    reports = Path(resolve_path(load_config()["paths"]["reports_dir"]))
    out = reports / "figures" / "curva_backtest.png"
    plot(reports, out)
    print(f"Figura gravada em {out}")


if __name__ == "__main__":
    main()
