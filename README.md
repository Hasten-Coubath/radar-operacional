# Radar Operacional

> **Em construção.** A manchete com o resultado do backtest entra aqui na Fase 10, com o número
> vindo de `reports/backtest.md`.

Alerta precoce de problemas operacionais em e-commerce a partir de avaliações de clientes,
usando o dataset público da Olist (2016–2018).

A pergunta que o projeto responde não é "qual a classe desta avaliação?", e sim a pergunta do
gestor de operações: **tem algo quebrando agora, onde, desde quando e qual o impacto?**

## Visão da solução

1. **Classificador de causa.** Cada avaliação com comentário vira um JSON validado (causa,
   gravidade, confiança, justificativa; a área responsável vem da causa), avaliado contra um
   gold set rotulado manualmente. Taxonomia v1.1 em [docs/taxonomia.md](docs/taxonomia.md).
2. **Detector de anomalias com backtest.** Causas agregadas por semana e segmento (estado e
   categoria; vendedor é aprofundamento do agente); o backtest mede com quantas semanas de antecedência o Radar detecta
   incidentes em relação à queda da nota média, e quantos falsos alarmes gera.
3. **Agente investigador com verificação.** Diante de um alerta, um agente com acesso
   somente leitura ao banco investiga via SQL e escreve um briefing; cada número do briefing é
   ligado à query que o gerou e reverificado automaticamente.

## LLM local, custo zero

