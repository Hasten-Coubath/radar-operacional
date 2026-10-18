"""Estatísticas da Fase 1 a partir do banco: gera `reports/fase1_dados.md` e figuras.

Uso: `python -m src.data.stats` (depois de `python -m src.data.make_db`). Todos os números do
relatório saem das consultas abaixo; nada é digitado à mão.
"""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import pandas as pd  # noqa: E402

from src.config import load_config, resolve_path  # noqa: E402
from src.data.point_in_time import load_orders, weekly_due_late_rate  # noqa: E402

MIN_WEEKLY_COMMENTS = 100  # semanas com menos avaliações com comentário ficam fora da janela
# O dataset só contém pedidos cuja pesquisa foi enviada até a última `review_creation_date`;
# pedidos atrasados entregues depois disso não aparecem. A taxa de atraso só é analisada até
# esta margem antes do corte (79% dos atrasos têm até 14 dias; ver seção 6).
LATE_CENSOR_MARGIN_DAYS = 14
COVERAGE_THRESHOLDS = (1, 2, 5, 10, 20)
# Janelas dos eventos vistos na exploração (seção 9), usadas só para localizar picos.
EVENT_WINDOWS = {
    "dez/2017 (pós-Black Friday)": ("2017-11-27", "2018-01-22"),
    "mar–abr/2018": ("2018-02-26", "2018-05-07"),
    "fim de mai–jun/2018": ("2018-05-21", "2018-06-25"),
}
LAGS = range(-2, 4)
QUANTILES = (0.05, 0.25, 0.5, 0.75, 0.95, 0.99)


def md_table(df: pd.DataFrame, floatfmt: str = "{:.2f}") -> str:
    """DataFrame -> tabela Markdown (sem dependência de `tabulate`)."""

    def fmt(v: object) -> str:
        if isinstance(v, float):
            return "" if pd.isna(v) else floatfmt.format(v)
        return str(v)

    header = "| " + " | ".join(map(str, df.columns)) + " |"
    sep = "|" + "|".join("---" for _ in df.columns) + "|"
    rows = ["| " + " | ".join(fmt(v) for v in row) + " |" for row in df.itertuples(index=False)]
    return "\n".join([header, sep, *rows])


def pct(x: float) -> str:
    return f"{100 * x:.1f}%"


def analysis_window(con: sqlite3.Connection) -> tuple[str, str]:
    """Semanas de resposta com >= MIN_WEEKLY_COMMENTS comentários, até a última semana de envio.

    Depois da última semana com pesquisas enviadas (`created_week`), as semanas de resposta só
    contêm respostas atrasadas a pesquisas antigas: estão incompletas.
    """
    w = pd.read_sql(
        "SELECT answered_week w, SUM(has_comment) n FROM reviews GROUP BY w ORDER BY w", con
    )
    ok = w[w["n"] >= MIN_WEEKLY_COMMENTS]["w"]
    last_created = con.execute("SELECT MAX(created_week) FROM reviews").fetchone()[0]
    return str(ok.iloc[0]), min(str(ok.iloc[-1]), last_created)


def late_window_end(con: sqlite3.Connection) -> str:
    """Última semana estimada de entrega cuja taxa de atraso não está censurada pelo corte."""
    (last,) = con.execute("SELECT MAX(review_creation_date) FROM reviews").fetchone()
    cutoff = pd.Timestamp(last) - pd.Timedelta(days=LATE_CENSOR_MARGIN_DAYS)
    return str((cutoff - pd.Timedelta(days=cutoff.weekday())).date())


def segment_coverage(con: sqlite3.Connection, start: str, end: str) -> pd.DataFrame:
    """Quantos segmentos têm volume médio semanal >= k, e que fração do total eles cobrem."""
    n_weeks = len(pd.date_range(start, end, freq="7D"))
    d = pd.read_sql(
        """
        SELECT rs.segment_type, rs.segment_value,
               SUM(r.has_comment) AS com,
               SUM(r.has_comment AND r.review_score <= 2) AS neg
        FROM review_segments rs JOIN reviews r ON r.review_id = rs.review_id
        WHERE r.answered_week BETWEEN ? AND ?
        GROUP BY rs.segment_type, rs.segment_value
        """,
        con,
        params=(start, end),
    )
    rows = []
    for seg, g in d.groupby("segment_type", sort=False):
        for col, label in (("com", "com comentário"), ("neg", "com comentário e nota ≤ 2")):
            weekly = g[col] / n_weeks
            row: dict[str, object] = {
                "segmento": seg,
                "avaliações": label,
                "segmentos": len(g),
            }
            for k in COVERAGE_THRESHOLDS:
                mask = weekly >= k
                row[f"≥{k}/sem"] = (
                    f"{int(mask.sum())} ({pct(g.loc[mask, col].sum() / g[col].sum())})"
                )
            rows.append(row)
    return pd.DataFrame(rows)


