# Fase 3: baseline e LLM v1 no dev

_Gerado por `python -m src.eval.dev_report`. Não edite à mão._

- Dev: 100 itens, 96 não ambíguos nas métricas (D-031). Taxonomia v1.1, 8 classes.
- Macro-F1 entre colchetes: IC 95% por bootstrap (1.000 reamostragens, semente 42). Reponderado: cada item pesa pela participação da sua nota no universo (D-028).
- Falha de schema conta como erro (`FAIL`). Tempo do LLM: latência da chamada, com o modelo já carregado; do baseline: só a previsão (o ajuste está em `fit_s` no CSV).
- Classes com poucos itens no dev (atendimento 3, outro 4) têm F1 instável.
- Pendente (sem previsões ainda): LLM v1 com raciocínio.

## Resumo

| método | macro-F1 | macro-F1 reponderado | acurácia | acurácia reponderada | falha de schema | s/item, mediana (média) | itens com 2ª tentativa |
|---|---|---|---|---|---|---|---|
| baseline TF-IDF+LR (CV 5 partes) | 0.408 [0.282; 0.508] | 0.401 | 0.625 | 0.759 | 0/100 (0.0%) | 0.000938 (0.00104) | — |
| LLM v1 sem raciocínio | 0.846 [0.676; 0.937] | 0.804 | 0.906 | 0.913 | 0/100 (0.0%) | 1.36 (1.41) | 0 |

### Métrica secundária: discordâncias em que a regra apoia o modelo (D-041)

**Não é a métrica principal.** A principal (acima) usa os rótulos originais e é a estimativa conservadora. Aqui, nos 4 itens de `data/gold/discordancias_regra.csv`, a previsão igual à causa dada pela regra escrita da taxonomia v1.1 também conta como acerto; nenhum rótulo foi alterado. Viés: os itens saíram da leitura dos erros do LLM v1 sem raciocínio, então esta métrica favorece esse método.

| método | macro-F1 (secundário) | macro-F1 reponderado (secundário) | acurácia (secundária) |
|---|---|---|---|
| baseline TF-IDF+LR (CV 5 partes) | 0.418 | 0.408 | 0.635 |
| LLM v1 sem raciocínio | 0.921 | 0.895 | 0.948 |

## Métricas por classe

### baseline TF-IDF+LR (CV 5 partes)

| classe | n | precisão | recall | F1 | F1 reponderado |
|---|---|---|---|---|---|
| entrega | 18 | 0.44 | 0.61 | 0.51 | 0.49 |
| defeito | 6 | 0.25 | 0.17 | 0.20 | 0.27 |
| diferente | 8 | 0.71 | 0.62 | 0.67 | 0.59 |
| incompleto | 12 | 0.38 | 0.42 | 0.40 | 0.36 |
| qualidade | 6 | 0.25 | 0.17 | 0.20 | 0.16 |
| atendimento | 3 | 0.00 | 0.00 | 0.00 | 0.00 |
| elogio | 39 | 0.86 | 0.92 | 0.89 | 0.96 |
| outro | 4 | 1.00 | 0.25 | 0.40 | 0.38 |

### LLM v1 sem raciocínio

| classe | n | precisão | recall | F1 | F1 reponderado |
|---|---|---|---|---|---|
| entrega | 18 | 0.85 | 0.94 | 0.89 | 0.83 |
| defeito | 6 | 0.67 | 1.00 | 0.80 | 0.85 |
| diferente | 8 | 0.80 | 1.00 | 0.89 | 0.81 |
| incompleto | 12 | 0.91 | 0.83 | 0.87 | 0.83 |
| qualidade | 6 | 1.00 | 0.50 | 0.67 | 0.54 |
| atendimento | 3 | 1.00 | 0.67 | 0.80 | 0.73 |
| elogio | 39 | 1.00 | 0.97 | 0.99 | 0.98 |
| outro | 4 | 1.00 | 0.75 | 0.86 | 0.87 |

## Matrizes de confusão (linhas = gold, colunas = previsto)

### baseline TF-IDF+LR (CV 5 partes)

