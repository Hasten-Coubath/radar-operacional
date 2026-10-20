# Plano do projeto

Referência do plano de fases, das regras de conduta e do protocolo de checkpoint (D-037).
Consolida a especificação inicial do usuário e as decisões de `docs/decisoes.md` até a D-037.
Uma mudança de plano exige uma entrada nova no log de decisões e a atualização deste arquivo.

## Objetivo

Alerta precoce de problemas operacionais de e-commerce a partir das avaliações de clientes da
Olist (2016–2018). A pergunta é a do gestor de operações: **tem algo quebrando agora, onde,
desde quando e qual o impacto?** São três camadas:

1. **Classificador de causa:** cada avaliação com comentário vira um JSON validado por Pydantic,
   avaliado contra um gold set rotulado manualmente.
2. **Detector de anomalias com backtest semanal sem vazamento:** mede a antecedência contra a
   queda da nota média, o recall de incidentes e os falsos alarmes por semana.
3. **Agente investigador SQL somente leitura:** cada afirmação numérica do briefing é ligada a
   uma `query_sql` e reverificada automaticamente.

## Regras de conduta

- Não inventar resultados nem métricas. Todo número do README vem de um script versionado.
- Confirmar nos dados antes de afirmar qualquer coisa.
- Se algo do plano não fizer sentido diante dos dados, parar e explicar, em vez de contornar em
  silêncio.
- Antes de qualquer execução com mais de 50 chamadas ao LLM, mostrar a estimativa de tempo de
  processamento e esperar o OK (D-013). A estimativa usa segundos por chamada medidos numa
  amostra pequena, mais o pior caso de 2 tentativas por item.
- Nunca usar o test set antes da Fase 5.
- Nunca ajustar a definição de incidente depois de ver os resultados do detector sem
  documentar a mudança e o motivo. D-026 e os períodos de calibração e avaliação estão
  congelados.
- Proibido usar o LLM para pré-rotular o gold set (avaliação circular). Os campos removidos em
  D-033 não são inferidos de nenhuma forma.
- Nenhum rótulo do gold set é alterado com base nas previsões de um modelo (D-041). O prompt
  não é ajustado para imitar rótulos questionáveis; melhorias de redação da taxonomia ficam
  para uma versão futura. O macro-F1 principal usa os rótulos originais.
- Backtest: a semana *t* só usa dados que já existiriam em *t* (D-019, D-025, D-030).
- Nunca versionar `.env`, chaves ou dados brutos. Os CSVs da Olist são baixados manualmente pelo
  usuário para `data/raw/`; o projeto nunca os baixa sozinho. `cache/` e `logs/` também não
  são versionados (D-035).
- Agente: conexão somente leitura, só `SELECT`, com timeout e limite de linhas, e testes que
  provem que a escrita é bloqueada. Sem frameworks pesados de agentes: um loop simples com
  limite de iterações.
- Seeds fixas, código tipado (mypy strict), docstrings curtas, commits pequenos, notebooks só em
  `notebooks/`.

## Premissas técnicas

- **Custo zero de API (D-010 a D-013).**
  - Provedor padrão: Ollama local com `qwen3:4b`, em `http://127.0.0.1:11434` (não
    `localhost`, que custa cerca de 2 s por chamada no Windows; D-024).
  - Classificação com `think: false`, `num_ctx: 4096`, `temperature: 0` e `seed: 42`.
  - A Anthropic continua disponível como opção paga.
  - A métrica de custo é o **tempo de processamento** (`python -m src.llm`).
- **Cache e reprodutibilidade (D-003, D-004, D-012).** Toda chamada passa por um cache em disco
  (chave SHA-256 de tudo que influencia a saída). `RADAR_LLM_MODE=cache_only` refaz relatórios
  sem chamar o modelo. As previsões são versionadas por `review_id`, sem texto (D-035).
- **Ordem de grandeza medida (D-024).** 0,47 s por chamada sem raciocínio e 18,5 s com
  raciocínio, em textos curtos. O tempo real vem do prompt real, medido na Fase 3.

## Protocolo de checkpoint

Ao fim de cada fase: **parar**, fazer commit e escrever o relatório exatamente neste formato,
em português:

```
## Checkpoint — Fase N: <nome>
### O que foi feito
### Arquivos criados/alterados
### Resultados (números, tabelas)
### Decisões tomadas e por quê
### Problemas, dúvidas e riscos
### Custo de API acumulado (estimado)
### Proposta para a próxima fase
```

Um agente revisor avalia cada fase. A fase seguinte só começa com autorização explícita do
usuário.

## Fases

| Fase | Nome | Situação |
|---|---|---|
| 0 | Setup | concluída (D-001 a D-009) |
| 0.1 | Ollama local, custo zero | concluída (D-010 a D-015) |
| 1 | Dados, banco e taxonomia | concluída (D-016 a D-023) |
| 1.1 | Sinal de atraso point-in-time e correções | concluída (D-024 a D-026) |
| 2 | Ferramenta de rotulagem e gold set | concluída (D-027 a D-032; ajustes D-033 a D-037) |
| 3 | Baseline e LLM v1 no dev | concluída (D-038 a D-041) |
| 4 | Análise de erros e LLM v2 | concluída, aguardando revisão (D-042 a D-045) |
| 5 | Avaliação final no test set (uma vez) | concluída, aguardando revisão (D-046); falta com raciocínio, depois do lote |
| 6 | Classificação em lote | — |
| 7 | Detector e backtest | — |
| 8 | Agente investigador com verificador | — |
| 9 | Painel Streamlit | — |
| 10 | README final | — |

### Fase 1 — Dados, banco e taxonomia (concluída)
- O banco SQLite `data/processed/radar.db` é determinístico e não é versionado
  (`python -m src.data.make_db`). Ele tem avaliações únicas com vínculo N:N com pedidos e
  segmentos materializados (D-016).
- Comentário elegível: tem pelo menos uma letra ou dígito, o que dá 41.281 avaliações (D-018).
- **Disponibilidade da avaliação no backtest:** `review_answer_ts` (`answered_week`), não a
  data de criação, que é a data de envio da pesquisa (D-019).
- **Janela de análise:** de 2017-02-06 a 2018-08-27. O sinal de atraso vai até 2018-08-13, por
  causa da censura no fim do dataset (D-020).
- **Segmentos de detecção:** estado do cliente e categoria. Vendedor é só uma dimensão de
  aprofundamento do agente (D-021).
- **Sinal de atraso point-in-time (D-025, D-030):** a coorte com data estimada na semana é
  avaliada em *t* + 7 dias. Pedidos nunca entregues contam como atrasados; pedidos sem itens
  ficam fora; `order_status` nunca é usado.

### Fase 2 — Gold set (concluída)
- 250 avaliações (50 por nota, semente 42), sem os IDs da amostra da taxonomia. A divisão é
  estratificada em 100 dev e 150 test, gravada antes da rotulagem (D-028).
- Rótulo manual: causa principal (8 classes da taxonomia v1.1 ou "ambíguo"), causa secundária
  opcional e só informativa, e nota livre (D-028, D-033, D-034).
- Ambíguos ficam fora das métricas principais e são reportados à parte, com a taxa de
  ambiguidade (D-031).
- As métricas são reponderadas pela distribuição real das notas (D-028).
- **Taxonomia v1.1** (D-034): `problema_entrega`, `produto_defeituoso_ou_danificado`,
  `produto_diferente_do_anunciado`, `pedido_incompleto_ou_errado`, `qualidade_insatisfatoria`,
  `problema_atendimento_ou_comunicacao`, `elogio` e `outro`. A área vem do mapeamento fixo
  causa → área.
- Relatório: `reports/gold_set.md`, com a composição de classes por nota e a cobertura de um
  recorte por notas ≤ 3.

### Fase 3 — Baseline e LLM v1 no dev
- **Schema do classificador:**
  - campos previstos: `causa` (8 classes), `gravidade` (baixa, média ou alta; sem rótulo no
    gold, então sem métrica), `confianca` (0 a 1) e `justificativa` curta;
  - `area_responsavel` é derivada da causa, não prevista;
  - entrada: título + mensagem + nota (D-029).
- **Prompt versionado** em `prompts/`. Os exemplos vêm só da taxonomia, nunca do gold set.
- **LLM `qwen3:4b`, com e sem raciocínio (D-011).** Medir 5 itens do dev com o prompt real,
  mostrar a estimativa e esperar o OK antes de rodar o dev inteiro.