def main() -> None:
    cfg = load_config()
    db_path = resolve_path(cfg["paths"]["db_path"])
    reports = resolve_path(cfg["paths"]["reports_dir"])
    figures = reports / "figures"
    figures.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)

    def q(sql: str, *params: object) -> pd.DataFrame:
        return pd.read_sql(sql, con, params=params)

    meta = dict(con.execute("SELECT key, value FROM meta").fetchall())
    checks = json.loads(meta["quality_checks"])
    counts = json.loads(meta["row_counts"])
    out: list[str] = [
        "# Fase 1 — Dados: estatísticas descritivas e exploração temporal",
        "",
        "_Gerado por `python -m src.data.stats` a partir de `data/processed/radar.db`. "
        "Não edite à mão._",
        "",
        "## 1. Tabelas do banco",
        "",
        md_table(pd.DataFrame(sorted(counts.items()), columns=["tabela", "linhas"])),
        "",
        "## 2. Checagens de qualidade (linhas mantidas, não descartadas)",
        "",
        md_table(pd.DataFrame(checks.items(), columns=["checagem", "contagem"])),
        "",
    ]

    # --- 3. avaliações e notas ---
    tot = q(
        "SELECT COUNT(*) n, SUM(has_comment) com, SUM(comment_title IS NOT NULL) tit FROM reviews"
    ).iloc[0]
    by_score = q(
        "SELECT review_score nota, COUNT(*) n, SUM(has_comment) com FROM reviews "
        "GROUP BY nota ORDER BY nota"
    )
    by_score["% do total"] = (by_score["n"] / tot["n"]).map(pct)
    by_score["% dos comentados"] = (by_score["com"] / tot["com"]).map(pct)
    by_score["% com comentário"] = (by_score["com"] / by_score["n"]).map(pct)
    by_score = by_score.rename(columns={"n": "avaliações", "com": "com comentário"})
    out += [
        "## 3. Avaliações",
        "",
        f"- Avaliações únicas (`review_id`): **{int(tot['n'])}**",
        f"- Com comentário de texto (elegíveis para classificação): **{int(tot['com'])}** "
        f"({pct(tot['com'] / tot['n'])})",
        f"- Com título: {int(tot['tit'])} ({pct(tot['tit'] / tot['n'])}); só título, sem "
        f"mensagem: {checks['title_without_message']}",
        "",
        "Distribuição de notas:",
        "",
        md_table(by_score),
        "",
    ]

    # --- 4. tamanho dos textos ---
    txt = q("SELECT review_score, comment_chars, comment_words FROM reviews WHERE has_comment = 1")
    qt = pd.DataFrame(
        {
            "quantil": [f"p{int(x * 100)}" for x in QUANTILES],
            "caracteres": [txt["comment_chars"].quantile(x) for x in QUANTILES],
            "palavras": [txt["comment_words"].quantile(x) for x in QUANTILES],
        }
    )
    med = txt.groupby("review_score")[["comment_chars", "comment_words"]].median().reset_index()
    med.columns = ["nota", "mediana de caracteres", "mediana de palavras"]
    short = (txt["comment_words"] <= 2).mean()
    out += [
        "## 4. Tamanho dos comentários",
        "",
        f"Média: {txt['comment_chars'].mean():.1f} caracteres, "
        f"{txt['comment_words'].mean():.1f} palavras. Comentários com até 2 palavras: "
        f"{pct(short)}.",
        "",
        md_table(qt, "{:.0f}"),
        "",
        md_table(med, "{:.0f}"),
        "",
    ]

    # --- 5. datas da avaliação ---
    lag = q(
        "SELECT (julianday(review_answer_ts) - julianday(review_creation_date)) d FROM reviews"
    )["d"]
    rel = q(
        """
        SELECT CAST(julianday(r.review_creation_date)
                    - julianday(date(o.delivered_customer_ts)) AS INTEGER) AS vs_entrega,
               CAST(julianday(r.review_creation_date)
                    - julianday(o.estimated_delivery_date) AS INTEGER) AS vs_estimada,
               o.delivered_customer_ts IS NULL AS sem_entrega
        FROM reviews r JOIN review_orders ro ON ro.review_id = r.review_id
        JOIN orders o ON o.order_id = ro.order_id
        """
    )
    deliv = rel[rel["sem_entrega"] == 0]
    before = deliv[deliv["vs_entrega"] < 0]
    lag_t = pd.DataFrame(
        {
            "quantil": [f"p{int(x * 100)}" for x in QUANTILES] + ["máx"],
            "dias": [lag.quantile(x) for x in QUANTILES] + [lag.max()],
        }
    )
    out += [
        "## 5. Datas da avaliação e vazamento temporal",
        "",
        "`review_creation_date` é a data em que a pesquisa foi enviada ao cliente; "
        "`review_answer_ts` é quando ele respondeu. O texto só existe a partir da resposta.",
        "",
        "Defasagem envio → resposta (dias):",
        "",
        md_table(lag_t, "{:.1f}"),
        "",
        f"- Em pares avaliação–pedido entregues, a pesquisa é enviada "
        f"{deliv['vs_entrega'].median():.0f} dia(s) após a entrega (mediana); "
        f"{pct((deliv['vs_entrega'] == 1).mean())} exatamente 1 dia depois.",
        f"- Pesquisa enviada **antes** da entrega: {len(before)} pares "
        f"({pct(len(before) / len(deliv))}); nesses, envio − data estimada tem mediana "
        f"{before['vs_estimada'].median():.0f} dia(s).",
        f"- Pares com pedido sem data de entrega: {int(rel['sem_entrega'].sum())}; "
        f"envio − data estimada tem mediana "
        f"{rel.loc[rel['sem_entrega'] == 1, 'vs_estimada'].median():.0f} dia(s).",
        "",
    ]

    # --- 6. sinal objetivo de atraso ---
    st = q(
        "SELECT order_status, COUNT(*) n, SUM(is_late IS NOT NULL) com_entrega FROM orders "
        "GROUP BY order_status ORDER BY n DESC"
    )
    dd = q("SELECT delay_days FROM orders WHERE delay_days IS NOT NULL")["delay_days"]
    late_rate = q("SELECT AVG(is_late) x FROM orders WHERE is_late IS NOT NULL").iloc[0]["x"]
    vs_score = q(
        """
        SELECT CASE WHEN o.is_late = 1 THEN 'atrasado'
                    WHEN o.is_late = 0 THEN 'no prazo'
                    ELSE 'sem data de entrega' END AS pedido,
               COUNT(*) AS avaliações,
               AVG(r.review_score) AS nota_média,
               AVG(r.review_score <= 2) AS frac_nota_le_2,
               AVG(r.has_comment) AS frac_com_comentário
        FROM reviews r JOIN review_orders ro ON ro.review_id = r.review_id
        JOIN orders o ON o.order_id = ro.order_id
        GROUP BY pedido ORDER BY pedido
        """
    )
    for c in ("frac_nota_le_2", "frac_com_comentário"):
        vs_score[c] = vs_score[c].map(pct)
    by_delay = q(
        """
        SELECT CASE WHEN o.delay_days <= 0 THEN '≤ 0'
                    WHEN o.delay_days <= 3 THEN '1–3'
                    WHEN o.delay_days <= 7 THEN '4–7'
                    WHEN o.delay_days <= 14 THEN '8–14'
                    ELSE '> 14' END AS dias_de_atraso,
               MIN(o.delay_days) AS ordem,
               COUNT(*) AS avaliações, AVG(r.review_score) AS nota_média
        FROM reviews r JOIN review_orders ro ON ro.review_id = r.review_id
        JOIN orders o ON o.order_id = ro.order_id
        WHERE o.delay_days IS NOT NULL GROUP BY dias_de_atraso ORDER BY ordem
        """
    ).drop(columns="ordem")
    dq = pd.DataFrame(
        {
            "quantil": [f"p{int(x * 100)}" for x in QUANTILES],
            "entrega − estimada (dias)": [dd.quantile(x) for x in QUANTILES],
        }
    )
    out += [
        "## 6. Sinal objetivo de atraso",
        "",
        "`delay_days` = data da entrega ao cliente − data estimada (dias de calendário); "
        "`is_late = delay_days > 0`; nulo quando não há data de entrega.",
        "",
        f"- Pedidos com data de entrega: {len(dd)}; atrasados: **{pct(late_rate)}**.",
        "",
        md_table(st.rename(columns={"n": "pedidos", "com_entrega": "com data de entrega"})),
        "",
        md_table(dq, "{:.0f}"),
        "",
        "Nota das avaliações por situação de entrega (pares avaliação–pedido):",
        "",
        md_table(vs_score),
        "",
        md_table(by_delay),
        "",
    ]
    (no_review,) = con.execute(
        "SELECT COUNT(*) FROM orders WHERE order_id NOT IN (SELECT order_id FROM review_orders)"
    ).fetchone()
    (last_created,) = con.execute("SELECT MAX(review_creation_date) FROM reviews").fetchone()
    late_end = late_window_end(con)
    cens = q(
        """
        SELECT estimated_week AS semana_estimada, COUNT(*) AS pedidos,
               SUM(delivered_customer_ts IS NULL) AS sem_entrega, AVG(is_late) AS frac_atraso
        FROM orders WHERE estimated_week BETWEEN date(?, '-49 days') AND date(?, '+28 days')
        GROUP BY semana_estimada ORDER BY semana_estimada
        """,
        late_end,
        late_end,
    )
    cens["frac_atraso"] = cens["frac_atraso"].map(pct)
    late_pos = dd[dd > 0]
    out += [
        "### 6.1 Censura no fim do dataset",
        "",
        f"Todo pedido do dataset tem avaliação (pedidos sem avaliação: {no_review}) e a última "
        f"pesquisa foi enviada em {last_created[:10]}. Como a pesquisa sai depois da entrega "
        "(ou depois da data estimada, se o pedido não chegou), pedidos atrasados que seriam "
        "entregues depois do corte não estão no dataset: a taxa de atraso das últimas semanas "
        "cai artificialmente.",
        "",
        f"Entre os pedidos atrasados, {pct((late_pos <= LATE_CENSOR_MARGIN_DAYS).mean())} têm "
        f"até {LATE_CENSOR_MARGIN_DAYS} dias de atraso. As análises de atraso por semana vão até "
        f"a semana estimada **{late_end}** (corte − {LATE_CENSOR_MARGIN_DAYS} dias); mesmo "
        "assim, as últimas semanas podem estar levemente subestimadas.",
        "",
        md_table(cens),
        "",
    ]

    # --- 7. volume semanal ---
    start, end = analysis_window(con)
    weekly = q(
        """
        SELECT answered_week AS semana, COUNT(*) AS avaliações, SUM(has_comment) AS comentadas,
               AVG(review_score) AS nota_média, AVG(review_score <= 2) AS frac_neg
        FROM reviews GROUP BY semana ORDER BY semana
        """
    )
    late_w = q(
        """
        SELECT estimated_week AS semana, COUNT(*) AS pedidos_entregues, AVG(is_late) AS frac_atraso
        FROM orders WHERE is_late IS NOT NULL AND estimated_week <= ?
        GROUP BY semana ORDER BY semana
        """,
        late_end,
    )
    pit = weekly_due_late_rate(
        load_orders(con), [str(d.date()) for d in pd.date_range(start, late_end, freq="7D")]
    ).rename(columns={"week": "semana", "due": "pedidos_vencidos", "late_rate": "frac_atraso"})
    win = weekly[(weekly["semana"] >= start) & (weekly["semana"] <= end)]
    vol = win[["avaliações", "comentadas"]].describe().loc[["min", "25%", "50%", "75%", "max"]]
    vol.insert(0, "estatística", vol.index)
    out += [
        "## 7. Volume semanal",
        "",
        f"Semana = segunda-feira da semana de resposta (`answered_week`). Janela de análise: "
        f"**{start} a {end}** ({len(win)} semanas), definida como a 1ª e a última semana com "
        f"≥ {MIN_WEEKLY_COMMENTS} avaliações com comentário, limitada à última semana com "
        "pesquisas enviadas. Fora dela o volume é residual (início da operação em 2016) ou a "
        "semana está incompleta (corte do dataset em 2018).",
        "",
        md_table(vol, "{:.0f}"),
        "",
        "![Volume semanal e nota média](figures/fase1_semanal.png)",
        "",
    ]
    _plot_weekly(weekly, late_w, pit, start, end, figures / "fase1_semanal.png")

    # --- 8. cobertura por segmento ---
    cov = segment_coverage(con, start, end)
    out += [
        "## 8. Cobertura por segmento",
        "",
        "Para cada tipo de segmento: quantos segmentos têm volume médio semanal ≥ k na janela "
        "de análise, e (entre parênteses) a fração das avaliações daquele tipo que eles "
        "concentram. Um pedido com vários vendedores/categorias conta para todos eles.",
        "",
        md_table(cov),
        "",
    ]

    # --- 9. exploração temporal ---
    lw = pit[pit["pedidos_vencidos"] >= 200][["semana", "pedidos_vencidos", "frac_atraso"]]
    base = lw["frac_atraso"].median()
    peaks = lw[lw["frac_atraso"] >= 2 * base].merge(
        weekly[["semana", "nota_média", "frac_neg"]], on="semana", how="left"
    )
    peaks["frac_atraso"] = peaks["frac_atraso"].map(pct)
    peaks["frac_neg"] = peaks["frac_neg"].map(pct)

    sm = q(
        """
        SELECT customer_state AS estado, substr(estimated_delivery_date, 1, 7) AS mes,
               COUNT(*) AS n, AVG(is_late) AS atraso
        FROM orders WHERE is_late IS NOT NULL AND estimated_week BETWEEN ? AND ?
        GROUP BY estado, mes
        """,
        start,
        late_end,
    )
    top_states = sm.groupby("estado")["n"].sum().sort_values(ascending=False).head(10).index
    heat = sm[sm["estado"].isin(top_states)].pivot(index="estado", columns="mes", values="atraso")
    heat = heat.loc[top_states]
    heat_t = (heat * 100).round(0).reset_index()
    heat_t.columns = [str(c)[2:] if c != "estado" else c for c in heat_t.columns]
    _plot_heatmap(heat, figures / "fase1_atraso_estado_mes.png")

    state_base = sm.groupby("estado").apply(
        lambda g: (g["n"] * g["atraso"]).sum() / g["n"].sum(), include_groups=False
    )
    sm["base_estado"] = sm["estado"].map(state_base)
    sm["lift"] = sm["atraso"] / sm["base_estado"]
    st_peaks = sm[(sm["n"] >= 100) & (sm["lift"] >= 2.5)].sort_values("lift", ascending=False)
    st_peaks = st_peaks.assign(
        atraso=st_peaks["atraso"].map(pct), base_estado=st_peaks["base_estado"].map(pct)
    )

    seller = _seller_candidates(con, start, late_end)
    out += [
        "## 9. Exploração temporal: candidatos a estudo de caso",
        "",
        "Exploração descritiva para escolher estudos de caso; **não** é a definição de "
        "incidente do backtest (Fase 7). Taxa de atraso por semana da data estimada de "
        f"entrega (o atraso só é observável depois dela), até a semana {late_end} (seção 6.1).",
        "",
        f"### 9.1 Semanas com taxa nacional de atraso ≥ 2× a mediana ({pct(base)})",
        "",
        "Atraso **point-in-time** (seção 11): coorte com data estimada na semana, conhecida "
        "ao fim dela; pedidos nunca entregues contam como atrasados. Semanas com ≥ 200 "
        "pedidos vencidos; nota média e fração de notas ≤ 2 das avaliações respondidas na "
        "mesma semana. As seções 9.2 a 9.4 usam `orders.is_late` (data final de entrega): "
        "são descrições retrospectivas, não sinais do backtest.",
        "",
        md_table(peaks, "{:.2f}"),
        "",
        "### 9.2 Taxa de atraso (%) por estado do cliente e mês da data estimada",
        "",
        "Os 10 estados com mais pedidos.",
        "",
        md_table(heat_t, "{:.0f}"),
        "",
        "![Atraso por estado e mês](figures/fase1_atraso_estado_mes.png)",
        "",
        "### 9.3 Estado × mês com atraso ≥ 2,5× a taxa média do próprio estado (n ≥ 100)",
        "",
        md_table(st_peaks.drop(columns="lift").head(20)),
        "",
        "### 9.4 Vendedor × mês com fração de notas ≤ 2 ≥ 2× a do próprio vendedor",
        "",
        "Vendedores com ≥ 300 avaliações na janela; mês com ≥ 30 avaliações e ≥ 15 notas ≤ 2. "
        "A coluna de atraso nacional do mês ajuda a separar problema do vendedor de problema "
        "sistêmico. IDs truncados em 8 caracteres.",
        "",
        md_table(seller),
        "",
    ]

    # --- 10. evidência para a taxonomia ---
    out += [
        "## 10. Evidência para a taxonomia: “não recebi” × desfecho do pedido",
        "",
        "Busca por expressões regulares no texto (não é classificação nem rótulo), cruzada "
        "com o desfecho objetivo do pedido. Pares avaliação–pedido com comentário.",
        "",
        md_table(_text_vs_outcome(con)),
        "",
    ]

    out += _pit_section(late_w, pit, weekly, figures / "fase1_pit_vs_nota.png")

    path = reports / "fase1_dados.md"
    path.write_text("\n".join(out), encoding="utf-8", newline="\n")
    print(f"Relatório gravado em {path}")


