# Análise de erros

Erros do classificador no **dev set** (o test set não é olhado antes da Fase 5). As listas de
IDs e rótulos vêm de `reports/fase3_dev.md` (`python -m src.eval.dev_report`). Os textos são
descritos com paráfrases curtas, sem copiar a avaliação. Nenhum rótulo e nenhum prompt foi
alterado nesta seção.

## Fase 3 — LLM v1 sem raciocínio (`prompts/classifier_v1.md`), dev

Foram 9 erros em 96 itens não ambíguos. A tabela mostra o rótulo do gold set, a previsão do
modelo e se a previsão segue a regra escrita na taxonomia v1.1.

| review_id | nota | gold | previsto | o que o texto diz (paráfrase) | regra escrita da v1.1 apoia |
|---|---|---|---|---|---|
| `0e0e6e39` | 4 | qualidade | defeito | suporte bom, mas a tampa é frágil e quebrou ao abrir | **previsto** (falha física descrita → defeito) |
| `251571af` | 3 | qualidade | defeito | a alça do cooler puxa o velcro e abre com peso | **previsto** (falha de funcionamento descrita) |
| `e0fa89c5` | 1 | qualidade | diferente | qualidade baixa comparada com a propaganda | **previsto** (comparação com o anúncio → diferente) |
| `14cbabf3` | 3 | entrega | incompleto | comprou dois itens e não recebeu um deles; sem retorno do contato | **previsto** ("comprei dois, recebi um" → incompleto, casos difíceis) |
| `bb385b4d` | 3 | outro | defeito | a caixa veio danificada e com aspecto de velha | gold (embalagem danificada, produto intacto → outro) |
| `31369d4a` | 5 | elogio | entrega | chegou na metade do prazo, cliente satisfeita | gold (positivo, sem problema) |
| `0c4648b0` | 1 | incompleto | entrega | o produto veio errado, e houve problemas com a entrega | gold (causa raiz e primeira citada: produto errado) |
| `3cdb1acf` | 1 | incompleto | diferente | anúncio de 120 cápsulas, recebeu 60; sem resposta do suporte | gold (quantidade errada → incompleto), com fronteira |
| `25221da0` | 4 | atendimento | entrega | "deveriam avisar" que seria retirada nos Correios | nenhum dos dois com clareza (retirada → outro; aviso → atendimento) |

### Categorias

1. **Discordâncias em que a regra apoia o modelo (4 erros).** Nesses itens, a regra escrita
   da taxonomia v1.1 dá a resposta do modelo, não o rótulo. Eles estão anotados em
   `data/gold/discordancias_regra.csv` (D-041).
   - Três vêm do remapeamento mecânico de D-034: itens com a nota "qualidade ruim" viraram
     `qualidade_insatisfatoria`, mas o texto descreve uma falha física ou compara com o
     anúncio. A definição da nova classe exclui esses dois casos.
   - O quarto (`14cbabf3`) é uma entrega parcial rotulada como `problema_entrega`. Pela regra,
     "comprei dois, recebi um" é `pedido_incompleto_ou_errado`.
   - **Regra do usuário (D-041):** os rótulos não mudam. A métrica principal conta esses 4
     itens como erro (estimativa conservadora). Um número alternativo, que os conta como
     acerto quando a previsão segue a regra, aparece só como métrica secundária identificada
     em `reports/fase3_dev.md`.
2. **Palavra-chave de entrega numa avaliação positiva (1 erro, `31369d4a`).** "Prazo" levou a
   `problema_entrega` num elogio explícito. É um erro do modelo.
3. **Regra de embalagem ignorada (1 erro, `bb385b4d`).** O prompt tem a regra, mas o modelo
   tratou a caixa danificada como produto danificado. Em parte, a ambiguidade é real: "caixa"
   pode ser a embalagem do produto.
4. **Causa raiz entre várias causas (1 erro, `0c4648b0`).** Produto errado + problemas de
   entrega: o modelo escolheu a entrega, contra as regras 3 e 4.
5. **Fronteiras entre classes de produto e atendimento (2 erros).**
   - `3cdb1acf`: quantidade errada que também contradiz o anúncio.
   - `25221da0`: aviso sobre retirada nos Correios.

### Observações para a Fase 4
- A confiança do modelo nos erros foi de 0,80 a 0,95. Nesta amostra, ela não separa erros de
  acertos, então não serve como filtro.
- **Nenhum rótulo é alterado com base nas previsões do modelo (D-041).** O prompt também não
  é ajustado para imitar os 4 rótulos da categoria 1: a v2 segue a regra escrita.

## Melhorias de redação para uma versão futura da taxonomia

Registradas aqui, sem aplicar. Valem para uma versão futura da taxonomia, não para a v1.1
usada nas Fases 3 a 5.

- **`qualidade_insatisfatoria` × falha física e × anúncio.** A classe veio do remapeamento
  mecânico das notas "qualidade ruim", mas a definição exclui falha física descrita e
  comparação com o anúncio. Uma versão futura deve escolher entre duas saídas:
  - redefinir a classe para cobrir "fragilidade" como julgamento de qualidade;
  - ou deixar explícito que "frágil, quebrou" é defeito.
- **Entrega parcial × "não recebi".** "Não recebi um dos itens" pode ser lido como problema de
  entrega ou como pedido incompleto. A regra atual (incompleto) deveria aparecer na definição de
  `problema_entrega`, e não só nos casos difíceis.
- **Aviso de retirada nos Correios.** Falta dizer onde fica a queixa "deveriam ter avisado"
  sobre a forma de entrega: hoje há uma tensão entre `outro` (retirada) e atendimento (aviso).
