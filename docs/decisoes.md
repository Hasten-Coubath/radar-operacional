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
> Revisado em D-012: com o Ollama, `temperature` e `seed` voltam a ser controláveis.

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
> Substituído por D-010/D-011: o padrão agora é `qwen3:4b` local; os modelos Anthropic
> continuam como alternativa paga comentada em `config.yaml`.

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
> Atualizado em D-013: sem custo de API, o argumento a favor de versionar o cache muda.

- Por ora `cache/` e `logs/` estão no `.gitignore`. Versionar o cache permitiria que qualquer
  pessoa reproduzisse os relatórios sem chave de API, mas ele contém textos de avaliações
  (derivados do dataset da Olist) e vai crescer com a classificação em lote. Decidir antes da
  Fase 3.

## Fase 0.1 — Mudança de premissa: custo zero de API

### D-010 · Provedor padrão: Ollama local; Anthropic fica como opcional
- **Premissa nova:** o projeto deve ter custo zero de API. Hardware de desenvolvimento:
  notebook com RTX 4050 (6 GB de VRAM), 16 GB de RAM, Windows.
- `OllamaProvider` (`src/llm/providers.py`) implementa o mesmo `Protocol` do D-002, usando a API
  `/api/chat` do Ollama via `urllib` da biblioteca padrão (sem dependência nova):
  - saída estruturada: o JSON Schema do Pydantic vai em `format` (decodificação restrita por
    gramática no llama.cpp), e a validação Pydantic local continua valendo (D-006);
  - ferramentas: definições no formato Anthropic (`input_schema`) são convertidas para o formato
    de função do Ollama, e as chamadas voltam como blocos `tool_use`. Resultados (`tool_result`)
    viram mensagens `role: tool`. O formato interno não muda, então o loop do agente (Fase 8)
    funciona com os dois provedores;
  - parâmetro que o provedor não suporta gera erro em vez de ser ignorado: `effort` no Ollama,
    `options` na Anthropic.
- `AnthropicProvider` não foi removido; basta `provider: anthropic` (ou `RADAR_LLM_PROVIDER`) e
  os papéis comentados em `config.yaml`.
- **Trade-off:**

  | | Ollama + qwen3:4b (padrão) | Anthropic (opcional) |
  |---|---|---|
  | Custo em dinheiro | zero | por token |
  | Privacidade | avaliações não saem da máquina | texto enviado a um terceiro |
  | Qualidade esperada | menor (modelo de 4B, quantizado) | maior |
  | Velocidade | limitada pela GPU de 6 GB; lotes grandes levam horas | paralelizável |
  | Reprodutibilidade | `temperature`/`seed` controláveis (D-012) | só via cache (D-005) |

  A perda de qualidade é medida, não presumida: o gold set da Fase 2 vale para qualquer modelo,
  e a Fase 5 reporta os números do modelo local. Se a qualidade ficar inaceitável, a troca de
  modelo é só configuração.

### D-011 · Modelo: `qwen3:4b`, raciocínio desligado na classificação
- `qwen3:4b` foi escolhido pelo usuário (já baixado). Cabe na VRAM de 6 GB com folga para o KV
  cache. O nome fica em `config.yaml` (`roles.<papel>.model`), então trocar não exige mudar código.
- `classifier`: `think: false`, `num_ctx: 4096`, `temperature: 0`, `seed: 42`. O 4096 cobre
  prompt de sistema + taxonomia + avaliação + JSON de saída; o tamanho real do prompt é medido
  na Fase 3, e um prompt que se aproxime do limite gera alerta em vez de truncamento silencioso.
- `agent` (provisório, decidido na Fase 8): `think: true`, `num_ctx: 8192` (o histórico de SQL
  não cabe em 4096), `temperature: 0.6` (recomendação do Qwen3 para o modo de raciocínio, onde a
  decodificação gulosa tende a entrar em repetição).
- **Fase 3:** comparar `qwen3:4b` com e sem `think` no dev set, medindo qualidade (F1 macro,
  por classe) contra segundos por avaliação. Para o modo com raciocínio, `temperature: 0` pode
  causar loops; se acontecer, isso é registrado e o modo é testado com 0,6, como no agente.

### D-012 · Amostragem controlável no Ollama (revisa D-005)
- Com o Ollama, `temperature: 0` + `seed` fixa reduzem bastante a variação entre execuções, mas
  não garantem saída idêntica bit a bit (paralelismo na GPU, versão do Ollama/llama.cpp). O cache
  continua sendo a fonte da reprodutibilidade dos relatórios.
- `think` e `options` fazem parte de `LLMRequest`, logo da chave de cache (D-003): mudar
  `num_ctx`, `temperature` ou `think` gera chave nova.

### D-013 · Custo = tempo de processamento (revisa D-008)
- O custo em dinheiro é zero (preço 0 para `qwen3:4b` em `config.yaml`). Tokens e latência
  continuam registrados por chamada, e o resumo (`python -m src.llm`) passa a ter, como métrica
  principal, `processing_s_live` (soma da latência das chamadas reais), segundos por chamada e
  tokens de saída por segundo, por modelo e por tag. `processing_s_saved_by_cache` é o tempo que
  o cache poupou.
- Para o Ollama também ficam no log `load_s`, `prompt_eval_s` e `eval_s`: a primeira chamada de
  um lote inclui carregar o modelo na GPU e não deve ser confundida com o custo por item.
- Limitação: o Ollama reaproveita o prefixo do prompt já processado, então `input_tokens`
  (`prompt_eval_count`) pode contar menos do que o prompt inteiro em chamadas seguidas.
- Regra de conduta revisada: **"antes de qualquer execução com mais de 50 chamadas ao LLM,
  mostrar a estimativa de tempo de processamento e esperar o OK"** (antes era custo em dinheiro).
  A estimativa usa segundos por chamada medidos numa amostra pequena, mais o pior caso de 2
  tentativas por item (D-006).
- Sobre D-009: sem custo de API, versionar o cache não poupa dinheiro, só tempo de GPU. O risco
  (texto de avaliações no repositório) continua. Decisão mantida para antes da Fase 3.

### D-014 · Teste real com o Ollama no lugar da chamada de fumaça
- `tests/test_ollama_live.py` (marcador `ollama`, fora do `pytest` padrão; rode com
  `pytest -m ollama`): uma classificação estruturada de um único texto escrito para o teste (não
  vem do dataset) e uma chamada de ferramenta. Verifica JSON válido, raciocínio desligado,
  tokens e latência registrados, custo zero e cache hit na repetição. É pulado se o servidor
  não responder ou se o modelo não estiver baixado.

### D-015 · Fase 6: estratégia híbrida como plano padrão
- Classificar o dataset inteiro com um modelo local leva horas. O plano padrão da Fase 6 é
  híbrido: o baseline (Fase 3) classifica tudo, e o LLM só entra onde o baseline tiver baixa
  confiança. O limiar de confiança e a fração enviada ao LLM são definidos no dev set, nunca no
  test set, e o tempo estimado é mostrado antes da execução (D-013).
