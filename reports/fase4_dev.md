# Fase 4: LLM v1 → v2 no dev

_Gerado por `python -m src.eval.fase4_report`. Não edite à mão._

Protocolo fixado antes de rodar a v2 (D-044): uma única iteração, regra de aceite e regra do limiar definidas a priori. A v2 (`prompts/classifier_v2.md`) só mexe nas categorias 2 a 5 de `docs/erros.md` e não muda definições de classe (D-041). Métricas completas dos dois prompts em `reports/fase3_dev.md`.

## Regra de aceite

| condição | v1 | v2 | passa |
|---|---|---|---|
| 1. macro-F1 principal v2 ≥ v1 | 0.846 | 0.864 | sim |
| 2. nenhum acerto perdido em classe rara | — | 1 perdidos | não |
| 3. falhas de schema v2 ≤ v1 | 0 | 0 | sim |

**Resultado: a v1 continua** (configuração escolhida: prompt v1, sem raciocínio).

## Comparação item a item (itens em que a previsão mudou)

6 de 96 itens não ambíguos mudaram: 3 ganhos, 3 perdas, 0 erros trocados. Acertos: v1 87, v2 87.

| review_id | nota | gold | v1 | v2 | efeito |
|---|---|---|---|---|---|
| e0fa89c5 | 1 | qualidade | diferente | qualidade | ganho |
| d1952450 | 2 | outro | outro | diferente | perda |
| 027ad90a | 1 | entrega | entrega | incompleto | perda |
| 78332b4c | 4 | entrega | entrega | elogio | perda |
| bb385b4d | 3 | outro | defeito | outro | ganho |
| 0c4648b0 | 1 | incompleto | entrega | incompleto | ganho |

## Limiar de confiança para revisão humana (prompt v1)

Itens com confiança abaixo do limiar iriam para revisão humana. Regra de escolha (D-044): maior acurácia do restante com no máximo 15% enviados; em empate, o que envia menos; sem ganho de pelo menos 2 p.p., não usar limiar.

| limiar | enviados | % enviada | acurácia do restante | erros entre os enviados |
|---|---|---|---|---|
| 0.00 | 0 | 0.0% | 90.6% | 0 |
| 0.80 | 0 | 0.0% | 90.6% | 0 |
| 0.85 | 19 | 19.8% | 92.2% | 3 |
| 0.90 | 25 | 26.0% | 94.4% | 5 |
| 0.95 | 51 | 53.1% | 97.8% | 8 |
| 1.00 | 85 | 88.5% | 100.0% | 9 |

**Proposta: sem limiar: o melhor limiar com ≤ 15% enviados ganha 0.0 p.p. (< 2 p.p.) sobre não enviar nada; dentro desse orçamento a confiança não separa os erros.**
