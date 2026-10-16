# Log de decisões

Cada entrada registra o que foi decidido, por quê e o que foi deixado de lado.

## Fase 0 — Setup

### D-001 · Ambiente: `venv` + `requirements.txt` com versões fixas
- `uv` não está instalado na máquina de desenvolvimento; `venv` vem com o Python e não exige
  ferramenta extra para quem clonar o repositório.
- Versões exatas (`==`) em `requirements.txt` (execução) e `requirements-dev.txt` (pytest,
  ruff, mypy) para reprodutibilidade. Desenvolvido em Python 3.12.10; alvo declarado `>=3.11`.

### D-002 · O código do projeto não importa a SDK do provedor diretamente
- `src/llm/providers.py` define um `Protocol` (`LLMProvider.generate(LLMRequest) -> LLMResponse`)
  e a implementação `AnthropicProvider`. O resto do projeto usa só `src.llm.client.LLMClient`.
- Trocar de provedor significa escrever outro `LLMProvider`; os testes usam um provedor falso.

### D-003 · Chave de cache = SHA-256 de tudo que influencia a saída
- JSON canônico (chaves ordenadas) de: provedor, modelo, prompt de sistema, mensagens (a
  entrada), ferramentas, schema de saída, `max_tokens` e `effort`. Mudar qualquer um gera chave
  nova; mudar só a ordem de chaves de um dict não.
- Cada entrada do cache guarda a requisição completa além da resposta, para auditoria
  ("qual prompt gerou esta classificação?").
- Respostas com `stop_reason` de recusa ou truncamento também vão para o cache, para que o replay
  reproduza fielmente o que aconteceu. Exceções (rede, 5xx) não são cacheadas.

### D-004 · Modo `cache_only` para reprodução sem custo
- `llm.mode: cache_only` (ou `RADAR_LLM_MODE=cache_only`) faz qualquer miss levantar
  `CacheMissError` em vez de chamar a API. É o modo usado para regenerar relatórios.

### D-005 · Sem `temperature`: reprodutibilidade vem do cache, não da amostragem
- Os modelos atuais da Anthropic usados aqui não aceitam parâmetros de amostragem fora do padrão,
  então não há como "fixar" a saída do modelo. Uma segunda execução sem cache pode dar outra
  resposta; por isso os números dos relatórios vêm sempre de execuções registradas em cache.
- Consequência para a avaliação: a variância entre execuções não é medida por padrão. Se for
  relevante (Fase 3/4), medimos explicitamente repetindo uma amostra pequena.

### D-006 · Saída estruturada: decodificação restrita + validação Pydantic local
- O schema Pydantic é enviado como `output_config.format` (JSON Schema estrito), o que restringe
  a forma do JSON. Restrições de valor (ex.: `confianca` entre 0 e 1) não são impostas pela API;
  a SDK as move para a descrição do campo. Quem garante o conteúdo é a validação Pydantic local.
- Em resposta inválida, `generate_structured` reenvia a conversa com a resposta anterior e o
  erro de validação (padrão: 2 tentativas no total). Cada retentativa é uma requisição distinta,
  então também fica em cache e é reproduzível. Sem sucesso, `parsed=None` → revisão humana.
- A taxa de falha de schema é medida na Fase 3 a partir de `StructuredResult.errors`.

### D-007 · Modelos por papel (provisório)
- `classifier`: `claude-haiku-5-5` (USD 0,10 / 0,50 por milhão de tokens de entrada/saída), o
  menor e mais barato, como pede o plano. `effort: low` como ponto de partida; o efeito do nível
  de esforço na qualidade é medido na Fase 3 antes de virar padrão.
- `agent`: `claude-opus-5-5` como placeholder. A escolha final (Opus 5.5 × Sonnet 5.5) será
  justificada na Fase 8 com custo e taxa de afirmações verificadas.

### D-008 · Custo estimado e registro de uso
- Preços em `config.yaml` (USD/milhão de tokens). Tokens de cache de prompt sem preço próprio são
  cobrados ao preço de input. Modelo sem preço configurado → custo `null` e contagem em
  `calls_without_price`, para não esconder lacunas.
- `logs/llm_usage.jsonl` registra toda chamada, inclusive cache hits: tokens, latência,
  `cost_usd_live` (o que a resposta custou na API) e `cost_usd_spent` (zero em cache hit).
  `python -m src.llm` soma o custo efetivamente gasto.

### D-009 · Cache e logs fora do git (pendente de decisão)
- Por ora `cache/` e `logs/` estão no `.gitignore`. Versionar o cache permitiria que qualquer
  pessoa reproduzisse os relatórios sem chave de API, mas ele contém textos de avaliações
  (derivados do dataset da Olist) e vai crescer com a classificação em lote. Decidir antes da
  Fase 3.
