# Backtest: avaliação (2018)

_Gerado por `python -m src.detection.backtest`. Não edite à mão._

- Segmentos monitorados: 34 (13 estados, 21 categorias).
- Semanas do período: 33 (2018-01-01 a 2018-08-13).
- Incidentes com início no período: tipo A 26, tipo B 1.
- θ: menor valor da grade com ≤ 1 falso alarme por semana na calibração (D-026, D-048); aplicado aqui sem mudança.

## Resultado no θ calibrado

| método | θ | alertas | falsos alarmes | FA/semana | recall A | recall B |
|---|---|---|---|---|---|---|
| Radar | 3.25 | 114 | 29 | 0.88 | 22/26 | 1/1 |
| B1 | 1.75 | 166 | 32 | 0.97 | 25/26 | 1/1 |
| B2 | 2.00 | 149 | 29 | 0.88 | 24/26 | 1/1 |
| B3 | 1.25 | 248 | 65 | 1.97 | 26/26 | 1/1 |

## Antecedência

| comparação | tipo | incidentes | ambos detectam | só Radar | só o outro | antecedência mediana (sem) | antecedência média (sem) |
|---|---|---|---|---|---|---|---|
| Radar vs B1 | A | 26 | 22 | 0 | 3 | 0.00 | -0.73 |
| Radar vs B1 | B | 1 | 1 | 0 | 0 | -4.00 | -4.00 |
| Radar vs B2 | A | 26 | 21 | 1 | 3 | 0.00 | -0.10 |
| Radar vs B2 | B | 1 | 1 | 0 | 0 | -4.00 | -4.00 |

| método | tipo | detectados | início − detecção, mediana (sem) |
|---|---|---|---|
| Radar | A | 22 | 0.50 |
| Radar | B | 1 | -1.00 |
| B1 | A | 25 | 2.00 |
| B1 | B | 1 | 3.00 |
| B2 | A | 24 | 1.00 |
| B2 | B | 1 | 3.00 |
| B3 | A | 26 | 3.00 |
| B3 | B | 1 | 4.00 |

### Incidente por incidente

Semana da primeira detecção de cada método (— = não detectou). Antecedência = detecção do outro método − detecção do Radar, em semanas (positivo = Radar antes).