Todo o uso de LLM roda localmente com o [Ollama](https://ollama.com) e o modelo `qwen3:4b`
(alvo: RTX 4050 com 6 GB de VRAM). O custo em dinheiro é zero e as avaliações não saem da
máquina. Em troca, o modelo é menor que os de API e cada chamada custa segundos de GPU. Por isso
a métrica de custo nos relatórios é o **tempo de processamento**, e a estratégia de
classificação do dataset inteiro é escolhida na Fase 6 com o tempo medido. O provedor da Anthropic continua disponível como opção paga. Detalhes e trade-offs
em [docs/decisoes.md](docs/decisoes.md) (D-010 a D-015).

## Arquitetura

_(diagrama Mermaid na Fase 10)_

## Resultados

### Classificador de causa (Fase 5, test set, avaliação única)

| | macro-F1 [IC 95%] | acurácia | s/item |
|---|---|---|---|
| **LLM local `qwen3:4b`, sem raciocínio** | **0,657** [0,518; 0,754] | 0,810 | 1,7 s |
| baseline TF-IDF + regressão logística | 0,422 [0,336; 0,492] | 0,708 | < 1 ms |

Fonte: `reports/fase5_test.md` (137 itens não ambíguos, 8 classes). No dev, o LLM tinha 0,846;
a queda está explicada nas Limitações. Medi se o modo com raciocínio valia a pena: no dev ele
empatou dentro do ruído (macro-F1 0,823 contra 0,846) e custou cerca de 20 vezes mais tempo
(`reports/fase3_dev.md`).

_(Detector e agente: Fases 7 e 8.)_

## Erros encontrados e correções

_(ver [docs/erros.md](docs/erros.md))_

## Limitações

_(Lista parcial; completada na Fase 10.)_

- **Só comentários com nota ≤ 3 são classificados** (D-039). Notas 4–5 ficam
  `nao_classificado`, não `elogio`. Estimativa no dev: perde-se cerca de 12% do volume de
  problemas e até cerca de 84% das reclamações de atendimento, que aparecem em notas altas
  (estimativa incerta: 5 itens no gold set). O Radar vê mal os problemas de atendimento.
- **Queda do classificador do dev para o test** (macro-F1 0,846 → 0,657; `reports/fase5_test.md`).
  - Quase toda a queda está em `qualidade_insatisfatoria`, com recall de 0,17 no test: os
    itens vão para `defeito` ou `diferente`.
  - A causa provável é a taxonomia: a classe nasceu do remapeamento mecânico de uma nota da
    rotulagem (D-034) e conflita com a definição escrita (D-041).
  - Some-se a isso a variância de um dev de 96 itens.
  - Por isso, o detector trata as três classes de produto como uma família só (D-047). Elas são
    todas da área `vendedor`, em que o acerto de área no test é de 45 em 46 (observação
    pós-teste).
- **Seleção do dataset:** só há pedidos que receberam pesquisa até 31/08/2018 (D-020).
- **Área responsável por mapeamento fixo** (D-027, D-034): avaria no transporte cai em
  `vendedor`, e cancelamento por falta de estoque cai em `logistica`.

## Como rodar

Requer Python 3.11+ e, para as etapas com LLM, o [Ollama](https://ollama.com/download).

```bash
python -m venv .venv
# Windows
.venv\Scripts\activate
# Linux/macOS
source .venv/bin/activate

pip install -r requirements-dev.txt
pytest                 # testes rápidos, sem LLM

ollama pull qwen3:4b   # ~2,5 GB
pytest -m ollama       # teste real com o modelo local (um item)
python -m src.llm.bench  # segundos por chamada, com e sem raciocínio
```

O `.env` é opcional (veja `.env.example`): só é preciso para sobrescrever configurações ou usar
o provedor pago (`RADAR_LLM_PROVIDER=anthropic` + `ANTHROPIC_API_KEY`).

Dados: baixe o [Brazilian E-Commerce Public Dataset by Olist](https://www.kaggle.com/datasets/olistbr/brazilian-ecommerce)
e coloque os CSVs em `data/raw/`. Os dados não são versionados.

```bash
python -m src.data.make_db           # data/processed/radar.db (determinístico, ~20 s)
python -m src.data.stats             # reports/fase1_dados.md + figuras
python -m src.data.sample_taxonomy   # IDs da amostra usada para validar a taxonomia
```

Gold set (rotulagem manual, sem LLM):

```bash
python -m src.labeling.gold          # sorteia amostra e divisão dev/test (uma vez só)
streamlit run src/labeling/app.py    # ferramenta de rotulagem (http://127.0.0.1:8501)
python -m src.labeling.migrate --force  # rótulos v1 -> taxonomia v1.1 (regras mecânicas)
python -m src.labeling.report        # reports/gold_set.md: distribuição dos rótulos
```

Plano de fases e regras do projeto: [docs/plano.md](docs/plano.md).

Classificador LLM (Fase 3; só o dev, o test set é bloqueado até a Fase 5):

```bash
python -m src.classifier.run --role classifier --limit 5         # medição de tempo em 5 itens
python -m src.classifier.run --role classifier_think --limit 5   # idem, com raciocínio
python -m src.classifier.run --role classifier --confirm         # dev inteiro (> 50 chamadas)
```

### Modo reprodutível (sem rodar o modelo)

Toda chamada ao LLM passa por um cache em disco (`cache/llm/`). Com `RADAR_LLM_MODE=cache_only`,
o projeto só lê o cache: nenhum modelo é chamado e uma requisição ausente gera erro. O tempo de
processamento acumulado, além de tokens e custo em dinheiro (zero com o Ollama), sai em:

```bash
python -m src.llm
```

## Demonstração

_(GIF do painel)_

## Estrutura

```
config.yaml          provedor e modelo do LLM, caminhos, modo do cache
data/raw/            CSVs da Olist (não versionados)
data/processed/      dados limpos e banco SQLite (não versionados)
data/gold/           gold set rotulado manualmente
data/samples/        IDs de amostras auxiliares (sem texto)
docs/                plano, taxonomia, decisões, análise de erros
prompts/             prompts versionados
reports/             relatórios de avaliação
src/data/            carga, limpeza, sinal de atraso (inclusive point-in-time), banco, estatísticas
src/labeling/        amostra do gold set, ferramenta de rotulagem, migração v1.1, relatório
src/taxonomy.py      classes e mapeamento causa -> área
src/llm/             cliente de LLM (Ollama/Anthropic), cache em disco, uso
tests/               pytest
```
