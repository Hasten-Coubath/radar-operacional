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

_(Fases 5, 7 e 8)_

## Erros encontrados e correções

_(ver [docs/erros.md](docs/erros.md))_

## Limitações

_(Fase 10)_

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