| segment_type | segment_value | tipo | start | end | Radar | família (Radar) | B1 | B2 | B3 | antecedência vs B1 (sem) | antecedência vs B2 (sem) |
|---|---|---|---|---|---|---|---|---|---|---|---|
| categoria | esporte_lazer | B | 2018-01-29 | 2018-02-05 | 2018-02-05 | incompleto | 2018-01-08 | 2018-01-08 | 2018-01-01 | -4 | -4 |
| categoria | relogios_presentes | A | 2018-01-29 | 2018-02-05 | 2018-01-01 | entrega | 2018-01-01 | — | 2018-01-01 | 0 |  |
| categoria | cool_stuff | A | 2018-02-12 | 2018-02-19 | — |  | — | — | 2018-02-12 |  |  |
| categoria | utilidades_domesticas | A | 2018-02-19 | 2018-04-02 | — |  | 2018-02-19 | 2018-03-26 | 2018-01-29 |  |  |
| categoria | ferramentas_jardim | A | 2018-02-26 | 2018-04-09 | 2018-02-19 | produto | 2018-03-12 | 2018-03-12 | 2018-02-26 | +3 | +3 |
| estado | GO | A | 2018-03-05 | 2018-04-02 | 2018-03-12 | entrega | 2018-03-05 | 2018-03-05 | 2018-03-05 | -1 | -1 |
| estado | RJ | A | 2018-03-05 | 2018-04-09 | 2018-02-12 | entrega | 2018-02-05 | 2018-02-05 | 2018-02-05 | -1 | -1 |
| categoria | cama_mesa_banho | A | 2018-03-12 | 2018-04-23 | 2018-03-12 | entrega | 2018-02-26 | 2018-03-05 | 2018-03-05 | -2 | -1 |
| categoria | cool_stuff | A | 2018-03-12 | 2018-03-26 | 2018-03-19 | entrega | 2018-02-26 | 2018-03-12 | 2018-02-12 | -3 | -1 |
| categoria | eletronicos | A | 2018-03-12 | 2018-04-02 | 2018-02-12 | entrega | 2018-02-12 | 2018-04-02 | 2018-02-26 | 0 | +7 |
| categoria | esporte_lazer | A | 2018-03-12 | 2018-04-09 | 2018-02-19 | entrega | 2018-02-19 | 2018-02-19 | 2018-02-12 | 0 | 0 |
| categoria | informatica_acessorios | A | 2018-03-12 | 2018-04-02 | 2018-03-12 | entrega | 2018-03-12 | 2018-03-12 | 2018-02-19 | 0 | 0 |
| categoria | moveis_decoracao | A | 2018-03-12 | 2018-03-26 | 2018-03-19 | atendimento | 2018-03-19 | 2018-02-26 | 2018-02-19 | 0 | -3 |
| categoria | papelaria | A | 2018-03-12 | 2018-04-02 | 2018-02-19 | entrega | 2018-02-19 | 2018-02-19 | 2018-02-19 | 0 | 0 |
| categoria | relogios_presentes | A | 2018-03-12 | 2018-04-09 | 2018-03-12 | entrega | 2018-03-05 | 2018-03-05 | 2018-02-12 | -1 | -1 |
| estado | MG | A | 2018-03-12 | 2018-04-16 | 2018-03-12 | entrega | 2018-03-05 | 2018-03-05 | 2018-02-19 | -1 | -1 |
| estado | PR | A | 2018-03-12 | 2018-04-09 | 2018-03-19 | entrega | 2018-03-12 | 2018-03-12 | 2018-03-12 | -1 | -1 |
| estado | SC | A | 2018-03-12 | 2018-04-02 | 2018-02-19 | entrega | 2018-02-19 | 2018-02-19 | 2018-02-19 | 0 | 0 |
| estado | SP | A | 2018-03-12 | 2018-03-26 | 2018-03-12 | entrega | 2018-02-19 | 2018-02-19 | 2018-02-19 | -3 | -3 |
| categoria | automotivo | A | 2018-03-19 | 2018-04-02 | 2018-02-19 | entrega | 2018-02-19 | 2018-02-19 | 2018-02-19 | 0 | 0 |
| categoria | beleza_saude | A | 2018-03-19 | 2018-04-16 | 2018-03-05 | entrega | 2018-03-12 | 2018-03-12 | 2018-02-19 | +1 | +1 |
| categoria | perfumaria | A | 2018-03-19 | 2018-04-02 | — |  | 2018-03-19 | 2018-03-19 | 2018-02-19 |  |  |
| categoria | telefonia | A | 2018-03-19 | 2018-04-02 | 2018-04-02 | entrega | 2018-03-12 | 2018-03-26 | 2018-03-05 | -3 | -1 |
| estado | BA | A | 2018-03-19 | 2018-04-23 | 2018-02-26 | incompleto | 2018-03-05 | 2018-03-05 | 2018-03-12 | +1 | +1 |
| estado | RS | A | 2018-03-19 | 2018-04-09 | 2018-03-26 | entrega | 2018-02-19 | 2018-03-26 | 2018-02-19 | -5 | 0 |
| estado | ES | A | 2018-04-09 | 2018-04-16 | 2018-03-19 | entrega | 2018-03-19 | 2018-03-19 | 2018-03-19 | 0 | 0 |
| estado | SP | A | 2018-08-06 | 2018-08-13 | — |  | 2018-08-06 | 2018-08-06 | 2018-08-06 |  |  |

## Diagnóstico de causa do Radar

| tipo | detectados pelo Radar | família compatível | famílias no alerta |
|---|---|---|---|
| A | 22 | 19/22 | entrega: 19, produto: 1, atendimento: 1, incompleto: 1 |
| B | 1 | 1/1 | incompleto: 1 |

