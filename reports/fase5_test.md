# Fase 5: avaliação final no test set

_Gerado por script versionado (`src/eval/`). Não edite à mão._

- **Avaliação única** (D-045): configuração escolhida no dev (Fase 4: prompt v1, sem raciocínio, sem limiar de confiança) e baseline ajustado nos 96 itens não ambíguos do dev. Nenhum ajuste depois deste relatório.
- Sem métrica secundária: as anotações de D-041 são do dev.
- test: 150 itens, 137 não ambíguos nas métricas (D-031). Taxonomia v1.1, 8 classes.
- Macro-F1 entre colchetes: IC 95% por bootstrap (1.000 reamostragens, semente 42). Reponderado: cada item pesa pela participação da sua nota no universo (D-028).
- Falha de schema conta como erro (`FAIL`). Tempo do LLM: latência da chamada, com o modelo já carregado; do baseline: só a previsão (o ajuste está em `fit_s` no CSV).
- Classes com poucos itens têm F1 instável (no dev: atendimento 3, outro 4; no test: atendimento 2, outro 3).
- Pendente (sem previsões ainda): LLM v1 com raciocínio (comparação, depois do lote).

## Resumo

| método | macro-F1 | macro-F1 reponderado | acurácia | acurácia reponderada | falha de schema | s/item, mediana (média) | itens com 2ª tentativa |
|---|---|---|---|---|---|---|---|
| baseline TF-IDF+LR (ajustado no dev) | 0.422 [0.336; 0.492] | 0.471 | 0.708 | 0.839 | 0/150 (0.0%) | 0.000143 (0.000143) | — |
| LLM v1 sem raciocínio | 0.657 [0.518; 0.754] | 0.672 | 0.810 | 0.879 | 0/150 (0.0%) | 1.68 (1.8) | 0 |

## Métricas por classe

### baseline TF-IDF+LR (ajustado no dev)

| classe | n | precisão | recall | F1 | F1 reponderado |
|---|---|---|---|---|---|
| entrega | 31 | 0.57 | 0.74 | 0.65 | 0.68 |
| defeito | 9 | 0.75 | 0.33 | 0.46 | 0.64 |
| diferente | 7 | 0.17 | 0.14 | 0.15 | 0.31 |
| incompleto | 18 | 0.86 | 0.67 | 0.75 | 0.73 |
| qualidade | 12 | 0.50 | 0.42 | 0.45 | 0.45 |
| atendimento | 2 | 0.00 | 0.00 | 0.00 | 0.00 |
| elogio | 55 | 0.85 | 0.96 | 0.91 | 0.96 |
| outro | 3 | 0.00 | 0.00 | 0.00 | 0.00 |

### LLM v1 sem raciocínio

| classe | n | precisão | recall | F1 | F1 reponderado |
|---|---|---|---|---|---|
| entrega | 31 | 0.96 | 0.87 | 0.92 | 0.92 |
| defeito | 9 | 0.53 | 0.89 | 0.67 | 0.71 |
| diferente | 7 | 0.43 | 0.86 | 0.57 | 0.55 |
| incompleto | 18 | 0.68 | 0.72 | 0.70 | 0.64 |
| qualidade | 12 | 1.00 | 0.17 | 0.29 | 0.31 |
| atendimento | 2 | 0.33 | 0.50 | 0.40 | 0.55 |
| elogio | 55 | 1.00 | 0.93 | 0.96 | 0.98 |
| outro | 3 | 0.60 | 1.00 | 0.75 | 0.72 |

## Matrizes de confusão (linhas = gold, colunas = previsto)

### baseline TF-IDF+LR (ajustado no dev)

| gold \ previsto | entrega | defeito | diferente | incompleto | qualidade | atendimento | elogio | outro |
|---|---|---|---|---|---|---|---|---|
| entrega | 23 | 0 | 1 | 2 | 1 | 0 | 4 | 0 |
| defeito | 4 | 3 | 2 | 0 | 0 | 0 | 0 | 0 |
| diferente | 1 | 0 | 1 | 0 | 2 | 0 | 2 | 1 |
| incompleto | 5 | 1 | 0 | 12 | 0 | 0 | 0 | 0 |
| qualidade | 4 | 0 | 2 | 0 | 5 | 0 | 1 | 0 |
| atendimento | 1 | 0 | 0 | 0 | 1 | 0 | 0 | 0 |
| elogio | 2 | 0 | 0 | 0 | 0 | 0 | 53 | 0 |
| outro | 0 | 0 | 0 | 0 | 1 | 0 | 2 | 0 |

