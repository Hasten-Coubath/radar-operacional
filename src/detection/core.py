"""Núcleo do detector e do backtest, sem banco de dados (D-026, D-043, D-047, D-048).

Tabelas semanais têm uma linha por (segment_type, segment_value, week), com `week` como
`pd.Timestamp` (segunda-feira) e todas as semanas presentes em cada segmento. Tudo é
point-in-time: a referência da semana t só usa as semanas t − 26 a t − 1.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence

import numpy as np
import pandas as pd

KEYS = ["segment_type", "segment_value"]
WINDOW = 26
MIN_REF_WEEKS = 8
Z = 1.96
REL_FACTOR = 2.0
ABS_MARGIN = 0.05
MATCH_BEFORE = 4  # alerta casa com incidente em [início − 4, fim]
FA_AFTER = 2  # alerta não é falso se cair em [início − 4, fim + 2] de algum incidente
WEEK = pd.Timedelta(days=7)
THETA_GRID = np.round(np.arange(0.5, 8.0001, 0.25), 2)
FA_BUDGET_PER_WEEK = 1.0


def week_range(start: str, end: str) -> pd.DatetimeIndex:
    return pd.date_range(start, end, freq="7D")


def complete(df: pd.DataFrame, weeks: pd.DatetimeIndex, fill: Mapping[str, float]) -> pd.DataFrame:
    """Garante todas as semanas em cada segmento (semanas ausentes recebem `fill`)."""
    segs = df[KEYS].drop_duplicates()
    grid = segs.merge(pd.DataFrame({"week": weeks}), how="cross")
    out = grid.merge(df, on=[*KEYS, "week"], how="left")
    return out.fillna(fill).sort_values([*KEYS, "week"]).reset_index(drop=True)


def wilson_lower(p: np.ndarray | pd.Series, n: np.ndarray | pd.Series, z: float = Z) -> np.ndarray:
    """Limite inferior do intervalo de Wilson (D-026). n = 0 → NaN."""
    p_arr = np.asarray(p, dtype=float)
    n_arr = np.asarray(n, dtype=float)
    with np.errstate(divide="ignore", invalid="ignore"):
        center = p_arr + z**2 / (2 * n_arr)
        half = z * np.sqrt(p_arr * (1 - p_arr) / n_arr + z**2 / (4 * n_arr**2))
        out = (center - half) / (1 + z**2 / n_arr)
    return np.where(n_arr > 0, out, np.nan)


def past_median(df: pd.DataFrame, value: str, n: str, n_min: int) -> pd.Series:
    """Mediana de `value` nas 26 semanas anteriores com `n` ≥ n_min (mínimo 8), por segmento."""
    v = df[value].where(df[n] >= n_min)
    return v.groupby([df[k] for k in KEYS]).transform(
        lambda s: s.shift(1).rolling(WINDOW, min_periods=MIN_REF_WEEKS).median()
    )


def anomalous_weeks(df: pd.DataFrame, k: str, n: str, n_min: int) -> pd.DataFrame:
    """Semanas anômalas de uma série de proporção k/n (D-026). Acrescenta p, ref, lower, anom."""
    out = df.copy()
    out["p"] = (out[k] / out[n]).where(out[n] > 0)
    out["ref"] = past_median(out, "p", n, n_min)
    out["lower"] = wilson_lower(out["p"].fillna(0), out[n])
    limit = np.maximum(REL_FACTOR * out["ref"], out["ref"] + ABS_MARGIN)
    out["anom"] = (
        (out[n] >= n_min) & out["ref"].notna() & (out["p"] > limit) & (out["lower"] > out["ref"])
    )
    return out


def runs_to_incidents(
    weeks: Sequence[pd.Timestamp], flags: Sequence[bool]
) -> list[tuple[pd.Timestamp, pd.Timestamp]]:
    """Regra de junção (D-026, interpretação de D-048) numa série semanal completa e ordenada.

    Une sequências anômalas separadas por uma única semana não anômala; um bloco vira incidente
    se tiver ≥ 2 semanas anômalas consecutivas. Devolve (início, fim) = 1ª e última anômalas.
    """
    idx = [i for i, f in enumerate(flags) if f]
    blocks: list[list[int]] = []
    for i in idx:
        if blocks and i - blocks[-1][-1] <= 2:  # gap de no máximo 1 semana
            blocks[-1].append(i)
        else:
            blocks.append([i])
    out = []
    for b in blocks:
        if any(b[j + 1] - b[j] == 1 for j in range(len(b) - 1)):
            out.append((weeks[b[0]], weeks[b[-1]]))
    return out


def incidents(table: pd.DataFrame, kind: str) -> pd.DataFrame:
    """Incidentes por segmento a partir da coluna `anom` de `anomalous_weeks`."""
    rows = []
    for key, g in table.sort_values("week").groupby(KEYS, sort=True):
        for start, end in runs_to_incidents(list(g["week"]), list(g["anom"])):
            rows.append(
                {
                    "segment_type": key[0],
                    "segment_value": key[1],
                    "tipo": kind,
                    "start": start,
                    "end": end,
                }
            )
    return pd.DataFrame(rows, columns=[*KEYS, "tipo", "start", "end"])


def proportion_score(k: pd.Series, n: pd.Series, ref: pd.Series, n_min: int) -> pd.Series:
    """(p − b) / √(b′(1 − b′)/n), b′ = max(b, 1/n). NaN sem volume ou sem referência (D-048)."""
    p = k / n.where(n > 0)
    b2 = np.maximum(ref, 1 / n.where(n > 0))
    se = np.sqrt(b2 * (1 - b2) / n)
    return ((p - ref) / se).where((n >= n_min) & ref.notna())


def proportion_signal(df: pd.DataFrame, k: str, n: str, n_min: int) -> pd.Series:
    t = df.assign(_p=(df[k] / df[n]).where(df[n] > 0))
    ref = past_median(t, "_p", n, n_min)
    return proportion_score(df[k], df[n], ref, n_min)


def mean_drop_signal(df: pd.DataFrame, n: str, s: str, ss: str, n_min: int) -> pd.Series:
    """B1: (b − m) / (sd/√n). `s` e `ss` são soma e soma dos quadrados das notas da semana."""
    t = df.assign(_m=(df[s] / df[n]).where(df[n] > 0))
    ref = past_median(t, "_m", n, n_min)
    grp = [t[k] for k in KEYS]

    def past_sum(col: str) -> pd.Series:
        return (
            t[col].groupby(grp).transform(lambda x: x.shift(1).rolling(WINDOW, min_periods=1).sum())
        )

    pn, ps, pss = past_sum(n), past_sum(s), past_sum(ss)
    var = (pss - ps**2 / pn) / (pn - 1)
    sd = np.sqrt(var.where(pn > 1))
    score = (ref - t["_m"]) / (sd / np.sqrt(t[n]))
    return score.where((t[n] >= n_min) & ref.notna() & (sd > 0))


def alerts(scores: pd.DataFrame, theta: float, weeks: pd.DatetimeIndex) -> pd.DataFrame:
    """Linhas com escore > θ dentro de `weeks`."""
    a = scores[(scores["score"] > theta) & scores["week"].isin(weeks)]
    return a.reset_index(drop=True)


def evaluate(
    al: pd.DataFrame,
    inc_all: pd.DataFrame,
    period_weeks: pd.DatetimeIndex,
) -> tuple[pd.DataFrame, int, float]:
    """Casamento alerta × incidente (D-026).

    Devolve (incidentes do período com a semana de detecção, nº de falsos alarmes, FA/semana).
    `inc_all` tem todos os incidentes (para excluir falsos alarmes); os do período são os com
    início em `period_weeks`. `al` já deve estar restrito a `period_weeks`.
    """
    lo, hi = period_weeks.min(), period_weeks.max()
    inc = inc_all[(inc_all["start"] >= lo) & (inc_all["start"] <= hi)].copy()
    det = []
    for r in inc.itertuples(index=False):
        m = al[
            (al["segment_type"] == r.segment_type)
            & (al["segment_value"] == r.segment_value)
            & (al["week"] >= r.start - MATCH_BEFORE * WEEK)
            & (al["week"] <= r.end)
        ]
        det.append(m["week"].min() if len(m) else pd.NaT)
    inc["detected"] = det
    false = 0
    for r in al.itertuples(index=False):
        same = inc_all[
            (inc_all["segment_type"] == r.segment_type)
            & (inc_all["segment_value"] == r.segment_value)
        ]
        covered = (
            (same["start"] - MATCH_BEFORE * WEEK <= r.week)
            & (r.week <= same["end"] + FA_AFTER * WEEK)
        ).any()
        false += not covered
    return inc.reset_index(drop=True), false, false / len(period_weeks)


def calibrate(
    scores: pd.DataFrame,
    inc_all: pd.DataFrame,
    weeks: pd.DatetimeIndex,
    grid: Sequence[float] = tuple(THETA_GRID),
    budget: float = FA_BUDGET_PER_WEEK,
) -> tuple[float | None, pd.DataFrame]:
    """Menor θ com FA/semana ≤ orçamento no período; devolve também a curva recall × FA."""
    rows = []
    for theta in grid:
        inc, n_fa, fa_week = evaluate(alerts(scores, theta, weeks), inc_all, weeks)
        row: dict[str, float] = {
            "theta": float(theta),
            "falsos_alarmes": n_fa,
            "fa_por_semana": fa_week,
        }
        for kind in ("A", "B"):
            sub = inc[inc["tipo"] == kind]
            row[f"recall_{kind}"] = (
                float(sub["detected"].notna().mean()) if len(sub) else float("nan")
            )
            row[f"n_{kind}"] = len(sub)
        rows.append(row)
    curve = pd.DataFrame(rows)
    ok = curve[curve["fa_por_semana"] <= budget]
    return (float(ok["theta"].min()) if len(ok) else None), curve