## Recall em níveis iguais de falsos alarmes

Comparação descritiva: o resultado principal é o do θ calibrado, acima. Para cada método e nível, o menor θ da grade cuja curva **deste período** fica em FA/semana ≤ nível (o degrau que não ultrapassa o nível, sem interpolar); esse θ é escolhido olhando 2018, por isso não é um resultado de previsão.

| nível (FA/sem ≤) | método | θ | FA/sem | recall A | recall B |
|---|---|---|---|---|---|
| 0.25 | Radar | 4.25 | 0.21 | 17/26 | 0/1 |
| 0.25 | B1 | 3.00 | 0.15 | 17/26 | 1/1 |
| 0.25 | B2 | 3.00 | 0.12 | 21/26 | 1/1 |
| 0.25 | B3 | 4.25 | 0.18 | 23/26 | 0/1 |
| 0.50 | Radar | 3.75 | 0.45 | 19/26 | 1/1 |
| 0.50 | B1 | 2.25 | 0.42 | 24/26 | 1/1 |
| 0.50 | B2 | 2.50 | 0.39 | 23/26 | 1/1 |
| 0.50 | B3 | 3.50 | 0.42 | 25/26 | 0/1 |
| 0.75 | Radar | 3.50 | 0.67 | 21/26 | 1/1 |
| 0.75 | B1 | 2.00 | 0.67 | 24/26 | 1/1 |
| 0.75 | B2 | 2.25 | 0.52 | 24/26 | 1/1 |
| 0.75 | B3 | 2.75 | 0.67 | 25/26 | 0/1 |
| 1.00 | Radar | 3.25 | 0.88 | 22/26 | 1/1 |
| 1.00 | B1 | 1.75 | 0.97 | 25/26 | 1/1 |
| 1.00 | B2 | 2.00 | 0.88 | 24/26 | 1/1 |
| 1.00 | B3 | 2.50 | 0.94 | 26/26 | 0/1 |

## Curva recall × falsos alarmes (grade completa)

Também em `reports/curva_avaliacao.csv` (com os falsos alarmes absolutos e o nº de incidentes).