| gold \ previsto | entrega | defeito | diferente | incompleto | qualidade | atendimento | elogio | outro |
|---|---|---|---|---|---|---|---|---|
| entrega | 11 | 0 | 0 | 4 | 1 | 0 | 2 | 0 |
| defeito | 2 | 1 | 0 | 3 | 0 | 0 | 0 | 0 |
| diferente | 2 | 0 | 5 | 1 | 0 | 0 | 0 | 0 |
| incompleto | 5 | 2 | 0 | 5 | 0 | 0 | 0 | 0 |
| qualidade | 3 | 1 | 0 | 0 | 1 | 0 | 1 | 0 |
| atendimento | 0 | 0 | 1 | 0 | 0 | 0 | 2 | 0 |
| elogio | 1 | 0 | 1 | 0 | 1 | 0 | 36 | 0 |
| outro | 1 | 0 | 0 | 0 | 1 | 0 | 1 | 1 |

### LLM v1 sem raciocínio

| gold \ previsto | entrega | defeito | diferente | incompleto | qualidade | atendimento | elogio | outro |
|---|---|---|---|---|---|---|---|---|
| entrega | 17 | 0 | 0 | 1 | 0 | 0 | 0 | 0 |
| defeito | 0 | 6 | 0 | 0 | 0 | 0 | 0 | 0 |
| diferente | 0 | 0 | 8 | 0 | 0 | 0 | 0 | 0 |
| incompleto | 1 | 0 | 1 | 10 | 0 | 0 | 0 | 0 |
| qualidade | 0 | 2 | 1 | 0 | 3 | 0 | 0 | 0 |
| atendimento | 1 | 0 | 0 | 0 | 0 | 2 | 0 | 0 |
| elogio | 1 | 0 | 0 | 0 | 0 | 0 | 38 | 0 |
| outro | 0 | 1 | 0 | 0 | 0 | 0 | 0 | 3 |

## Itens ambíguos (fora das métricas)

| review_id | nota | baseline TF-IDF+LR (CV 5 partes) | LLM v1 sem raciocínio |
|---|---|---|---|
| c131334b | 3 | defeito | elogio |
| 0f8b4ad4 | 3 | entrega | outro |
| 76561047 | 3 | defeito | defeito |
| 5875e483 | 2 | diferente | diferente |

## A nota como atalho (D-029)

Acerto por nota e erros na direção da nota. No gold set, todos os itens de nota 5 são `elogio`, então o atalho nota 5 → elogio não é penalizado aqui.

| método | acerto nota 1 | acerto nota 2 | acerto nota 3 | acerto nota 4 | acerto nota 5 | nota 4–5, gold ≠ elogio, previsto elogio | nota 1–2, gold = elogio, previsto ≠ elogio |
|---|---|---|---|---|---|---|---|
| baseline TF-IDF+LR (CV 5 partes) | 0.45 | 0.68 | 0.24 | 0.70 | 1.00 | 6/6 | 1/1 |
| LLM v1 sem raciocínio | 0.85 | 1.00 | 0.82 | 0.90 | 0.95 | 0/6 | 0/1 |

## Observação: causa de entrega × sinal objetivo de entrega

Só descritivo, sem métrica: a flag de atraso foi removida (D-033). O sinal objetivo é retrospectivo: pedido entregue depois da data estimada (`orders.is_late`) ou nunca entregue. Reclamação de demora dentro do prazo e atraso sem reclamação são esperados (taxonomia, `problema_entrega`).

| fonte | itens | previsto/rotulado entrega | com atraso ou sem entrega | atrasados ou sem entrega no total | desses, com causa entrega | concordância (sim/sim + não/não) |
|---|---|---|---|---|---|---|
| gold (não ambíguos) | 96 | 18 | 11/18 | 12 | 11/12 | 91.7% |
| baseline TF-IDF+LR (CV 5 partes) | 100 | 26 | 8/26 | 12 | 8/12 | 78.0% |
| LLM v1 sem raciocínio | 100 | 20 | 12/20 | 12 | 12/12 | 92.0% |

## Erros do LLM v1 sem raciocínio (insumo da Fase 4)

9 erros em 96 itens. Só IDs e rótulos; a leitura dos textos está em `docs/erros.md`.

| review_id | nota | gold | previsto | confiança |
|---|---|---|---|---|
| 31369d4a | 5 | elogio | entrega | 0.85 |
| bb385b4d | 3 | outro | defeito | 0.95 |
| 0c4648b0 | 1 | incompleto | entrega | 0.80 |
| 3cdb1acf | 1 | incompleto | diferente | 0.90 |
| 25221da0 | 4 | atendimento | entrega | 0.80 |
| 14cbabf3 | 3 | entrega | incompleto | 0.90 |
| 0e0e6e39 | 4 | qualidade | defeito | 0.90 |
| 251571af | 3 | qualidade | defeito | 0.85 |
| e0fa89c5 | 1 | qualidade | diferente | 0.80 |
