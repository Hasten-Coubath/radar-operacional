# Radar Operacional

> **Em construção.** A manchete com o resultado do backtest entra aqui na Fase 10, com o número
> vindo de `reports/backtest.md`.

Alerta precoce de problemas operacionais em e-commerce a partir de avaliações de clientes,
usando o dataset público da Olist (2016–2018).

A pergunta que o projeto responde não é "qual a classe desta avaliação?", e sim a pergunta do
gestor de operações: **tem algo quebrando agora, onde, desde quando e qual o impacto?**

## Visão da solução

1. **Classificador de causa.** Cada avaliação com comentário vira um JSON validado (causa,
   gravidade, área responsável, atraso, reembolso/troca, confiança, justificativa), avaliado
   contra um gold set rotulado manualmente.
2. **Detector de anomalias com backtest.** Causas agregadas por semana e segmento (estado,
   categoria, vendedor); o backtest mede com quantas semanas de antecedência o Radar detecta
   incidentes em relação à queda da nota média, e quantos falsos alarmes gera.
3. **Agente investigador com verificação.** Diante de um alerta, um agente com acesso
   somente leitura ao banco investiga via SQL e escreve um briefing; cada número do briefing é
   ligado à query que o gerou e reverificado automaticamente.

## Arquitetura

_(diagrama Mermaid na Fase 10)_

## Resultados

_(Fases 5, 7 e 8)_

## Erros encontrados e correções

_(ver [docs/erros.md](docs/erros.md))_

## Limitações

_(Fase 10)_

## Como rodar

Requer Python 3.11+.

```bash
python -m venv .venv
# Windows
.venv\Scripts\activate
# Linux/macOS
source .venv/bin/activate

pip install -r requirements-dev.txt
cp .env.example .env   # e preencha ANTHROPIC_API_KEY
pytest
```

Dados: baixe o [Brazilian E-Commerce Public Dataset by Olist](https://www.kaggle.com/datasets/olistbr/brazilian-ecommerce)
e coloque os CSVs em `data/raw/`. Os dados não são versionados.

### Modo reprodutível (sem gastar API)

Toda chamada ao LLM passa por um cache em disco (`cache/llm/`). Com `RADAR_LLM_MODE=cache_only`,
o projeto só lê o cache: nenhuma chamada à API é feita e uma requisição ausente gera erro em vez
de custo. O custo acumulado das chamadas reais sai em:

```bash
python -m src.llm
```

## Demonstração

_(GIF do painel)_

## Estrutura

```
config.yaml          modelos, caminhos, preços, modo do LLM
data/raw/            CSVs da Olist (não versionados)
data/processed/      dados limpos e banco SQLite (não versionados)
data/gold/           gold set rotulado manualmente
docs/                taxonomia, decisões, análise de erros
prompts/             prompts versionados
reports/             relatórios de avaliação
src/llm/             cliente de LLM, cache em disco, custo
tests/               pytest
```