TEXT_PATTERNS = {
    "não recebi / não chegou": r"n[aã]o (?:recebi|chegou|foi entregue|entregaram|me entregaram)"
    r"|ainda n[aã]o (?:recebi|chegou)|nunca (?:recebi|chegou)",
    "extravio / consta entregue": r"extravi|consta(?:va)? como entregue"
    r"|consta que (?:foi )?entregue|entregue (?:a|para) outra|roubad",
    "cancelamento / estoque": r"cancel|sem estoque|fora de estoque"
    r"|n[aã]o (?:tinha|havia) (?:o produto|em estoque|estoque)",
}


def _text_vs_outcome(con: sqlite3.Connection) -> pd.DataFrame:
    d = pd.read_sql(
        """
        SELECT r.comment_message AS m, o.order_status AS st, o.is_late,
               o.delivered_customer_ts IS NOT NULL AS entregue,
               r.review_creation_date < COALESCE(date(o.delivered_customer_ts), '9999') AS antes
        FROM reviews r JOIN review_orders ro ON ro.review_id = r.review_id
        JOIN orders o ON o.order_id = ro.order_id WHERE r.has_comment = 1
        """,
        con,
    )
    text = d["m"].str.lower()  # lower() do SQLite só converte ASCII ("NÃO" -> "nÃo")
    rows = []
    for name, pattern in TEXT_PATTERNS.items():
        x = d[text.str.contains(pattern, regex=True)]
        top = x["st"].value_counts().head(4)
        rows.append(
            {
                "expressão no texto": name,
                "pares": len(x),
                "entregue depois": pct(x["entregue"].mean()),
                "atrasado (entre entregues)": pct(x.loc[x["entregue"] == 1, "is_late"].mean()),
                "pesquisa antes da entrega": pct(x["antes"].mean()),
                "status final": ", ".join(f"{k} {v}" for k, v in top.items()),
            }
        )
    return pd.DataFrame(rows)