| θ | Radar FA/sem | Radar recall A | Radar recall B | B1 FA/sem | B1 recall A | B1 recall B | B2 FA/sem | B2 recall A | B2 recall B | B3 FA/sem | B3 recall A | B3 recall B |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 0.50 | 15.06 | 1.00 | 1.00 | 3.76 | 1.00 | 1.00 | 4.30 | 1.00 | 1.00 | 2.67 | 1.00 | 1.00 |
| 0.75 | 13.73 | 1.00 | 1.00 | 3.03 | 1.00 | 1.00 | 3.61 | 1.00 | 1.00 | 2.42 | 1.00 | 1.00 |
| 1.00 | 12.48 | 1.00 | 1.00 | 2.33 | 1.00 | 1.00 | 2.73 | 1.00 | 1.00 | 2.33 | 1.00 | 1.00 |
| 1.25 | 8.24 | 1.00 | 1.00 | 1.73 | 1.00 | 1.00 | 2.24 | 0.96 | 1.00 | 1.97 | 1.00 | 1.00 |
| 1.50 | 6.97 | 1.00 | 1.00 | 1.36 | 0.96 | 1.00 | 1.58 | 0.96 | 1.00 | 1.82 | 1.00 | 1.00 |
| 1.75 | 5.76 | 1.00 | 1.00 | 0.97 | 0.96 | 1.00 | 1.30 | 0.96 | 1.00 | 1.64 | 1.00 | 1.00 |
| 2.00 | 4.91 | 1.00 | 1.00 | 0.67 | 0.92 | 1.00 | 0.88 | 0.92 | 1.00 | 1.33 | 1.00 | 1.00 |
| 2.25 | 2.91 | 1.00 | 1.00 | 0.42 | 0.92 | 1.00 | 0.52 | 0.92 | 1.00 | 1.18 | 1.00 | 1.00 |
| 2.50 | 2.12 | 1.00 | 1.00 | 0.33 | 0.88 | 1.00 | 0.39 | 0.88 | 1.00 | 0.94 | 1.00 | 0.00 |
| 2.75 | 1.64 | 0.96 | 1.00 | 0.27 | 0.85 | 1.00 | 0.30 | 0.88 | 1.00 | 0.67 | 0.96 | 0.00 |
| 3.00 | 1.27 | 0.92 | 1.00 | 0.15 | 0.65 | 1.00 | 0.12 | 0.81 | 1.00 | 0.55 | 0.96 | 0.00 |
| 3.25 | 0.88 | 0.85 | 1.00 | 0.09 | 0.62 | 1.00 | 0.06 | 0.73 | 1.00 | 0.52 | 0.96 | 0.00 |
| 3.50 | 0.67 | 0.81 | 1.00 | 0.03 | 0.50 | 1.00 | 0.03 | 0.62 | 1.00 | 0.42 | 0.96 | 0.00 |
| 3.75 | 0.45 | 0.73 | 1.00 | 0.00 | 0.42 | 0.00 | 0.03 | 0.50 | 0.00 | 0.36 | 0.92 | 0.00 |
| 4.00 | 0.42 | 0.65 | 1.00 | 0.00 | 0.42 | 0.00 | 0.03 | 0.42 | 0.00 | 0.30 | 0.92 | 0.00 |
| 4.25 | 0.21 | 0.65 | 0.00 | 0.00 | 0.42 | 0.00 | 0.00 | 0.42 | 0.00 | 0.18 | 0.88 | 0.00 |
| 4.50 | 0.09 | 0.58 | 0.00 | 0.00 | 0.35 | 0.00 | 0.00 | 0.42 | 0.00 | 0.15 | 0.85 | 0.00 |
| 4.75 | 0.09 | 0.58 | 0.00 | 0.00 | 0.35 | 0.00 | 0.00 | 0.38 | 0.00 | 0.12 | 0.77 | 0.00 |
| 5.00 | 0.09 | 0.54 | 0.00 | 0.00 | 0.35 | 0.00 | 0.00 | 0.38 | 0.00 | 0.09 | 0.77 | 0.00 |
| 5.25 | 0.06 | 0.50 | 0.00 | 0.00 | 0.35 | 0.00 | 0.00 | 0.31 | 0.00 | 0.09 | 0.77 | 0.00 |
| 5.50 | 0.03 | 0.42 | 0.00 | 0.00 | 0.31 | 0.00 | 0.00 | 0.27 | 0.00 | 0.09 | 0.77 | 0.00 |
| 5.75 | 0.03 | 0.38 | 0.00 | 0.00 | 0.23 | 0.00 | 0.00 | 0.23 | 0.00 | 0.09 | 0.65 | 0.00 |
| 6.00 | 0.03 | 0.38 | 0.00 | 0.00 | 0.19 | 0.00 | 0.00 | 0.23 | 0.00 | 0.06 | 0.65 | 0.00 |
| 6.25 | 0.03 | 0.38 | 0.00 | 0.00 | 0.19 | 0.00 | 0.00 | 0.15 | 0.00 | 0.06 | 0.62 | 0.00 |
| 6.50 | 0.03 | 0.38 | 0.00 | 0.00 | 0.15 | 0.00 | 0.00 | 0.15 | 0.00 | 0.06 | 0.62 | 0.00 |
| 6.75 | 0.00 | 0.38 | 0.00 | 0.00 | 0.12 | 0.00 | 0.00 | 0.08 | 0.00 | 0.03 | 0.58 | 0.00 |
| 7.00 | 0.00 | 0.27 | 0.00 | 0.00 | 0.12 | 0.00 | 0.00 | 0.08 | 0.00 | 0.03 | 0.54 | 0.00 |
| 7.25 | 0.00 | 0.23 | 0.00 | 0.00 | 0.08 | 0.00 | 0.00 | 0.08 | 0.00 | 0.03 | 0.46 | 0.00 |
| 7.50 | 0.00 | 0.23 | 0.00 | 0.00 | 0.08 | 0.00 | 0.00 | 0.08 | 0.00 | 0.03 | 0.46 | 0.00 |
| 7.75 | 0.00 | 0.23 | 0.00 | 0.00 | 0.04 | 0.00 | 0.00 | 0.08 | 0.00 | 0.03 | 0.42 | 0.00 |
| 8.00 | 0.00 | 0.19 | 0.00 | 0.00 | 0.04 | 0.00 | 0.00 | 0.08 | 0.00 | 0.03 | 0.42 | 0.00 |