- **Baseline TF-IDF + regressão logística (D-036):** treino no dev com validação cruzada
  estratificada de 5 partes. Na Fase 5, ajuste final no dev inteiro.
- **Métricas:**
  - F1 macro e F1 por classe, com e sem reponderação;
  - matriz de confusão;
  - taxa de falha de schema;
  - segundos por item;
  - previsões nos itens ambíguos, à parte;
  - uso da nota como atalho (D-029).
- **Previsões versionadas** em `data/predictions/` (D-035). As chamadas ficam registradas em
  `logs/llm_usage.jsonl`.

### Fase 4 — Análise de erros e LLM v2
- Erros do LLM v1 e do baseline no dev, registrados em `docs/erros.md`.
- O prompt v2 (e, se for o caso, o modo de raciocínio) é ajustado só no dev.

### Fase 5 — Avaliação final no test set
- Uma única avaliação de cada configuração escolhida na Fase 4, contra o baseline, no test set.
  Nada é ajustado depois disso.
- Métricas como na Fase 3, mais intervalos de confiança.

### Fase 6 — Classificação em lote
- **Decidido (D-039):** classificar só os comentários com nota ≤ 3, cerca de 36% do total.
  Notas 4–5 ficam `nao_classificado`, nunca `elogio`, e fora das contagens de causa do
  detector.
- **Perda estimada:** atendimento perde cerca de 84% do seu volume e o total de problemas
  cerca de 12%; detalhe em D-039.
- **Configuração:** a do LLM escolhida nas Fases 4 e 5. Execução retomável, com o cache como
  ponto de retomada, estimativa de tempo e OK do usuário.

### Fase 7 — Detector e backtest
- **Definição de incidente, linhas de base, métricas e períodos congelados em D-026.** A
  atualização de nomes de classe por D-034 está anotada lá.
- **Períodos:** calibração de 2017-02-06 a 2017-12-25 (47 semanas); avaliação de 2018-01-01 a
  2018-08-13 (33 semanas).
- **Incidente tipo A (atraso point-in-time) e tipo B (notas ≤ 2 em pedidos entregues no
  prazo):** referência de 26 semanas, limiar max(2·*b*, *b* + 0,05) e limite inferior de Wilson
  acima de *b*.
- **Métodos comparados:**
  - Radar: proporção de cada causa por segmento e semana;
  - B1: nota média;
  - B2: fração de notas ≤ 2;
  - B3: atraso point-in-time, como referência.

  Todos calibrados para no máximo 1 falso alarme por semana em 2017.
- **Métricas em 2018:** recall por tipo, antecedência do Radar sobre B1 e falsos alarmes por
  semana.
- **Se a antecedência for pequena** (mediana ≤ 1 semana), o valor principal passa a ser:
  - o diagnóstico de causa;
  - o recall no tipo B;
  - o caso do vendedor `5dceca12`.

### Fase 8 — Agente investigador com verificador
- Diante de um alerta, o agente investiga via SQL, com conexão somente leitura, só `SELECT`,
  timeout e limite de linhas. Testes mostram que a escrita é bloqueada.
- Loop simples com limite de iterações, sem framework de agentes.
- Cada afirmação numérica do briefing é ligada a uma `query_sql` e reexecutada pelo
  verificador.
- O vendedor entra como aprofundamento a partir do alerta de estado ou categoria (D-021),
  incluindo o caso `5dceca12`.
- O modelo do agente é provisório (D-011), e a escolha final é justificada aqui com tempo e
  taxa de afirmações verificadas.

### Fase 9 — Painel Streamlit
- Alertas por semana e segmento, causas, linhas de base e o briefing do agente com as queries
  de cada número. Servidor restrito a `127.0.0.1`.

### Fase 10 — README final
- Manchete com o resultado do backtest, vinda de `reports/backtest.md`.
- Arquitetura em Mermaid, resultados das Fases 5, 7 e 8, erros e correções.
- Limitações, incluindo a seleção do dataset (D-020) e o mapeamento de área (D-027, D-034).
- Instruções para rodar e um GIF do painel.