def _seller_candidates(con: sqlite3.Connection, start: str, end: str) -> pd.DataFrame:
    d = pd.read_sql(
        """
        SELECT rs.segment_value AS vendedor, substr(r.answered_week, 1, 7) AS mes,
               COUNT(DISTINCT r.review_id) AS n, AVG(r.review_score <= 2) AS neg,
               AVG(o.is_late) AS atraso
        FROM review_segments rs
        JOIN reviews r ON r.review_id = rs.review_id
        JOIN review_orders ro ON ro.review_id = r.review_id
        JOIN orders o ON o.order_id = ro.order_id
        WHERE rs.segment_type = 'vendedor' AND r.answered_week BETWEEN ? AND ?
        GROUP BY vendedor, mes
        """,
        con,
        params=(start, end),
    )
    nat = pd.read_sql(
        """
        SELECT substr(r.answered_week, 1, 7) AS mes, AVG(o.is_late) AS atraso_nacional
        FROM reviews r JOIN review_orders ro ON ro.review_id = r.review_id
        JOIN orders o ON o.order_id = ro.order_id GROUP BY mes
        """,
        con,
    )
    d["n_neg"] = (d["n"] * d["neg"]).round().astype(int)
    tot = d.groupby("vendedor")[["n", "n_neg"]].sum()
    big = tot[tot["n"] >= 300]
    d = d[d["vendedor"].isin(big.index)].copy()
    d["base"] = d["vendedor"].map(big["n_neg"] / big["n"])
    d = d[(d["n"] >= 30) & (d["n_neg"] >= 15) & (d["neg"] >= 2 * d["base"])]
    d = d.merge(nat, on="mes").sort_values(["mes", "vendedor"])
    state = dict(con.execute("SELECT seller_id, seller_state FROM sellers").fetchall())
    return pd.DataFrame(
        {
            "vendedor": d["vendedor"].str[:8],
            "UF vendedor": d["vendedor"].map(state),
            "mês": d["mes"],
            "avaliações": d["n"],
            "% nota ≤ 2": d["neg"].map(pct),
            "% nota ≤ 2 (base)": d["base"].map(pct),
            "% atraso": d["atraso"].map(pct),
            "% atraso nacional": d["atraso_nacional"].map(pct),
        }
    )