## Incidentes do período

| segment_type | segment_value | tipo | start | end |
|---|---|---|---|---|
| categoria | esporte_lazer | B | 2018-01-29 | 2018-02-05 |
| categoria | relogios_presentes | A | 2018-01-29 | 2018-02-05 |
| categoria | cool_stuff | A | 2018-02-12 | 2018-02-19 |
| categoria | utilidades_domesticas | A | 2018-02-19 | 2018-04-02 |
| categoria | ferramentas_jardim | A | 2018-02-26 | 2018-04-09 |
| estado | GO | A | 2018-03-05 | 2018-04-02 |
| estado | RJ | A | 2018-03-05 | 2018-04-09 |
| categoria | cama_mesa_banho | A | 2018-03-12 | 2018-04-23 |
| categoria | cool_stuff | A | 2018-03-12 | 2018-03-26 |
| categoria | eletronicos | A | 2018-03-12 | 2018-04-02 |
| categoria | esporte_lazer | A | 2018-03-12 | 2018-04-09 |
| categoria | informatica_acessorios | A | 2018-03-12 | 2018-04-02 |
| categoria | moveis_decoracao | A | 2018-03-12 | 2018-03-26 |
| categoria | papelaria | A | 2018-03-12 | 2018-04-02 |
| categoria | relogios_presentes | A | 2018-03-12 | 2018-04-09 |
| estado | MG | A | 2018-03-12 | 2018-04-16 |
| estado | PR | A | 2018-03-12 | 2018-04-09 |
| estado | SC | A | 2018-03-12 | 2018-04-02 |
| estado | SP | A | 2018-03-12 | 2018-03-26 |
| categoria | automotivo | A | 2018-03-19 | 2018-04-02 |
| categoria | beleza_saude | A | 2018-03-19 | 2018-04-16 |
| categoria | perfumaria | A | 2018-03-19 | 2018-04-02 |
| categoria | telefonia | A | 2018-03-19 | 2018-04-02 |
| estado | BA | A | 2018-03-19 | 2018-04-23 |
| estado | RS | A | 2018-03-19 | 2018-04-09 |
| estado | ES | A | 2018-04-09 | 2018-04-16 |
| estado | SP | A | 2018-08-06 | 2018-08-13 |

## Caso `5dceca12` (D-026, item 3)

Vendedor não é segmento de detecção (D-021): o caso é examinado pelas categorias dos seus pedidos. Categoria não monitorada = limitação de cobertura.

| categoria | pedidos do vendedor | monitorada | alertas do Radar (mar–mai/2018) | incidentes no período |
|---|---|---|---|---|
| malas_acessorios | 184 | sim | nenhum | nenhum |
| bebes | 105 | sim | 2018-03-12 (entrega) | nenhum |
| cama_mesa_banho | 16 | sim | 2018-03-12 (entrega), 2018-03-19 (entrega), 2018-04-09 (entrega) | A 2018-03-12→2018-04-23 |
| casa_conforto | 9 | não | nenhum | nenhum |
| cool_stuff | 8 | sim | 2018-03-19 (entrega) | A 2018-03-12→2018-03-26 |
| fashion_esporte | 2 | não | nenhum | nenhum |
| fashion_calcados | 1 | não | nenhum | nenhum |
