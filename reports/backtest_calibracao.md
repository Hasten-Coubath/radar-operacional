# Backtest: calibração (2017)

_Gerado por `python -m src.detection.backtest`. Não edite à mão._

- Segmentos monitorados: 34 (13 estados, 21 categorias).
- Semanas do período: 47 (2017-02-06 a 2017-12-25).
- Incidentes com início no período: tipo A 20, tipo B 1.
- θ: menor valor da grade com ≤ 1 falso alarme por semana na calibração (D-026, D-048).

## Resultado no θ calibrado

| método | θ | alertas | falsos alarmes | FA/semana | recall A | recall B |
|---|---|---|---|---|---|---|
| Radar | 3.25 | 70 | 35 | 0.74 | 16/20 | 0/1 |
| B1 | 1.75 | 89 | 45 | 0.96 | 17/20 | 1/1 |
| B2 | 2.00 | 83 | 44 | 0.94 | 17/20 | 1/1 |
| B3 | 1.25 | 127 | 46 | 0.98 | 20/20 | 1/1 |

## Antecedência

| comparação | tipo | incidentes | ambos detectam | só Radar | só B1 | antecedência mediana (sem) | antecedência média (sem) | só B2 |
|---|---|---|---|---|---|---|---|---|
| Radar vs B1 | A | 20 | 15 | 1 | 2.00 | 0.00 | 0.87 |  |
| Radar vs B1 | B | 1 | 0 | 0 | 1.00 |  |  |  |
| Radar vs B2 | A | 20 | 15 | 1 |  | 0.00 | 1.20 | 2.00 |
| Radar vs B2 | B | 1 | 0 | 0 |  |  |  | 1.00 |

| método | tipo | detectados | início − detecção, mediana (sem) |
|---|---|---|---|
| Radar | A | 16 | 0.00 |
| Radar | B | 0 |  |
| B1 | A | 17 | 0.00 |
| B1 | B | 1 | 0.00 |
| B2 | A | 17 | -1.00 |
| B2 | B | 1 | 0.00 |
| B3 | A | 20 | 0.50 |
| B3 | B | 1 | 1.00 |

## Diagnóstico de causa do Radar

| tipo | detectados pelo Radar | família compatível | famílias no alerta |
|---|---|---|---|
| A | 16 | 11/16 | entrega: 11, incompleto: 4, produto: 1 |
| B | 0 | 0/0 |  |

## Curva recall × falsos alarmes (alguns θ)

| theta | falsos_alarmes | fa_por_semana | recall_A | n_A | recall_B | n_B | método |
|---|---|---|---|---|---|---|---|
| 1.00 | 474 | 10.09 | 1.00 | 20 | 1.00 | 1 | Radar |
| 2.00 | 189 | 4.02 | 0.95 | 20 | 1.00 | 1 | Radar |
| 3.00 | 58 | 1.23 | 0.85 | 20 | 0.00 | 1 | Radar |
| 4.00 | 20 | 0.43 | 0.70 | 20 | 0.00 | 1 | Radar |
| 5.00 | 8 | 0.17 | 0.40 | 20 | 0.00 | 1 | Radar |
| 6.00 | 4 | 0.09 | 0.25 | 20 | 0.00 | 1 | Radar |
| 8.00 | 3 | 0.06 | 0.15 | 20 | 0.00 | 1 | Radar |
| 1.00 | 111 | 2.36 | 0.95 | 20 | 1.00 | 1 | B1 |
| 2.00 | 37 | 0.79 | 0.75 | 20 | 1.00 | 1 | B1 |
| 3.00 | 11 | 0.23 | 0.65 | 20 | 1.00 | 1 | B1 |
| 4.00 | 5 | 0.11 | 0.55 | 20 | 0.00 | 1 | B1 |
| 5.00 | 2 | 0.04 | 0.25 | 20 | 0.00 | 1 | B1 |
| 6.00 | 1 | 0.02 | 0.20 | 20 | 0.00 | 1 | B1 |
| 8.00 | 0 | 0.00 | 0.10 | 20 | 0.00 | 1 | B1 |
| 1.00 | 112 | 2.38 | 1.00 | 20 | 1.00 | 1 | B2 |
| 2.00 | 44 | 0.94 | 0.85 | 20 | 1.00 | 1 | B2 |
| 3.00 | 14 | 0.30 | 0.70 | 20 | 1.00 | 1 | B2 |
| 4.00 | 6 | 0.13 | 0.45 | 20 | 0.00 | 1 | B2 |
| 5.00 | 3 | 0.06 | 0.35 | 20 | 0.00 | 1 | B2 |
| 6.00 | 2 | 0.04 | 0.10 | 20 | 0.00 | 1 | B2 |
| 8.00 | 0 | 0.00 | 0.05 | 20 | 0.00 | 1 | B2 |
| 1.00 | 65 | 1.38 | 1.00 | 20 | 1.00 | 1 | B3 |
| 2.00 | 22 | 0.47 | 1.00 | 20 | 1.00 | 1 | B3 |
| 3.00 | 11 | 0.23 | 0.90 | 20 | 0.00 | 1 | B3 |
| 4.00 | 4 | 0.09 | 0.70 | 20 | 0.00 | 1 | B3 |
| 5.00 | 3 | 0.06 | 0.65 | 20 | 0.00 | 1 | B3 |
| 6.00 | 2 | 0.04 | 0.50 | 20 | 0.00 | 1 | B3 |
| 8.00 | 1 | 0.02 | 0.20 | 20 | 0.00 | 1 | B3 |

## Incidentes do período

| segment_type | segment_value | tipo | start | end |
|---|---|---|---|---|
| estado | SP | A | 2017-05-08 | 2017-05-15 |
| categoria | brinquedos | B | 2017-09-18 | 2017-09-25 |
| estado | BA | A | 2017-10-02 | 2017-10-09 |
| categoria | bebes | A | 2017-10-16 | 2017-11-06 |
| categoria | cool_stuff | A | 2017-10-23 | 2017-10-30 |
| estado | PR | A | 2017-11-06 | 2017-11-13 |
| categoria | ferramentas_jardim | A | 2017-11-27 | 2017-12-25 |
| categoria | moveis_decoracao | A | 2017-11-27 | 2017-12-25 |
| categoria | bebes | A | 2017-12-04 | 2017-12-18 |
| categoria | cool_stuff | A | 2017-12-04 | 2017-12-18 |
| categoria | utilidades_domesticas | A | 2017-12-04 | 2017-12-25 |
| estado | RS | A | 2017-12-04 | 2017-12-25 |
| categoria | brinquedos | A | 2017-12-11 | 2017-12-25 |
| categoria | cama_mesa_banho | A | 2017-12-11 | 2017-12-25 |
| categoria | esporte_lazer | A | 2017-12-11 | 2017-12-25 |
| categoria | relogios_presentes | A | 2017-12-11 | 2017-12-25 |
| categoria | telefonia | A | 2017-12-11 | 2017-12-25 |
| estado | MG | A | 2017-12-11 | 2017-12-25 |
| estado | PR | A | 2017-12-11 | 2017-12-18 |
| estado | RJ | A | 2017-12-11 | 2017-12-25 |
| categoria | perfumaria | A | 2017-12-18 | 2017-12-25 |
