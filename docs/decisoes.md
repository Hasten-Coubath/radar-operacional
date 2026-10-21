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
> **Resolvido em D-035:** cache e logs não são versionados; as previsões por `review_id`, sem
> texto, são.
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
> Alternativas a avaliar na Fase 6: classificar tudo com o LLM (D-032) e classificar só
> notas ≤ 3 (cobertura por classe em `reports/gold_set.md`).
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
- **Revisado em D-025**, com a versão point-in-time para o backtest.
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

### D-019 · Semana e disponibilidade da avaliação: divergência com o plano
> **Decidido pelo usuário (2026-10-18):** no backtest, a avaliação fica disponível em
> `review_answer_ts` (`answered_week`).

- O plano diz para usar a data de criação da avaliação no backtest. Nos dados,
  `review_creation_date` é a **data de envio da pesquisa** (88,8% exatamente 1 dia após a
  entrega), e o texto só existe na **resposta** (`review_answer_ts`). A resposta chega com
  mediana de 1,7 dia depois do envio, p95 de 7 dias e p99 de 22,5 dias.
- Usar a data de criação deixaria a semana *t* ver respostas dadas em *t + 1* ou depois: um
  vazamento pequeno na mediana, mas real na cauda. **Proposta:** a disponibilidade de uma
  avaliação no backtest é `review_answer_ts` (`answered_week`). O banco guarda as duas
  semanas (`created_week`, `answered_week`) para que a escolha seja só de configuração.
  Aprovado (ver nota acima).
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

### D-021 · Volume por segmento: vendedor semanal é esparso demais
> **Decidido pelo usuário (2026-10-18):** a detecção da Fase 7 usa só **estado e categoria**,
> com o limiar de volume de D-026. Vendedor deixa de ser segmento de detecção e passa a ser
> dimensão de aprofundamento do agente investigador (Fase 8). A proposta abaixo, de janela
> de 4 semanas para vendedor, fica descartada.

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

## Fase 1.1 — Correções aprovadas pelo usuário antes da Fase 2

### D-024 · Ollama em funcionamento: medições e duas correções
- Ambiente: Ollama 0.40.6 e `qwen3:4b` (Q4_K_M, 2,5 GB). `pytest -m ollama`: 2 de 2
  passaram (classificação estruturada e chamada de ferramenta).
- Benchmark `python -m src.llm.bench`: 5 textos sintéticos, modelo já carregado na GPU.

  | | Sem raciocínio (`think=false`) | Com raciocínio (`think=true`) |
  |---|---|---|
  | s/chamada, mediana | 0,47 (mín 0,41, máx 0,57) | 18,51 (mín 11,49, máx 30,29) |
  | Tokens de saída, mediana | 23 | 1.040 |
  | JSON válido | 5 de 5 | 5 de 5 |

  A 1ª chamada inclui carregar o modelo (`load_s` ≈ 2,2 s).
- **Correção 1: `localhost` → `127.0.0.1`.** No Windows, `localhost` tenta IPv6 (`::1`)
  primeiro, e cada requisição perdia 2,05 s (medido: 2,052 s contra 0,001 s com
  `127.0.0.1`). Sem a correção, a chamada sem raciocínio levava 2,6 s, quase 6 vezes mais.
- **Correção 2: raciocínio vazando para o texto.** Com ferramentas e `think=false`, o qwen3
  escreveu o raciocínio no `content`, terminando em `</think>`. O provedor agora move esse
  trecho para um bloco `thinking`; um teste unitário e o teste real verificam. Na
  classificação, sem ferramentas, isso não ocorreu.
- **Ordem de grandeza** (não é a estimativa formal; o prompt real da Fase 3 será maior):
  - 41.281 comentários × 0,47 s ≈ 5,4 h sem raciocínio;
  - × 18,5 s ≈ 212 h com raciocínio;
  - o dev set com raciocínio leva ≈ 31 min.

  O modo com raciocínio só é viável no dev set, o que reforça a estratégia híbrida (D-015).

### D-025 · Sinal de atraso point-in-time para o backtest (revisa D-017)
- **Regra (definida pelo usuário):** na semana *t*, um pedido está atrasado se a data
  estimada já passou e ele não tinha sido entregue até *t*, ou se foi entregue com atraso
  até *t*. A data de entrega só é usada se for anterior ao instante de avaliação.
  `order_status` nunca é usado, porque não sabemos quando o status mudou.
- **Implementação** em `src/data/point_in_time.py`:
  - `delay_status_as_of(orders, as_of)`: devolve um de 5 estados;
  - `weekly_due_late_rate`: coorte com data estimada de *t* a *t* + 6, avaliada em *t* + 7
    dias, opcionalmente por segmento.

  São 13 testes, incluindo a propriedade de que trocar entregas posteriores a `as_of` não
  muda o resultado em `as_of`.
- **Auditoria da Fase 1.** `orders.is_late`, que usa a data final de entrega, apareceu em
  dois tipos de uso:
  - nas seções 6, 9.2–9.4 e 10, que são descrições retrospectivas e foram mantidas, agora
    marcadas como tal;
  - na série semanal (gráfico e tabela 9.1), que foi trocada pela versão point-in-time.
- **Diferença entre as séries.** Para a coorte da semana estimada, o atraso já está decidido
  em *t* + 7. As duas séries só diferem no denominador: na point-in-time, pedidos nunca
  entregues contam como atrasados.
  - Já com a exclusão de D-030: diferença média de +2,38 p.p. por semana, máxima de
    +10,71 p.p., correlação de 0,967 (`reports/fase1_dados.md`, seção 11).
  - Antes da exclusão: +3,19 p.p. de média e correlação de 0,948.
- **A conclusão "mesma semana" se mantém e fica mais forte.** Nos 3 eventos, a menor nota
  média e a maior fração de notas ≤ 2 caem na mesma semana do pico de atraso point-in-time
  (dez/2017) ou uma semana antes (mar–abr/2018 e mai–jun/2018). A correlação mais negativa
  entre atraso em *t* e nota em *t* + *k* está em *k* = −1 (−0,772), próxima de *k* = 0
  (−0,744); antes de D-030, eram −0,765 e −0,757. No agregado nacional, a nota não atrasa
  em relação ao sinal objetivo.
  Hipótese não verificada: avaliações de pedidos atrasados de coortes anteriores chegam
  enquanto a coorte da semana ainda está vencendo.
- **Ponto que estava em aberto, resolvido em D-030:**
  - Os pedidos nunca entregues incluem 686 sem itens registrados (artefato do dataset, quase
    todos `unavailable`) e cancelados.
  - Eles são 3% a 7% da coorte em 2017 e 1,4% a 2,8% em 2018, o que eleva o nível da série
    em 2017.
  - **Proposta:** excluir do sinal os pedidos sem itens. Como os itens são registrados na
    compra, isso não gera vazamento.
  - Aprovado e aplicado (D-030).

