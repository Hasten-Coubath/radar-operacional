# Análise de erros

Erros do classificador no **dev set** (o test set não é olhado antes da Fase 5). As listas de
IDs e rótulos vêm de `reports/fase3_dev.md` (`python -m src.eval.dev_report`). Os textos são
descritos com paráfrases curtas, sem copiar a avaliação. Nenhum rótulo e nenhum prompt foi
alterado nesta seção.

## Fase 3 — LLM v1 sem raciocínio (`prompts/classifier_v1.md`), dev

Foram 9 erros em 96 itens não ambíguos. A tabela mostra o rótulo do gold set, a previsão do
modelo e se a previsão segue a regra escrita na taxonomia v1.1.

| review_id | nota | gold | previsto | o que o texto diz (paráfrase) | regra escrita da v1.1 favorece |
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

1. **Conflito entre o rótulo e a definição escrita (4 erros).** Nesses itens, a regra da
   taxonomia v1.1 dá a resposta do modelo, não o rótulo.
   - Três vêm do remapeamento mecânico de D-034: itens com a nota "qualidade ruim" viraram
     `qualidade_insatisfatoria`, mas o texto descreve uma falha física ou compara com o
     anúncio. A definição da nova classe exclui esses dois casos.
   - O quarto (`14cbabf3`) é uma entrega parcial rotulada como `problema_entrega`. Pela regra,
     "comprei dois, recebi um" é `pedido_incompleto_ou_errado`.
   - **Não são erros claros do modelo.** Resolver exige decidir qual das duas coisas manda: o
     rótulo ou a definição. Isso fica para o usuário na Fase 4.
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
- **Risco de viés:** revisar só os rótulos que o modelo errou enviesaria o gold set a favor do
  modelo. Se o usuário decidir revisar o conflito da categoria 1, a revisão deve cobrir a
  classe inteira, nos dois splits e sem ver as previsões: os 18 itens de
  `qualidade_insatisfatoria` e as entregas parciais.
