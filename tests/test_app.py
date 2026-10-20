"""Painel (Fase 9) com dados sintéticos: replay sem futuro, selos e renderização."""

from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest
from streamlit.testing.v1 import AppTest

from src.app.data import badge, load, replay, synthetic, visible_briefings
from src.config import PROJECT_ROOT


def test_replay_hides_the_future() -> None:
    d = synthetic()
    w = pd.Timestamp("2017-09-04")
    assert (pd.to_datetime(replay(d.alerts, w)["week"]) <= w).all()
    assert len(replay(d.scores, w)) < len(d.scores)
    assert all(pd.Timestamp(b["alerta"]["week"]) <= w for b in visible_briefings(d.briefings, w))


def test_badges_and_synthetic_flag(tmp_path: Path) -> None:
    assert badge("verificada").startswith("✅") and badge("divergente").startswith("❌")
    assert "não verificável" in badge("erro")
    d = load(tmp_path)  # sem arquivos do backtest: sintético, e marcado como tal
    assert d.synthetic and all("[SINTÉTICO]" in b["resumo"] for b in d.briefings)
    assert synthetic().alerts.equals(synthetic().alerts)  # determinístico


@pytest.fixture
def app(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> AppTest:
    monkeypatch.setenv("RADAR_REPORTS_DIR", str(tmp_path))
    at = AppTest.from_file(str(PROJECT_ROOT / "src" / "app" / "painel.py"), default_timeout=60)
    at.run()
    assert not at.exception
    return at


def test_panel_renders_with_synthetic_warning(app: AppTest) -> None:
    assert any("Dados sintéticos" in w.value for w in app.warning)
    assert len(app.tabs) == 2
    assert any("Afirmações verificadas" in m.value for m in app.markdown)