def _pit_section(
    final: pd.DataFrame, pit: pd.DataFrame, weekly: pd.DataFrame, fig_path: Path
) -> list[str]:
    """Compara o atraso pela data final com o point-in-time, e ambos com a nota média."""
    m = pit[["semana", "pedidos_vencidos", "late", "open_late", "frac_atraso"]].merge(
        final[["semana", "frac_atraso"]].rename(columns={"frac_atraso": "frac_atraso_final"}),
        on="semana",
        how="left",
    )
    m = m.merge(weekly[["semana", "nota_média", "frac_neg"]], on="semana", how="left")
    diff_pp = 100 * (m["frac_atraso"] - m["frac_atraso_final"])
    corr_ff = m["frac_atraso"].corr(m["frac_atraso_final"])

    # correlação entre o atraso na semana t e as avaliações respondidas na semana t + k
    lag_rows = []
    for label, series in (("point-in-time", "frac_atraso"), ("data final", "frac_atraso_final")):
        for k in LAGS:
            lag_rows.append(
                {
                    "atraso": label,
                    "k (semanas)": k,
                    "corr(atraso_t, nota média_t+k)": m[series].corr(m["nota_média"].shift(-k)),
                    "corr(atraso_t, frac. nota ≤ 2_t+k)": m[series].corr(m["frac_neg"].shift(-k)),
                }
            )
    lags = pd.DataFrame(lag_rows)
    best = {
        str(label): int(g.loc[g["corr(atraso_t, nota média_t+k)"].idxmin(), "k (semanas)"])
        for label, g in lags.groupby("atraso")
    }

    ev_rows = []
    for name, (a, b) in EVENT_WINDOWS.items():
        e = m[(m["semana"] >= a) & (m["semana"] <= b)]
        ev_rows.append(
            {
                "evento": name,
                "pico de atraso (point-in-time)": e.loc[e["frac_atraso"].idxmax(), "semana"],
                "pico de atraso (data final)": e.loc[e["frac_atraso_final"].idxmax(), "semana"],
                "menor nota média": e.loc[e["nota_média"].idxmin(), "semana"],
                "maior frac. nota ≤ 2": e.loc[e["frac_neg"].idxmax(), "semana"],
            }
        )
    _plot_pit(m, fig_path)
    return [
        "## 11. Atraso point-in-time × data final × nota média",
        "",
        "**Auditoria.** `orders.is_late` usa a data final de entrega. Foi usado nas seções 6 "
        "(nota por situação de entrega), 9.2–9.4 (estado e vendedor por mês) e 10 (desfecho dos "
        "textos “não recebi”), que são descrições retrospectivas. A série semanal da Fase 1 "
        "(gráfico e tabela 9.1) também usava `is_late`, indexada pela semana estimada; agora "
        "usa a versão point-in-time.",
        "",
        "**Versão point-in-time** (`src/data/point_in_time.py`): para a semana t, coorte com data "
        "estimada de t a t + 6, avaliada em t + 7 dias, usando só entregas anteriores a esse "
        "instante. Para essa coorte o atraso já está decidido em t + 7 (o dia estimado passou), "
        "então a diferença para a série pela data final está no denominador: pedidos nunca "
        "entregues contam como atrasados em vez de ficarem de fora.",
        "",
        f"- Diferença point-in-time − data final, por semana: média {diff_pp.mean():+.2f} p.p., "
        f"máxima {diff_pp.max():+.2f} p.p.; correlação entre as séries: {corr_ff:.3f}.",
        f"- Atrasados ainda em aberto ao fim da semana estimada: {int(m['open_late'].sum())} de "
        f"{int(m['late'].sum())} ({pct(m['open_late'].sum() / m['late'].sum())}).",
        f"- Defasagem com a correlação mais negativa entre atraso e nota média: k = "
        f"{best['point-in-time']} (point-in-time) e k = {best['data final']} (data final).",
        "",
        "Picos dentro de cada evento (semana, segunda-feira):",
        "",
        md_table(pd.DataFrame(ev_rows)),
        "",
        "Correlação entre o atraso da semana t e as avaliações respondidas em t + k:",
        "",
        md_table(lags, "{:.3f}"),
        "",
        "![Atraso point-in-time e nota média](figures/fase1_pit_vs_nota.png)",
        "",
    ]