### D-026 · Definição de incidente e linhas de base, fixadas antes da Fase 7
> **Nomes de classe atualizados por D-034 (taxonomia v1.1).** No diagnóstico (item 1 de
> "Se a antecedência for pequena"), a causa esperada no tipo A passa a ser
> `problema_entrega`, que reúne `atraso_entrega` e `nao_recebido`; no tipo B, as demais
> causas, incluindo `qualidade_insatisfatoria`. Definição de incidente, parâmetros, períodos e
> métricas não mudam. Nenhum detector existia na data da mudança.
Escrita antes de existir qualquer detector. Qualquer mudança posterior exige nova entrada
com o motivo e os resultados antes e depois da mudança.

**Segmentos monitorados (D-021):**
- Estado do cliente e categoria, com volume médio ≥ 5 comentários por semana na janela de
  2017-02-06 a 2018-08-27. São 13 estados e 21 categorias (`reports/fase1_dados.md`,
  seção 8).
- Usar o volume da janela inteira é uma escolha retrospectiva. Ela afeta quais segmentos são
  monitorados, não quando eles alertam.

**Congelamento.** Versão final registrada em 2026-10-18, antes de existir qualquer detector.
Os parâmetros abaixo são fixos: não são ajustados em nenhum período, nem de calibração, nem
de avaliação. Uma versão anterior desta entrada usava outro corte de períodos (calibração até
2017-10-30); foi trocada antes de qualquer detector existir, pelo motivo explicado em
"Períodos".

**Períodos** (fixos; não serão alterados depois de ver resultados):

| Período | Semanas (segunda-feira) | Uso |
|---|---|---|
| Calibração | 2017-02-06 a 2017-12-25 (47 semanas) | ajustar limiares e hiperparâmetros do detector e das linhas de base |
| Avaliação | 2018-01-01 a 2018-08-13 (33 semanas) | medir recall, antecedência e falsos alarmes; nada é ajustado aqui |

- **Por que o corte por ano:** a versão anterior (calibração até 2017-10-30) foi escolhida
  sabendo onde caíam os eventos vistos na Fase 1. O corte por ano não depende dessa
  informação. Consequência aceita: o evento de dez/2017 fica na calibração.
- **O fim** em 2018-08-13 é o da série de atraso sem censura (D-020).
- **Incidente que cruza o corte** pertence ao período da sua semana de início. Incidentes
  iniciados na calibração ficam fora das métricas de avaliação. As semanas deles que caem em
  2018 também não contam para falsos alarmes: alertas ali não são falsos nem acertos.
- **Histórico:** detectores e linhas de base podem usar semanas de calibração como histórico
  ao rodar na avaliação, sempre point-in-time.
- **O que é escolhido só na calibração:** limiares, comprimento de janela, método estatístico
  e quais causas compõem cada sinal. O conjunto de avaliação é usado uma única vez, ao final
  da Fase 7.

**Gabarito × detectores.** Os rótulos de incidente são gabarito: podem usar o histórico
inteiro, porque nenhum detector os vê. Detectores e linhas de base usam só dados
point-in-time (D-019, D-025, D-030).

**"Acima do normal": definição numérica.** Para uma série de proporção *p* com *n*
observações na semana *t* do segmento *s*:

1. **Referência:** *b* = mediana de *p* nas semanas *u* ∈ [*t* − 26, *t* − 1] com *n* ≥
   *n_min*.
   - Exige no mínimo 8 dessas semanas; sem elas, a semana *t* não pode ser anômala.
   - Como só olha para trás, a referência também é point-in-time.