### LLM v1 sem raciocínio

| gold \ previsto | entrega | defeito | diferente | incompleto | qualidade | atendimento | elogio | outro |
|---|---|---|---|---|---|---|---|---|
| entrega | 27 | 1 | 0 | 2 | 0 | 1 | 0 | 0 |
| defeito | 0 | 8 | 0 | 1 | 0 | 0 | 0 | 0 |
| diferente | 0 | 0 | 6 | 1 | 0 | 0 | 0 | 0 |
| incompleto | 0 | 0 | 4 | 13 | 0 | 1 | 0 | 0 |
| qualidade | 0 | 6 | 4 | 0 | 2 | 0 | 0 | 0 |
| atendimento | 1 | 0 | 0 | 0 | 0 | 1 | 0 | 0 |
| elogio | 0 | 0 | 0 | 2 | 0 | 0 | 51 | 2 |
| outro | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 3 |

## Itens ambíguos (fora das métricas)

| review_id | nota | baseline TF-IDF+LR (ajustado no dev) | LLM v1 sem raciocínio |
|---|---|---|---|
| 9857b937 | 3 | qualidade | diferente |
| ee008a5e | 4 | elogio | elogio |
| 52c7c153 | 4 | elogio | atendimento |
| ab7a1371 | 3 | entrega | entrega |
| 049c8284 | 1 | incompleto | atendimento |
| bd619f83 | 4 | elogio | entrega |
| 647f735a | 3 | outro | diferente |
| 8d1f4df8 | 2 | entrega | atendimento |
| 5a70d3b3 | 2 | diferente | elogio |
| 88ce13e4 | 2 | entrega | entrega |
| 775e02bf | 1 | entrega | entrega |
| d5ff6fd8 | 3 | qualidade | diferente |
| ce1bdb91 | 2 | incompleto | diferente |

## A nota como atalho (D-029)

Acerto por nota e erros na direção da nota. No gold set, todos os itens de nota 5 são `elogio`, então o atalho nota 5 → elogio não é penalizado aqui.

| método | acerto nota 1 | acerto nota 2 | acerto nota 3 | acerto nota 4 | acerto nota 5 | nota 4–5, gold ≠ elogio, previsto elogio | nota 1–2, gold = elogio, previsto ≠ elogio |
|---|---|---|---|---|---|---|---|
| baseline TF-IDF+LR (ajustado no dev) | 0.68 | 0.46 | 0.62 | 0.74 | 1.00 | 7/8 | 1/2 |
| LLM v1 sem raciocínio | 0.75 | 0.69 | 0.69 | 0.93 | 0.97 | 0/8 | 0/2 |

## Observação: causa de entrega × sinal objetivo de entrega

Só descritivo, sem métrica: a flag de atraso foi removida (D-033). O sinal objetivo é retrospectivo: pedido entregue depois da data estimada (`orders.is_late`) ou nunca entregue. Reclamação de demora dentro do prazo e atraso sem reclamação são esperados (taxonomia, `problema_entrega`).

| fonte | itens | previsto/rotulado entrega | com atraso ou sem entrega | atrasados ou sem entrega no total | desses, com causa entrega | concordância (sim/sim + não/não) |
|---|---|---|---|---|---|---|
| gold (não ambíguos) | 137 | 31 | 18/31 | 21 | 18/21 | 88.3% |
| baseline TF-IDF+LR (ajustado no dev) | 150 | 44 | 18/44 | 24 | 18/24 | 78.7% |
| LLM v1 sem raciocínio | 150 | 32 | 18/32 | 24 | 18/24 | 86.7% |

## Observação pós-teste: acerto por área responsável

**Seção adicionada depois de ver o resultado do test**, para descrever erros entre classes da mesma área (defeito, diferente, incompleto e qualidade são todas `vendedor`). Não é métrica de decisão e não estava no protocolo.

| método | acerto de área | acerto de causa | vendedor com área certa |
|---|---|---|---|
| baseline TF-IDF+LR (ajustado no dev) | 0.759 | 0.708 | 28/46 |
| LLM v1 sem raciocínio | 0.927 | 0.810 | 45/46 |
