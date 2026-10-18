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

## Fase 1 — Dados, banco e taxonomia

Números citados abaixo vêm de `reports/fase1_dados.md` (`python -m src.data.stats`).

### D-016 · Modelo de dados: avaliação única, vínculo N:N com pedidos, segmentos materializados
- No CSV, 802 `review_id` aparecem em 2–3 linhas, cada uma com outro pedido do mesmo cliente
  e conteúdo idêntico (conferido). É **uma** avaliação cobrindo vários pedidos. Por isso:
  `reviews` tem uma linha por `review_id` (99.173), e `review_orders` guarda o vínculo
  (100.000 pares). Os 555 pedidos com mais de uma avaliação mantêm todas: são avaliações
  distintas, em datas diferentes.
- `order_segments`: estado do cliente (1 por pedido), mais categorias e vendedores distintos
  dos itens. Pedido com vários vendedores (1.278) ou categorias (727) pertence a todos eles;
  pedido sem itens (775, quase todos `unavailable`/`canceled`) só tem estado. A view
  `review_segments` conta cada avaliação uma vez por segmento.
- Alternativa descartada: atribuir o pedido só ao item mais caro. Seria arbitrário, e o
  caso afeta só 1,3% dos pedidos.
- "Estado" é o do **cliente** (destino da entrega), onde aparecem os problemas de logística.
  O estado do vendedor fica em `sellers` para o agente.

### D-017 · Sinal objetivo de atraso
- `delay_days` = data de entrega ao cliente − data estimada, em dias de calendário. A data
  estimada não tem hora, e entregar no próprio dia é pontual. `is_late = delay_days > 0`. Os
  dois são nulos sem data de entrega (2.965 pedidos), inclusive os 8 `delivered` sem data.
  Os 6 `canceled` com data de entrega ficam com o sinal calculado e o status preservado.
- **Resultado:** 6,8% dos pedidos entregues atrasam. Nota média das avaliações de pedidos
  atrasados: 2,26, contra 4,28 no prazo. Pedidos sem entrega têm nota 1,76.
- Inconsistências mantidas e contadas, não corrigidas: 23 pedidos com coleta pela
  transportadora depois da entrega ao cliente (não usamos essa data).
- **Limitação para o backtest:** o atraso só é observável depois da data estimada, ou na
  entrega, se for antes. A Fase 7 deve usar "atrasado e já conhecido na semana t". As datas
  necessárias estão no banco.

### D-018 · Comentário elegível para classificação
- `has_comment = 1` quando a mensagem, depois de normalizada (quebras de linha unificadas,
  espaços aparados), tem **pelo menos uma letra ou dígito**. Isso exclui 150 mensagens só
  com espaço ou pontuação ("."). Ficam **41.281 avaliações (41,6%)**.
- Avaliações só com título (1.733) **não** entram, porque o plano pede "comentário de texto não
  vazio" e o título é curto e genérico. Quando existe, o título é passado como contexto junto
  com a mensagem.
- Mojibake: 8 mensagens com padrões de codificação quebrada. Não tratadas.

### D-019 · Semana e disponibilidade da avaliação: **divergência com o plano, decisão pendente**
- O plano diz para usar a data de criação da avaliação no backtest. Nos dados,
  `review_creation_date` é a **data de envio da pesquisa** (88,8% exatamente 1 dia após a
  entrega), e o texto só existe na **resposta** (`review_answer_ts`). A resposta chega com
  mediana de 1,7 dia depois do envio, p95 de 7 dias e p99 de 22,5 dias.
- Usar a data de criação deixaria a semana *t* ver respostas dadas em *t + 1* ou depois: um
  vazamento pequeno na mediana, mas real na cauda. **Proposta:** a disponibilidade de uma
  avaliação no backtest é `review_answer_ts` (`answered_week`). O banco guarda as duas
  semanas (`created_week`, `answered_week`) para que a escolha seja só de configuração.
  **Aguarda aprovação do usuário** antes da Fase 7.
- Semana = segunda-feira (`YYYY-MM-DD`).

### D-020 · Seleção e censura no fim do dataset
- Todo pedido do dataset tem avaliação (0 sem avaliação), e a última pesquisa foi enviada em
  2018-08-31. O dataset é, na prática, "pedidos que receberam pesquisa até 31/08/2018". Pedidos
  atrasados que seriam entregues depois disso não aparecem, e a taxa de atraso das últimas
  semanas cai artificialmente (0% nas semanas estimadas de setembro de 2018).
- **Janela de análise:** semanas de resposta de 2017-02-06 a 2018-08-27 (82 semanas). Fora
  dela, o volume tem menos de 100 comentários por semana (início em 2016) ou a semana está
  incompleta (depois do último envio).
- **Atraso por semana estimada:** só até 2018-08-13 (corte − 14 dias; 78,8% dos atrasos têm
  até 14 dias). As últimas semanas ainda podem estar levemente subestimadas.
- **Limitação que não dá para corrigir:** a inclusão de um pedido no dataset depende de um
  evento futuro (ter recebido a pesquisa). O backtest herda essa seleção; vai para as
  Limitações do README.

### D-021 · Volume por segmento: vendedor semanal é esparso demais (**ponto para a Fase 7**)
- Na janela de análise, entre os segmentos com volume médio semanal de comentários ≥ 5:
  13 de 27 estados (93,9% dos comentários), 21 de 74 categorias (88,5%) e só 11 de 3.067
  vendedores (15,8%).
- Considerando só comentários com nota ≤ 2, nenhum vendedor chega a 5 por semana, e só 16
  chegam a 1 por semana.
- **Consequência:** detecção semanal por vendedor, no formato do plano, só é viável para
  poucos vendedores. Proposta para a Fase 7, sem decidir agora:
  - estado e categoria em janela semanal, com um mínimo de volume;
  - vendedor em janela móvel de 4 semanas, restrito aos vendedores acima de um limiar de
    volume fixado antes de ver os resultados;
  - abaixo do limiar, o segmento não gera alerta, e isso fica registrado como cobertura.
- Variações bruscas de volume total (semanas de 2017-04-24, 2018-05-28 e 2018-07-16, com
  menos da metade das vizinhas) indicam que o detector deve usar **taxas** (proporção de cada
  causa), não contagens absolutas.

### D-022 · Taxonomia v1 e amostra de validação
- Leitura de 100 comentários (20 por nota, semente 42). Nomes das 8 classes mantidos;
  definições, fronteiras e regras em `docs/taxonomia.md`.
- Principal ajuste: `nao_recebido` fica restrita a falha definitiva (extravio, "consta
  entregue", cancelamento, falta de estoque), e "ainda não recebi" vai para `atraso_entrega`.
  Evidência: 79,2% dos pedidos com expressões do tipo "não recebi" foram entregues depois.
- Os IDs da amostra (`data/samples/amostra_taxonomia.csv`) são **excluídos do gold set**,
  porque os exemplos da taxonomia, que podem inspirar prompts, saem dela.

### D-023 · O que é versionado
- **Não versionado:** `data/processed/radar.db`, derivado dos dados brutos (contém os
  textos). É regenerado de forma determinística por `python -m src.data.make_db`: duas
  execuções deram o mesmo SHA-256. O banco guarda em `meta` o SHA-256 de cada CSV de
  origem.
- **Versionado:**
  - `reports/fase1_dados.md` e `reports/figures/`, que têm só agregados;
  - `data/samples/amostra_taxonomia.csv`, só IDs e notas;
  - os exemplos citados em `docs/taxonomia.md`, trechos curtos que o plano exige (o dataset é
    CC BY-NC-SA 4.0).