2. **Anômala:** a semana é anômala se valem as três condições:
   - *n* ≥ *n_min*;
   - *p* > max(2·*b*, *b* + 0,05);
   - *L* > *b*, em que *L* é o limite inferior do intervalo de Wilson de 95% para *p*:

     *L* = (*p* + *z*²/2*n* − *z*·√(*p*(1 − *p*)/*n* + *z*²/4*n*²)) / (1 + *z*²/*n*),
     com *z* = 1,96.
3. **Volume baixo:** semanas com *n* < *n_min* não são anômalas e contam como semanas normais
   para a regra de junção.

Limiar de *p* conforme a referência (antes do teste de Wilson):

| *b* | 0% | 3% | 5% | 10% | 20% |
|---|---|---|---|---|---|
| limiar | 5% | 8% | 10% | 20% | 40% |

Por que esses parâmetros (escolhidos a priori, não ajustados):
- **2× com piso de 5 p.p.:** exige um efeito relativo e um efeito absoluto mínimos.
- **Wilson:** evita disparos por volume baixo.
- **Mediana de 26 semanas:** cobre meio ano de "normal" e resiste a incidentes de até cerca
  de 12 semanas.

**Incidente:** sequência de ≥ 2 semanas anômalas consecutivas, do mesmo segmento e tipo.
Sequências separadas por uma única semana não anômala são unidas. O início é a primeira
semana anômala; o fim, a última.

| Tipo | *p* | *n* | *n_min* |
|---|---|---|---|
| A — atraso | taxa de atraso point-in-time da coorte com data estimada na semana (D-025, D-030) | pedidos da coorte | 30 |
| B — insatisfação não ligada a atraso | fração de notas ≤ 2 entre as avaliações respondidas na semana de pedidos entregues no prazo (`is_late = 0`; retrospectivo, permitido no gabarito) | essas avaliações | 20 |

**Métodos comparados.** Todos usam a mesma regra de alerta e são calibrados para o mesmo
orçamento de falsos alarmes:
- **Radar:** proporção de cada causa classificada, por segmento e semana.
- **B1, sinal ingênuo do plano:** queda da nota média do segmento (avaliações respondidas na
  semana).
- **B2, alternativa mais simples:** fração de avaliações com nota ≤ 2, ou seja, a contagem de
  reclamações normalizada pelo volume.
- **B3, referência:** taxa de atraso point-in-time.
  - No tipo A, é circular (é ela que define o incidente), então não compete em antecedência.
  - No tipo B, mostra o que um monitor de logística não vê.

**Orçamento de falsos alarmes:**
- Na calibração (2017), cada método usa o limiar mais sensível que mantém no máximo 1
  falso alarme por semana, somando todos os segmentos monitorados. Esse limiar é levado sem
  mudança para a avaliação (2018).
- Também é reportada a curva recall × falsos alarmes por semana para vários limiares, para
  que a conclusão não dependa de um único ponto.

**Métricas** (só no período de avaliação, 2018):
- **Casamento:** um alerta do método *m* no segmento *s* na semana *w* casa com o incidente
  *i* de *s* se *w* ∈ [início − 4, fim]. A semana de detecção *d_m(i)* é a do primeiro alerta
  que casa.
- **Recall por tipo:** incidentes detectados / incidentes.
- **Antecedência do Radar sobre B1:** *d_B1(i)* − *d_Radar(i)*, em semanas, onde positivo
  significa que o Radar detectou antes. Só vale quando os dois detectam; os incidentes que só
  um método detecta são contados à parte, sem imputar valor. Também é reportado início −
  *d_m(i)*.
- **Falsos alarmes por semana:** alertas que não casam com nenhum incidente do mesmo
  segmento (de qualquer tipo) em [início − 4, fim + 2], divididos pelas semanas de avaliação.

**Se a antecedência for pequena.** Antecedência pequena é definida como mediana de Radar −
B1 ≤ 1 semana nos incidentes do tipo A. É o esperado pela seção 11 da Fase 1. Nesse caso, o
projeto avalia e reporta como valor principal:
1. **Diagnóstico:** nos incidentes detectados, a causa dominante no alerta do Radar bate com
   o tipo? No tipo A, `atraso_entrega` ou `nao_recebido`; no tipo B, as demais causas. B1 e
   B2 não informam causa.
2. **Problemas que não são de atraso:** recall do Radar nos incidentes do tipo B, contra B1,
   B2 e B3. Por construção, B3 não vê esses incidentes.
3. **Caso `5dceca12`:** vendedor de SP em abr/2018, com 50% de notas ≤ 2 e atraso de 15,6%,
   próximo dos 13% nacionais.
   - Como vendedor não é segmento de detecção, o caso é examinado na Fase 7 pela categoria do
     vendedor: há alerta? há incidente do tipo B?
   - Na Fase 8, é examinado como aprofundamento do agente a partir do alerta da categoria.
   - Se não houver alerta na categoria, isso é reportado como limitação de cobertura.

### D-027 · Área responsável: mapeamento fixo causa → área
> **Revisado em D-034:** tabela da taxonomia v1.1 lá. A tabela abaixo é a da v1.
A área não é rotulada nem prevista; é derivada da causa (`src/taxonomy.py`, `AREA_BY_CAUSE`).

| Causa | Área |
|---|---|
| `atraso_entrega`, `nao_recebido` | `logistica` |
| `produto_defeituoso_ou_danificado`, `produto_diferente_do_anunciado`, `pedido_incompleto_ou_errado` | `vendedor` |
| `problema_atendimento_ou_comunicacao` | `atendimento` |
| `elogio` | `nenhuma` |
| `outro`, `ambiguo` | `indefinida` |

**Limitações conhecidas:**
- Avaria no transporte cai em `produto_defeituoso_ou_danificado`, que leva a `vendedor`,
  embora a responsabilidade seja da logística.
- Cancelamento ou falta de estoque cai em `nao_recebido`, que leva a `logistica`, embora a
  responsabilidade seja do vendedor.

## Fase 2 — Ferramenta de rotulagem e gold set

### D-028 · Gold set: amostra, divisão e rotulagem
> Revisado: `menciona_atraso` e `pede_reembolso_troca` removidos (D-033); classes da
> taxonomia v1.1 e causa secundária fora das métricas (D-034).
**Amostra e divisão:**
- 250 avaliações com comentário, 50 por nota, semente 42. Os 100 IDs da amostra da
  taxonomia foram excluídos (sobreposição verificada: 0).
- O universo é o de todas as avaliações com comentário, não só a janela de análise.
- Divisão estratificada de 20 dev e 30 test por nota (100 dev, 150 test), sorteada e gravada
  em `data/gold/gold_sample.csv` antes da rotulagem. O script se recusa a sobrescrever o
  arquivo.
- A ordem de apresentação mistura dev e test, para que quem rotula não saiba o split.

**Campos que o usuário rotula:**
- causa principal: uma das 8 classes ou "ambíguo / não sei";
- causa secundária (opcional);
- `menciona_atraso`;
- `pede_reembolso_troca`;
- nota livre, com até 200 caracteres.

`gravidade` não é rotulada, e a área vem de D-027.

**A ferramenta:**
- Mostra a nota, o título e a mensagem, mas não os dados do pedido nem o sinal de atraso.
- Não chama nenhum LLM, porque pré-rotular é proibido.
- `.streamlit/config.toml` restringe o servidor a `127.0.0.1`, para que os textos não fiquem
  expostos na rede local.

**Uso nas métricas:**
- As métricas são reponderadas pela distribuição real das notas entre os comentários. O peso
  de cada nota é a participação dela no universo dividida por 0,2 (`src/labeling/report.py`).
- Itens "ambíguo" ficam fora das métricas principais e são reportados à parte (D-031).

**Versionamento:** `data/gold/` é versionado, com IDs e rótulos e sem textos.

### D-029 · A nota é entrada do classificador
- **Decidido pelo usuário:** a nota é mostrada a quem rotula e também é entrada do
  classificador.
- **Risco a medir na Fase 3:** o modelo pode usar a nota como atalho (por exemplo, nota 5 →
  `elogio`), errando casos como o extravio com nota 5 visto na amostra da taxonomia.

### D-030 · Pedidos sem itens ficam fora do sinal de atraso
- **Decidido pelo usuário (2026-10-18).** O sinal point-in-time (`load_orders` em
  `src/data/point_in_time.py`) exclui os pedidos com `n_items = 0`. São 775 no banco e 686 na
  janela de análise: 599 `unavailable`, 82 `canceled` e 5 `created`.
- **Motivo:** são um artefato do dataset (o pedido não tem item registrado) e nunca podem ser
  entregues; sem a exclusão, inflavam a série de 2017. Os itens são registrados na compra,
  então o filtro não usa informação futura. Há teste para isso.
- **Efeito:** ver os números de D-025.
- **O que não muda:** as tabelas retrospectivas (`orders.is_late`) e o banco não são
  afetados; os pedidos continuam lá.

### D-031 · Itens "ambíguo" no gold set
- **Decidido pelo usuário (2026-10-18).** Itens rotulados "ambíguo / não sei" ficam fora das
  métricas principais do classificador (Fases 3 a 5) e são reportados à parte.
- **O que é reportado:**
  - a taxa de ambiguidade, no total e por split (`src/labeling/report.py`);
  - na avaliação, o que cada classificador previu nesses itens.

### D-032 · Nota para a Fase 6: avaliar classificar tudo com o LLM
- Com 0,47 s por chamada sem raciocínio (D-024), classificar os 41.281 comentários com o LLM
  ficaria na ordem de horas, não de dias.
- **Na Fase 6, avaliar essa opção contra a híbrida de D-015.** Requisitos:
  - execução retomável, com o cache em disco como ponto de retomada: cada item já
    classificado é um acerto de cache;
  - estimativa de tempo com os segundos por chamada medidos no dev com o prompt real, mais o
    pior caso de 2 tentativas por item;
  - OK do usuário antes de rodar (regra das 50 chamadas).
- A escolha leva em conta a qualidade medida na Fase 5. Se o LLM não for melhor que o
  baseline no test set, rodá-lo em tudo não se justifica.

## Fase 2.1 — Decisões do usuário após a rotulagem (2026-10-20)

Números citados abaixo vêm de `reports/gold_set.md` (`python -m src.labeling.report`).

### D-033 · `menciona_atraso` e `pede_reembolso_troca` deixam de existir
- **Decidido pelo usuário.** Os dois campos estavam "não" nos 250 itens rotulados. O usuário
  confirmou que não usou as teclas A/E durante a rotulagem: não foi falha da ferramenta.
- **O que muda:** os campos saem do gold set, do modelo `Label`, da ferramenta de rotulagem, do
  relatório, da taxonomia e do futuro schema do classificador. Também não terão métrica.
- **Proibido:** inferir esses campos por LLM ou heurística, para preencher o gold set ou
  qualquer outra coisa. Eles simplesmente deixam de existir no projeto.
- O arquivo original, com as duas colunas zeradas, fica no histórico do git (commit `9a32701`).
  `data/gold/labels_v1.csv` é esse arquivo sem as duas colunas.

### D-034 · Taxonomia v1.1: mudanças mecânicas, sem rejulgar itens
**Decidido pelo usuário.** Quatro mudanças:

| | Mudança | Regra aplicada aos rótulos |
|---|---|---|
| a | `atraso_entrega` + `nao_recebido` → `problema_entrega` (área `logistica`) | as duas viram `problema_entrega`, na principal e na secundária |
| b | nova classe `qualidade_insatisfatoria` (área `vendedor`, que já cobre produto e anúncio) | causa principal `outro` com nota livre "qualidade ruim" |
| c | embalagem danificada com produto intacto | permanece em `outro`; regra escrita na taxonomia |
| d | causa secundária | informativa, fora das métricas; o classificador não a prevê |

Continuam 8 classes. Definições em `docs/taxonomia.md` (v1.1).

**Mapeamento causa → área (revisa D-027):**

| Causa | Área |
|---|---|
| `problema_entrega` | `logistica` |
| `produto_defeituoso_ou_danificado`, `produto_diferente_do_anunciado`, `pedido_incompleto_ou_errado`, `qualidade_insatisfatoria` | `vendedor` |
| `problema_atendimento_ou_comunicacao` | `atendimento` |
| `elogio` | `nenhuma` |
| `outro`, `ambiguo` | `indefinida` |

As limitações de D-027 continuam. A segunda muda de nome: cancelamento e falta de estoque caem
em `problema_entrega` → `logistica`, embora a responsabilidade seja do vendedor.

**Implementação (auditável):**
- `data/gold/labels_v1.csv`: rótulos originais congelados.
- `python -m src.labeling.migrate --force` aplica as regras e grava `data/gold/labels.csv` em
  v1.1. Um teste garante que o `labels.csv` versionado é exatamente a migração do v1; qualquer
  edição manual o quebra.
- Resultado: 49 itens em `problema_entrega` (29 vindos de `nao_recebido` e 20 de
  `atraso_entrega`; dev 18, test 31), 18 em `qualidade_insatisfatoria` (dev 6, test 12) e uma
  causa secundária renomeada. Nenhuma secundária precisou ser apagada.
- Efeito: `outro` cai para 7 itens (dev 4, test 3) e entra na lista de classes raras, junto
  com `produto_diferente_do_anunciado` (test 7) e `problema_atendimento_ou_comunicacao`
  (dev 3, test 2).

**Evidência que justifica as mudanças sem depender do test set.** Toda a evidência vem do
corpus da Fase 1 ou do dev, com os rótulos v1:
- **(a) fusão:**
  - no corpus, 79,2% dos pares avaliação–pedido com "não recebi"/"não chegou" foram entregues
    depois (`reports/fase1_dados.md`, seção 10);
  - no dev, 5 dos 10 itens rotulados `nao_recebido` ("não vai chegar") têm pedido entregue;
  - a mesma fronteira foi aplicada de forma muito diferente por dois leitores: 3
    `nao_recebido` para 18 `atraso_entrega` na leitura da taxonomia (100 itens, Claude),
    contra 10 para 8 no dev (usuário).

  A fronteira não é decidível só pelo texto.
- **(b) qualidade:** no dev, 6 dos 10 itens `outro` têm a nota "qualidade ruim". Só o dev já
  mostra que esse é o tema mais comum de `outro`, e ele não tinha classe.
- **(c) embalagem:** no dev, 3 dos 10 `outro` têm a nota "embalagem danificada". A regra
  escreve o que já foi rotulado, sem mudar rótulo.
- **(d) secundária:** decisão de método, sem dependência de dados.

**Transparência:**
- As contagens do test estavam no relatório da Fase 2 (commit `9a32701`) quando a decisão foi
  tomada, e mostram o mesmo padrão. A decisão não precisa delas.
- Nenhum modelo tinha sido rodado e nenhuma métrica tinha sido vista.
- O sinal de entrega foi consultado só no dev, e só para esta auditoria.

### D-035 · Versionamento: previsões sim, cache não (resolve D-009)
- **Decidido pelo usuário.** `cache/` e `logs/` continuam fora do git, porque o cache guarda o
  texto das avaliações.
- **Previsões versionadas** em `data/predictions/`, um CSV por execução, sem texto:
  - `review_id`;
  - identificação da execução: modelo, `think`, versão do prompt e chave de cache;
  - saída validada: `causa`, `gravidade`, `confianca`;
  - status do schema, tentativas e latência.
- **`justificativa` não é versionada:** é texto gerado pelo modelo e pode citar a avaliação.
  Fica só no cache.
- **Reprodução:** com o cache local, `RADAR_LLM_MODE=cache_only` refaz tudo. Sem o cache, os
  relatórios são recalculados a partir das previsões versionadas.

### D-036 · Baseline: TF-IDF + regressão logística treinada no dev
- **Aprovado pelo usuário.** Treino só com o gold set do dev, itens não ambíguos (96 de 100).
  - Números do dev: validação cruzada estratificada de 5 partes, semente 42.
  - Fase 5: ajuste final no dev inteiro, avaliado uma vez no test.
- **Entrada:** a mesma do LLM, ou seja, título + mensagem e a nota (D-029), para que a
  comparação seja justa.
- **Limitação:** `problema_atendimento_ou_comunicacao` tem 3 itens no dev, menos que as 5
  partes; em algumas partes ela não aparece no teste. Isso é reportado, não contornado. Com
  96 itens, o baseline é fraco por construção.

### D-037 · `docs/plano.md`
- O plano de fases, as regras de conduta e o protocolo de checkpoint ficam em `docs/plano.md`,
  atualizado com as decisões até aqui. É a referência do plano, no lugar do contexto da
  conversa. Mudanças de plano exigem entrada neste log e atualização do plano.

## Fase 3 — Baseline e LLM v1 no dev

### D-038 · Classificador LLM v1: schema, prompt e papel com raciocínio
- **Schema** (`src/classifier/llm.py`): os campos vêm nesta ordem.
  - `justificativa` vem primeiro, até 300 caracteres: o modelo explica antes de decidir, o
    que sem raciocínio funciona como um passo curto de reflexão;
  - depois `causa` (8 classes v1.1), `gravidade` (baixa, media ou alta) e `confianca` (0 a 1).
  - A área vem da causa.
  - A ordem dos campos é parte do prompt e pode mudar na v2.
- **Prompt** `prompts/classifier_v1.md`:
  - regras gerais, classes com o que incluem e excluem, e critérios de gravidade, condensados
    de `docs/taxonomia.md` v1.1;
  - nenhum exemplo do gold set;
  - cerca de 1.000 tokens de entrada no total, medidos entre 996 e 1.024 por item.
- **Entrada:** nota, título e mensagem (D-029). Nada do pedido entra.
- **Papel `classifier_think`** (`config.yaml`):
  - `think: true` e `max_tokens: 4096`, porque o raciocínio gastou de 829 a 1.716 tokens nos 5
    itens e 1024 truncaria;
  - `num_ctx: 8192`, porque prompt, raciocínio e JSON não cabem em 4096;
  - `temperature: 0`, como pede D-011. Não houve repetição nos 5 itens.
- **Aquecimento:** antes de cada execução, uma chamada direta ao provedor carrega o modelo com
  as opções do papel, fora do cache e do log, para que a carga não conte como custo por item
  (D-013).
- **Medição** em 5 itens do dev (sorteio com semente 42), `python -m src.classifier.run --limit 5`:

  | | Sem raciocínio (`classifier`) | Com raciocínio (`classifier_think`) |
  |---|---|---|
  | s/item, mediana (mín–máx) | 1,17 (1,09–2,00) | 21,04 (15,69–33,37) |
  | Tokens de saída, mediana (máx) | 62 (85) | 1.106 (1.716) |
  | JSON válido | 5 de 5 | 5 de 5 |

  O tempo sem raciocínio é cerca de 2,5 vezes o do benchmark de D-024 (0,47 s), por causa do
  prompt real (cerca de 1.000 tokens) e da justificativa (cerca de 60 tokens).
- O log `logs/llm_usage.jsonl` registra as 10 chamadas. O benchmark e os testes reais usam um
  diretório temporário de propósito, e por isso o log estava vazio antes.

### D-039 · Fase 6: classificar só comentários com nota ≤ 3
- **Decidido pelo usuário** com a coluna do dev de `reports/gold_set.md`: notas 1 a 3 cobrem
  88,2% do volume reponderado de problemas (todas as classes exceto `elogio`). No universo,
  notas 1 a 3 são 36,1% dos comentários.
- **Regra:** comentários com nota 4 ou 5 recebem o status `nao_classificado`.
  - **Nunca** são tratados como `elogio`.
  - Ficam fora das contagens de causa do detector.
- **Perda estimada por classe**, na coluna do dev: fração reponderada do volume da classe que
  está em notas 4–5 e não será classificada.

  | Classe | Perda | n no dev |
  |---|---|---|
  | `problema_atendimento_ou_comunicacao` | **84,4%** (a mais afetada) | 3 |
  | `outro` | 38,6% | 4 |
  | `qualidade_insatisfatoria` | 20,2% | 6 |
  | `problema_entrega` | 12,0% | 18 |
  | `produto_defeituoso_ou_danificado`, `produto_diferente_do_anunciado`, `pedido_incompleto_ou_errado` | 0% | 6, 8, 12 |
  | todas exceto `elogio` | 11,8% | 57 |

  Com n tão pequeno, as perdas de atendimento e `outro` são só ordens de grandeza, e os splits
  discordam: no test, os 2 itens de atendimento estão em nota ≤ 3 (perda de 0%), e com os dois
  splits juntos a perda de atendimento é de 44,4% (n = 5). O número do dev é o usado na
  decisão, como pediu o usuário, mas a perda real de atendimento é incerta.
- **Consequência para o detector:** reclamações de atendimento ficam quase invisíveis para o
  Radar. Isso vai para as Limitações do README.
- **Ponto aberto para antes da Fase 7:** o denominador da proporção de cada causa. Pode ser
  todos os comentários do segmento e semana, incluindo os `nao_classificado`, ou só os
  classificados. A escolha deve ser fixada antes da calibração.

### D-040 · Baseline e métricas da Fase 3: detalhes fixados antes de rodar
- **Baseline** (`src/classifier/baseline.py`), com hiperparâmetros escolhidos a priori e
  rodado uma única vez, sem busca:
  - TF-IDF de palavras (1–2) e de caracteres (`char_wb`, 2–5, `min_df` 2);
  - one-hot da nota;
  - regressão logística com `C = 10` e `class_weight = "balanced"`.

  O `C` maior que o padrão compensa as poucas amostras por classe.
- **Validação cruzada:** o scikit-learn avisou que a menor classe (atendimento, 3 itens) tem
  menos membros que as 5 partes. O aviso foi registrado, sem contornar.
- **Métricas** (`src/eval/classification.py`):
  - falha de schema conta como erro (rótulo `FAIL`);
  - macro-F1 nas 8 classes, com intervalo de confiança de 95% por bootstrap (1.000
    reamostragens, semente 42);
  - versão reponderada com o peso da nota de cada item (D-028).
- **Tempo por item:** latência da chamada para o LLM, com o modelo carregado; só a previsão
  para o baseline, com o tempo de ajuste em `fit_s`.
- **Concordância com o sinal objetivo de entrega:** só observação, sem métrica (D-033). Usa o
  sinal retrospectivo (`orders.is_late` ou pedido sem entrega).

### D-041 · O gold set não muda com base nas previsões do modelo
- **Regra do usuário (2026-10-20):** nenhum rótulo do gold set é alterado com base nas
  previsões de qualquer modelo.
- **As 4 discordâncias em que a regra apoia o modelo** (`docs/erros.md`, categoria 1) ficam
  anotadas em `data/gold/discordancias_regra.csv`. O arquivo tem o rótulo original e a causa
  que a regra escrita da v1.1 daria, e é uma anotação, não um rótulo.
- **Métrica principal:** o macro-F1 principal usa os rótulos originais e é a estimativa
  conservadora.
- **Métrica secundária:** nesses 4 itens, a previsão igual à causa da regra também conta como
  acerto. É calculada para todos os métodos e aparece sempre identificada como secundária
  (`reports/fase3_dev.md`).
  - **Viés declarado:** os itens saíram da leitura dos erros do LLM v1 sem raciocínio, então a
    métrica secundária favorece esse método.
- **Fase 4:** o prompt não é ajustado para imitar esses rótulos questionáveis. Se a taxonomia
  precisar de redação mais clara, isso é registrado como melhoria para uma versão futura
  (`docs/erros.md`, "Melhorias de redação") e não é aplicado à v1.1.

## Fase 4 — Análise de erros e LLM v2 (decisões do usuário em 2026-10-20, antes de rodar a v2)

### D-042 · Configuração principal: LLM sem raciocínio
- **Decidido pelo usuário** depois da Fase 3: `qwen3:4b` sem raciocínio (papel `classifier`).
  - Com raciocínio, empatou dentro do ruído: macro-F1 de 0,823 contra 0,846, com intervalos de
    confiança praticamente iguais.
  - Custa cerca de 20 vezes mais tempo: 28 s contra 1,4 s por item.
- O modo com raciocínio fica como comparação: roda no test depois do lote da Fase 6, para não
  disputar a GPU.

### D-043 · Denominador do Radar (fixado antes da Fase 7)
- **Decidido pelo usuário:** a taxa da causa *X* no segmento *s* e na semana *t* é
  **comentários classificados com a causa *X* / total de avaliações de *s* respondidas em *t***.
  - O total inclui avaliações com e sem comentário e os `nao_classificado` (D-039).
  - A semana é a da resposta (`answered_week`, D-019), e o segmento vem da view
    `review_segments`.
- **Leitura:** "avaliações com causa *X* a cada 100 avaliações". A taxa capta tanto o aumento
  de reclamações quanto a mudança de causa, e usa a mesma base de B1 (nota média) e B2 (fração
  de notas ≤ 2), o que torna a comparação justa.
- **Se a antecedência ficar parecida com a de B2,** o argumento do projeto passa a ser o
  diagnóstico de causa, como já previsto em D-026.
- Complementa D-026 ("Métodos comparados", Radar). Não muda a definição de incidente nem os
  períodos.

### D-044 · Protocolo da Fase 4, fixado antes de rodar a v2
- **Uma única iteração v1 → v2** do prompt sem raciocínio, no dev (100 chamadas, OK do
  usuário).
  - A v2 só ataca as categorias 2 a 5 de `docs/erros.md`.
  - Não imita os 4 rótulos questionáveis (D-041) e não muda nenhuma definição de classe da
    v1.1.
- **Regra de aceite (a priori):** a v2 substitui a v1 se, e só se, valerem as três condições
  no dev:
  1. macro-F1 principal (rótulos originais, sem reponderação) da v2 ≥ 0,846 (v1);
  2. nenhum acerto perdido em classe rara: todo item com gold `produto_diferente_do_anunciado`,
     `problema_atendimento_ou_comunicacao` ou `outro` que a v1 acerta, a v2 também acerta;
  3. falhas de schema da v2 ≤ as da v1 (0).

  Se qualquer condição falhar, a v1 continua. Nenhuma outra iteração é feita.
- **Relatório item a item:** acertos ganhos e perdidos da v2 em relação à v1
  (`reports/fase4_dev.md`).
- **Limiar de confiança para revisão humana:** calibrado no dev, com as confianças salvas da
  configuração escolhida, sem GPU.
  - **Curva:** para cada limiar *c*, a % de itens com confiança < *c* enviada para revisão e
    a acurácia do restante.
  - **Regra de escolha (a priori):**
    - o limiar que maximiza a acurácia do restante, enviando no máximo 15% dos itens;
    - em empate, o que envia menos;
    - se nenhum limiar melhorar a acurácia do restante em pelo menos 2 p.p. sobre não enviar
      nada, a proposta é **não usar limiar**, porque a confiança não é informativa.
  - O limiar escolhido no dev é aplicado sem ajuste no test (Fase 5).

### D-045 · Resultado da Fase 4 e protocolo da Fase 5
**Resultado da Fase 4** (`reports/fase4_dev.md`, regras de D-044 aplicadas sem mudança):
- **A v2 foi rejeitada e a v1 continua.**
  - Condição 1 passa: macro-F1 de 0,864 na v2 contra 0,846 na v1.
  - Condição 3 passa: 0 falhas de schema.
  - **Condição 2 falha:** a v2 perdeu um acerto em `outro` (`d1952450`).
- **Item a item:** 6 itens mudaram, com 3 ganhos e 3 perdas; os acertos ficaram em 87 a 87.
  - Os ganhos vieram de três correções: embalagem, causa raiz e um item de qualidade × anúncio.
  - As perdas foram um `outro` virando `diferente` e dois de entrega, um virando incompleto e
    outro virando elogio.
  - A v2 mexeu no mesmo tanto que consertou. Não há outra iteração (D-044).
- **Limiar de confiança: nenhum.** A confiança da v1 tem só 5 valores (0,80 a 1,00).
  - O primeiro limiar que envia alguém (0,85) já manda 19,8% dos itens, acima do orçamento
    de 15%.
  - Com até 15% enviados, o ganho é de 0 p.p.
  - Na Fase 6, nenhum item vai para revisão humana por confiança. A confiança fica gravada
    para uso futuro.

**Protocolo da Fase 5** (avaliação única no test, autorizada pelo usuário):
- **Configurações avaliadas:**
  - baseline TF-IDF+LR (D-036, D-040), ajustado nos 96 itens não ambíguos do dev;
  - LLM v1 sem raciocínio (D-042).

  O LLM v1 com raciocínio roda no test depois do lote da Fase 6.
- **Liberação do test:** o executor só aceita o test com `--allow-test`, uma flag reservada a
  esta avaliação.
- **Métricas:** as mesmas da Fase 3 (`reports/fase5_test.md`), com bootstrap de 95%.
  - Não há métrica secundária no test: as anotações de D-041 são do dev, e nenhuma anotação
    nova é criada a partir dos erros do test.
- **Nada é ajustado depois:** prompt, limiar, taxonomia e rótulos ficam como estão, qualquer
  que seja o resultado.

## Fase 5 — Avaliação final no test set

### D-046 · Resultado da avaliação única no test (nada é ajustado)
Os números vêm de `reports/fase5_test.md` (`python -m src.eval.test_report`): 150 itens, 137
não ambíguos, rodados uma única vez.

| | macro-F1 [IC 95%] | macro-F1 reponderado | acurácia | acurácia reponderada | falha de schema | s/item |
|---|---|---|---|---|---|---|
| baseline | 0,422 [0,336; 0,492] | 0,471 | 0,708 | 0,839 | 0 | < 0,001 |
| LLM v1 sem raciocínio | **0,657** [0,518; 0,754] | 0,672 | 0,810 | 0,879 | 0 | 1,68 (mediana) |

- **Queda do dev para o test.** No LLM, o macro-F1 cai de 0,846 para 0,657 e a acurácia de
  0,906 para 0,810. O baseline fica estável (0,408 → 0,422).
- **A queda se concentra em `qualidade_insatisfatoria`.** São 12 itens no test, com recall de
  0,17: 6 previstos como `defeito` e 4 como `diferente`.
  - É o mesmo padrão das discordâncias em que a regra apoia o modelo no dev (D-041): rótulos
    vindos do remapeamento mecânico da nota "qualidade ruim" (D-034) contra uma definição
    escrita que manda falha física para `defeito` e comparação com o anúncio para `diferente`.
  - O test não foi inspecionado item a item, então isso é uma hipótese compatível com os
    números, não uma verificação.
  - Outras confusões: 4 de `incompleto` previstos como `diferente`; 2 de `elogio` previstos
    como `incompleto` e 2 como `outro`.
- **Observação pós-teste, fora do protocolo:** o acerto da área responsável do LLM é 0,927, e
  45 de 46 itens da área `vendedor` ficam com a área certa. Os erros de causa ficam quase
  todos dentro da mesma área.
- **Nota como atalho:** o baseline previu `elogio` em 7 de 8 itens de nota 4–5 que não eram
  elogio; o LLM, em 0 de 8.
- **Consequências** (registradas, sem ajustar nada):
  - o número a citar é o do test, 0,657, não o do dev;
  - a causa `qualidade_insatisfatoria` não é confiável para o detector;
  - a melhoria da taxonomia já está registrada para uma versão futura (`docs/erros.md`).

### D-047 · Família "produto" como unidade de detecção e diagnóstico na Fase 7
- **Decidido pelo usuário (2026-10-20), antes de qualquer código da Fase 7.**
  - `qualidade_insatisfatoria`, `produto_defeituoso_ou_danificado` e
    `produto_diferente_do_anunciado` formam a família **produto**.
  - Na Fase 7, o Radar detecta e diagnostica por família, não por essas três causas
    separadas.
- **A decisão foi motivada pelos resultados do test set (D-046).**
  - No test, `qualidade_insatisfatoria` teve recall de 0,17, e os itens foram para `defeito`
    e `diferente`.
  - Fica declarado que o test influenciou uma escolha de desenho posterior. A escolha não
    altera nenhum número da Fase 5.
- **As métricas do classificador no test permanecem exatamente como reportadas** em
  `reports/fase5_test.md`. Um F1 por família só pode aparecer como observação pós-teste
  identificada, nunca como métrica principal.
- As outras causas continuam como unidades próprias: `problema_entrega`,
  `pedido_incompleto_ou_errado`, `problema_atendimento_ou_comunicacao` e `outro`. `elogio`
  não entra em sinal de problema.
- Não muda a definição de incidente, os períodos nem o denominador (D-026, D-043).

## Fase 7 — Detector e backtest

### D-048 · Detalhes de implementação do backtest, fixados antes de existir resultado
D-026, D-043 e D-047 deixam alguns detalhes em aberto. Eles ficam fixados aqui, antes de
qualquer execução do detector, e não mudam depois.

**Regra de alerta comum a todos os métodos.** É point-in-time, com a mesma referência de D-026:
mediana das 26 semanas anteriores com volume ≥ *n_min*, exigindo pelo menos 8.
- **Sinais de proporção** (Radar por família, B2 fração de notas ≤ 2, B3 atraso point-in-time):
  - escore = (*p* − *b*) / √(*b′*(1 − *b′*)/*n*), com *b′* = max(*b*, 1/*n*);
  - o piso evita divisão por zero quando a referência é 0.
- **B1 (nota média):**
  - escore = (*b* − *m*) / (*s*/√*n*);
  - *m* é a média da semana e *b* a mediana das médias anteriores;
  - *s* é o desvio-padrão das notas individuais das 26 semanas anteriores, agrupadas.
  - Queda da nota → escore positivo.
- **Radar:**
  - um escore por família de causa (D-047): entrega, produto, incompleto, atendimento e outro;
  - o escore do Radar na semana é o maior deles, e a família que o produz é o diagnóstico;
  - taxa por família = comentários classificados com a causa / total de avaliações do
    segmento na semana (D-043).
- **Alerta:** escore > *θ* e volume ≥ *n_min* do sinal.
  - *θ* é o único parâmetro calibrado por método, numa grade de 0,5 a 8,0 com passo de 0,25,
    escolhendo o menor *θ* com no máximo 1 falso alarme por semana em 2017 (D-026).
- **Volumes mínimos dos sinais:** 20 avaliações para Radar, B1 e B2; 30 pedidos na coorte
  para B3. São os mesmos *n_min* dos tipos B e A de incidente.

**Interpretação da regra de junção de D-026.**
- Primeiro, sequências de semanas anômalas separadas por uma única semana não anômala são
  unidas, inclusive semanas isoladas.
- Depois, um bloco unido só vira incidente se tiver pelo menos 2 semanas anômalas
  consecutivas.
- Início e fim do incidente: a primeira e a última semana anômala do bloco.

**Segmentos e semanas.**
- **Segmentos:** os de D-026, com volume médio ≥ 5 comentários por semana na janela.
- **Tipo A:** a categoria de um pedido vem de `order_segments`; um pedido com várias
  categorias entra em todas, como no resto do projeto (D-016).
- **Tipo B:** conta as avaliações ligadas a pelo menos um pedido entregue no prazo naquele
  segmento.
- **Semanas:** de 2016-08-01 a 2018-08-13. As anteriores à janela servem só de histórico para
  a referência.

**Calibração sem espiar 2018.**
- Na calibração, o gabarito é calculado com dados até 2017-12-31.
- Um alerta de dezembro que anteceda um incidente iniciado em 2018 conta como falso alarme.
  Isso é conservador: no máximo, leva a um *θ* um pouco mais alto.
- **A avaliação (2018) só roda com o lote completo**, e com os *θ* gravados na calibração
  (`reports/backtest_calibracao.json`), sem mudança.

### D-051 · Integridade do lote antes da avaliação de 2018 (critérios fixados antes do fim)
> Decisão do usuário em 2026-10-20, com o lote em andamento (cerca de 45% das chamadas). O
> script foi versionado antes de rodar no lote completo.

`python -m src.eval.integridade` precisa passar inteiro; senão a avaliação não roda e o
problema é reportado. Verificações:
- nº de linhas = nº de comentários do banco; nenhum `review_id` faltando, duplicado ou fora do
  banco;
- só os status `classificado`, `nao_classificado` e `falha_schema`;
- `nao_classificado` = nº de notas 4–5, e `classificado` + `falha_schema` = nº de notas ≤ 3;
  nenhuma nota ≤ 3 sem classificação e nenhuma nota ≥ 4 classificada (D-039);
- toda causa classificada pertence à taxonomia v1.1;
- **falhas de schema em no máximo 1% das chamadas** (148 de 14.888); o número é reportado;
- `lote_missing` até 2018-08-13 = 0.

### D-052 · Observação: um mesmo alerta pode casar com dois incidentes (sem mudança na regra)
> Registrado em 2026-10-20, depois da calibração. É uma observação: D-026 e D-048 seguem
> congelados.

- **O caso.** No estado PR há dois incidentes A seguidos em 2017: de 2017-11-06 a 2017-11-13
  e de 2017-12-11 a 2017-12-18. A janela de casamento do primeiro vai até 2017-11-13 (o fim);
  a do segundo começa em 2017-11-13 (início − 4 semanas). Os quatro métodos alertam em
  2017-11-13 (no Radar, família `entrega`), e esse alerta conta como a detecção do incidente
  de dezembro, 4 semanas antes do início, embora caia no fim do incidente de novembro.
- **Efeito na calibração.** O recall não muda: sem esse alerta, os quatro métodos ainda
  detectariam o incidente de dezembro com alertas de 2017-12-11 (B3) ou 2017-12-18 (Radar, B1
  e B2). A antecedência do Radar sobre B1 e B2 nesse incidente é 0 nos dois casos. Muda só a
  medida "início − detecção": +4 semanas em vez de −1 (Radar, B1 e B2) ou 0 (B3).
- **Como ler.** A regra de D-026 casa cada incidente com o primeiro alerta da janela, sem
  impedir que um alerta sirva a dois incidentes do mesmo segmento. Isso não altera a contagem
  de falsos alarmes. Antecedências na borda da janela (4 semanas) devem ser conferidas na
  tabela "incidente por incidente" do backtest antes de virar estudo de caso. Vale também para
  2018, sem mudar a regra.

### D-053 · Desenho final: B2 detecta, a camada de IA explica (decisão POSTERIOR à avaliação)
> **Decisão do usuário em 2026-10-20, tomada DEPOIS de ver a avaliação de 2018**
> (`reports/backtest.md`). Não é uma escolha feita às cegas: é motivada pelo resultado do test
> do detector, e é declarada assim. Os resultados do backtest ficam exatamente como estão; nada
> é recalculado nem reajustado.

**O que o backtest mostrou** (números de `reports/backtest.md`, θ fixados em 2017):
- **Detecção:** no mesmo nível de falsos alarmes (0,88 por semana), o Radar detecta 22 de 26
  incidentes A e o B2 (fração de notas ≤ 2) detecta 24. Em todos os níveis da curva, o Radar
  fica igual ou atrás das linhas de base.
- **Antecedência:** mediana de 0 semana contra B1 e B2; média de −0,73 contra B1 e −0,10
  contra B2 (o Radar detecta, em média, um pouco depois).
- **Diagnóstico:** a família do alerta é compatível em 19 de 22 incidentes A (86%), pouco acima
  da taxa de base de `entrega` em todos os alertas do Radar (88 de 114, 77%). Em 2017: 11 de 16
  (69%) contra 40 de 70 (57%).

**Desenho final do sistema:**
- **Detector: B2** (fração de avaliações com nota ≤ 2 na semana, contra a mediana das 26
  semanas anteriores; θ = 2,0 da calibração de 2017, D-048).
- **Camada de IA para explicar o alerta:** as classificações do lote (Fase 6) e o agente
  investigador com verificação (Fase 8) dizem a causa, os segmentos, vendedores e pedidos
  afetados e o impacto. Cada número do briefing é reexecutado pelo verificador.
- O Radar continua no repositório e no relatório do backtest como o método avaliado. Ele não
  é removido nem reescrito.

## Fase 8 — Agente investigador com verificador

### D-049 · Acesso SQL, verificador e loop do agente (código pronto, sem chamadas reais)
- **Somente leitura em quatro camadas** (`src/agent/sql.py`), cada uma testada sozinha:
  1. arquivo aberto com `mode=ro`;
  2. `PRAGMA query_only`;
  3. autorizador do SQLite que só permite SELECT, leitura de colunas, funções e CTE recursiva,
     e nega ATTACH e PRAGMA;
  4. texto que precisa começar com SELECT/WITH, com uma instrução por chamada.
- **Limites por consulta:** 5 s (progress handler) e 200 linhas.
- **Testes** (`tests/test_agent_sql.py`, 17): INSERT, UPDATE, DELETE, DROP, CREATE, ALTER,
  ATTACH, PRAGMA, VACUUM, REPLACE, escrita disfarçada de `WITH`, várias instruções, tempo
  limite e limite de linhas.
- **Verificador** (`src/agent/verify.py`): o briefing traz afirmações com texto, valor e
  `query_sql`. Cada consulta é reexecutada e precisa devolver um único valor numérico.
  - **Igualdade:** arredondamento de até 2 casas ou tolerância relativa de 0,1%.
  - **Status:** `verificada`, `divergente` ou `erro`.
  - **Números soltos** no resumo, sem afirmação correspondente, são listados. A detecção é
    heurística: ignora datas `AAAA-MM-DD` e menções a nota de 1 a 5, e aceita *x* = 100 × valor
    para percentuais.
- **Loop** (`src/agent/investigator.py`): até 8 iterações de chamada de ferramenta, depois um
  pedido final de briefing em JSON (`Briefing`, com até 2 tentativas, D-006) e a verificação.
  Sem framework de agentes.
- **Limitação (resolvida em D-050):** o agente vê o banco inteiro. A regra de
  usar só dados até a semana do alerta está no prompt (`prompts/agent_v1.md`), não é imposta.
  - Numa investigação de um alerta antigo do backtest, o agente pode olhar o futuro.
  - Opção de correção: um banco recortado na semana do alerta, gerado para cada
    investigação. Fica como decisão do usuário.
- **Chamadas reais ao Ollama:** só depois do lote da Fase 6, que ocupa a GPU. Até lá, só testes
  com provedor roteirizado.

### D-050 · Banco recortado por investigação (resolve a limitação de D-049)
- **Decidido pelo usuário.** Cada investigação usa um banco gerado no corte, que é o fim da
  semana do alerta: a segunda-feira seguinte, 00:00, exclusive (`src/agent/snapshot.py`).
- **O agente só vê esse banco**, aberto com as quatro camadas de somente leitura de D-049.
- **A regra de usar só o que se sabia está imposta pelos dados.** No prompt, ela fica só como
  contexto.

**Estado point-in-time, não só filtro de linhas:**
- **Pedidos:** só os comprados antes do corte.
  - Aprovação, envio e entrega posteriores ao corte viram nulo.
  - `delay_days`, `is_late`, `delivery_days` e `delivered_week` só existem se a entrega foi
    antes do corte.
- **`order_status` final é substituído por um status derivado das datas no corte:**
  `created`, `approved`, `shipped` ou `delivered`.
  - Não se sabe quando o status mudou (D-025).
  - Cancelamentos e indisponibilidades não aparecem no banco recortado, e um pedido cancelado
    antes do corte surge como `approved` ou `created`. É uma limitação aceita: a data do
    cancelamento não existe no dataset.
- **`situacao_entrega`:** coluna nova com a lógica de `src/data/point_in_time.py`
  (`delay_status_as_of`).
- **Avaliações e classificações:** só as com `review_answer_ts` antes do corte (D-019). O
  vínculo `review_orders` e a view `review_segments` seguem o mesmo recorte.

**Exceção declarada ao requisito "nenhuma data depois do corte".**
- Ficam as datas planejadas, conhecidas na compra, mesmo que caiam depois do corte:
  `estimated_delivery_date`, `estimated_week` e `shipping_limit_ts`.
- Anulá-las esconderia o que se sabia na semana do alerta, inclusive o que define "atrasado em
  aberto".
- O teste verifica todas as outras colunas de data de todas as tabelas, e lista essas três
  como exceções explícitas.

**Testes** (`tests/test_snapshot.py`):
1. Nenhuma data de evento depois do corte, em nenhuma tabela.
2. Um pedido comprado antes e entregue depois do corte aparece como não entregue: entrega nula,
   `approved` e `atrasado_em_aberto`.
3. Consultas do agente sobre o período posterior ao corte devolvem vazio, em avaliações,
   classificações e pedidos. Uma resposta às 23:59 do domingo da semana do alerta entra.

O verificador reexecuta as consultas no mesmo banco recortado: um número só é verificado se
fosse calculável na semana do alerta.