def _plot_pit(m: pd.DataFrame, path: Path) -> None:
    fig, ax = plt.subplots(figsize=(11, 4))
    x = pd.to_datetime(m["semana"])
    ax.plot(x, 100 * m["frac_atraso"], color="#dd8452", label="% atraso (point-in-time)")
    ax.plot(
        x,
        100 * m["frac_atraso_final"],
        color="#dd8452",
        ls="--",
        alpha=0.6,
        label="% atraso (data final)",
    )
    ax.set_ylabel("% atrasados (semana estimada)")
    ax2 = ax.twinx()
    ax2.plot(x, m["nota_média"], color="#c44e52", label="nota média (semana de resposta)")
    ax2.set_ylabel("nota média (invertido)")
    ax2.invert_yaxis()
    h1, l1 = ax.get_legend_handles_labels()
    h2, l2 = ax2.get_legend_handles_labels()
    ax.legend(h1 + h2, l1 + l2, loc="upper left")
    ax.grid(alpha=0.3)
    ax.set_title("Atraso point-in-time × nota média")
    fig.tight_layout()
    fig.savefig(path, dpi=110)
    plt.close(fig)


def _plot_weekly(
    weekly: pd.DataFrame,
    late_w: pd.DataFrame,
    pit: pd.DataFrame,
    start: str,
    end: str,
    path: Path,
) -> None:
    w = weekly[(weekly["semana"] >= start) & (weekly["semana"] <= end)]
    lw = late_w[(late_w["semana"] >= start) & (late_w["semana"] <= end)]
    fig, axes = plt.subplots(3, 1, figsize=(11, 8), sharex=True)
    x = pd.to_datetime(w["semana"])
    axes[0].bar(x, w["avaliações"], width=6, color="#bbb", label="avaliações")
    axes[0].bar(x, w["comentadas"], width=6, color="#4c72b0", label="com comentário")
    axes[0].set_ylabel("por semana")
    axes[0].legend(loc="upper left")
    axes[1].plot(x, w["nota_média"], color="#c44e52")
    axes[1].set_ylabel("nota média")
    axes[2].plot(
        pd.to_datetime(pit["semana"]),
        100 * pit["frac_atraso"],
        color="#dd8452",
        label="point-in-time",
    )
    axes[2].plot(
        pd.to_datetime(lw["semana"]),
        100 * lw["frac_atraso"],
        color="#dd8452",
        ls="--",
        alpha=0.6,
        label="data final",
    )
    axes[2].legend(loc="upper left")
    axes[2].set_ylabel("% atrasados\n(semana estimada)")
    for ax in axes:
        ax.grid(alpha=0.3)
    fig.suptitle("Olist: volume, nota média e atraso por semana")
    fig.tight_layout()
    fig.savefig(path, dpi=110)
    plt.close(fig)


def _plot_heatmap(heat: pd.DataFrame, path: Path) -> None:
    fig, ax = plt.subplots(figsize=(12, 4.5))
    im = ax.imshow(100 * heat.to_numpy(dtype=float), aspect="auto", cmap="OrRd")
    ax.set_xticks(range(len(heat.columns)), [str(c) for c in heat.columns], rotation=60)
    ax.set_yticks(range(len(heat.index)), list(heat.index))
    fig.colorbar(im, ax=ax, label="% atrasados")
    ax.set_title("Taxa de atraso por estado do cliente e mês da data estimada")
    fig.tight_layout()
    fig.savefig(path, dpi=110)
    plt.close(fig)


if __name__ == "__main__":
    main()
