# Taxonomia de causas — v1

**Versão:** v1 (nomes das 8 classes da proposta inicial mantidos; definições, critérios e regras
escritos na Fase 1). Qualquer mudança futura gera v2, com o motivo registrado em
`docs/decisoes.md`.

**Como foi validada:** leitura de 100 comentários sorteados com semente 42, 20 por nota (1 a 5),
entre as avaliações com comentário (`python -m src.data.sample_taxonomy --show`). Os IDs estão
em `data/samples/amostra_taxonomia.csv` e **ficam fora do gold set** (Fase 2), porque os
exemplos abaixo saem dessa amostra. A evidência quantitativa citada vem de
`reports/fase1_dados.md` (seção 10).

## Regras gerais

1. **Uma causa principal por avaliação**, decidida pelo texto (título + mensagem). A nota pode
   ser vista, mas não decide a causa: há nota 5 com extravio e nota 1 sem causa nenhuma.
2. **Problema concreto vence elogio.** Se o texto descreve uma falha específica (quebrou,
   faltou item, atrasou, veio errado), a causa é essa falha, mesmo com elogios em volta e mesmo
   que o cliente minimize ("veio com uma mancha pequena, mas recomendo"). A gravidade baixa fica
   registrada em outro campo. Ressalvas vagas sem falha específica ("peca um pouquinho na
   qualidade, mas as crianças amaram") não são problema concreto.
3. **Várias causas: escolha a causa raiz**, isto é, o que deu errado com o pedido ou o produto.
   `problema_atendimento_ou_comunicacao` só é a causa principal quando a queixa central é o
   suporte ou o processo (falta de resposta, devolução, reembolso, nota fiscal), ou quando é a
   única queixa. Exemplo: "recebi o produto errado, fiz o estorno e não recebi meu dinheiro" é
   `pedido_incompleto_ou_errado`.
4. **Desempate entre causas raiz de mesmo peso:** a que aparece primeiro no texto.
5. **Na dúvida entre duas classes, use as regras de fronteira de cada classe.** Se nenhuma
   resolver, escolha a classe mais específica e marque confiança baixa. `outro` é para o que
   não cabe em nenhuma classe, não para dúvida.

## Classes

### `atraso_entrega`
**Definição:** a queixa principal é o tempo de entrega: atrasou, está demorando, ainda não
chegou, ou o prazo é longo demais.

- **Inclui:**
  - "ainda não recebi" ou "não chegou até hoje" **sem** indicação de que o pedido se perdeu ou foi cancelado;
  - perguntas sobre quando o pedido chega;
  - percepção de demora mesmo dentro do prazo ("demorou mas chegou").
- **Exclui:** extravio, entrega para outra pessoa, "consta como entregue mas não recebi" e
  pedido cancelado (vão para `nao_recebido`).
- **Por que "não recebi" fica aqui:** em 3.506 pares avaliação–pedido com expressões do tipo
  "não recebi" ou "não chegou", 79,2% dos pedidos **foram entregues depois** (57,2% dos
  entregues com atraso), e em 63,6% a pesquisa foi enviada antes da entrega. Na maioria das
  vezes o texto descreve um atraso em andamento, não uma perda. Pelo texto, não dá para saber
  se o pedido chegará.
- **Observação:** a percepção de demora dentro do prazo vai discordar do sinal objetivo de
  atraso (`orders.is_late`). Essa discordância é esperada e será medida na Fase 3.
- **Exemplos:**
  - `1bfec3e913196c72c1ea06fc8816bd9c` (nota 1): "[entrega atrasada] o prazo terminou e nao
    recebi meu produto"
  - `95e88f02a69c50b2141483c5416bff46` (nota 1): "Comprei a mais de um mês e não chegou até
    hoje!" (o pedido foi entregue 27 dias após a data estimada)

### `nao_recebido`
**Definição:** o texto indica que o pedido **não vai chegar** ou que houve falha definitiva
na entrega.

- **Inclui:**
  - extravio ou roubo;
  - "consta como entregue, mas não recebi";
  - entrega a outra pessoa ou em endereço errado sem que o cliente tenha recebido;
  - pedido cancelado pela loja;
  - falta de estoque depois da compra;
  - devolução ao remetente.
- **Exclui:**
  - "ainda não recebi" sem sinal de falha definitiva (vai para `atraso_entrega`);
  - entrega em local diferente quando o cliente recebeu (vai para `outro`).
- **Exemplos:**
  - `26e781176657ab402172f4428c5f306b` (nota 5): "correios alega o produto foi extraviado, já
    fui lá varias vezes, e não localizaram o produto."
  - `b1db86411f885467912c2992eb18e734` (nota 2): "Nao tinha o produto e ja respondi o
    questionario, ficaram de devolver o valor"

### `produto_defeituoso_ou_danificado`
**Definição:** o produto recebido é o pedido, mas tem problema físico ou de funcionamento.

- **Inclui:**
  - defeito, "não liga", "parou de funcionar";
  - quebra, amassado, vazamento, mancha, peça solta;
  - avaria no transporte;
  - material claramente frágil ou de baixa qualidade (descrição física do problema).
- **Exclui:**
  - item diferente do que o anúncio mostrava (vai para `produto_diferente_do_anunciado`);
  - item errado ou faltando (vai para `pedido_incompleto_ou_errado`).
- **Fronteira:** dano de transporte e defeito de fabricação ficam na mesma classe. A
  distinção, que importa para operações, fica no campo de área responsável (proposta abaixo).
- **Exemplos:**
  - `49478943bfa2f9242c0d54d1fc33ddc2` (nota 1): "Chegou com defeito,não liga"
  - `507abf30b3c07f378435c96db2f7e764` (nota 2): "O produto chegou amassado e com um pouco de
    perda do líquido do frasco"

### `produto_diferente_do_anunciado`
**Definição:** o produto recebido é o que foi pedido, mas não corresponde ao anúncio
(foto, descrição, cor, tamanho, material, marca ou originalidade).

- **Inclui:**
  - "diferente da foto";
  - "não é da cor do anúncio";
  - "achei que seria maior" ou "menor do que parecia";
  - suspeita de produto não original.
- **Exclui:**
  - item trocado, ou seja, outro produto, não o pedido (vai para `pedido_incompleto_ou_errado`);
  - defeito ou dano (vai para `produto_defeituoso_ou_danificado`).
- **Fronteira com qualidade:** se a queixa compara com o anúncio ou com a expectativa criada
  por ele ("inferior ao que imaginava"), vai para esta classe. Se descreve uma falha física
  sem referência ao anúncio, vai para `produto_defeituoso_ou_danificado`.
- **Exemplos:**
  - `ea064d00128289d0d4d756e625ef5431` (nota 2): "Bem diferente do que aparece na foto"
  - `3478b281f318f515dbd413fd55862965` (nota 2): "Não veio na cor conforme o anuncio, a
    mochila não tem espuma interna. No mais tudo tranquilo"

### `pedido_incompleto_ou_errado`
**Definição:** o conteúdo da entrega não confere com o pedido: faltou item, faltou parte ou
acessório, quantidade errada ou veio outro produto.

- **Inclui:**
  - "comprei 2, veio 1";
  - "veio sem o forro";
  - "recebi algo que não pedi";
  - "não é o mesmo produto que comprei";
  - entrega parcial sem previsão para o restante.
- **Exclui:**
  - o produto certo diferente do anúncio (vai para `produto_diferente_do_anunciado`);
  - itens que chegaram em entregas separadas mas completas (vai para `outro`).
- **Exemplos:**
  - `e781a0e40c96ff7df9ae343a8d38641d` (nota 1): "[Comprei dois filtros...] Comprei dois
    filtros e a embalagem chegou com apenas um filtro... E o outro?"
  - `0d9d92adaf307d05e2a54228263baaeb` (nota 1): "Quero devolver pois recebi algo que não
    pedi"

### `problema_atendimento_ou_comunicacao`
**Definição:** a queixa central é o relacionamento com a loja ou a plataforma.

- **Inclui:**
  - falta de resposta e informações erradas;
  - dificuldade para devolver, trocar ou receber reembolso;
  - problemas de nota fiscal;
  - avisos confusos sobre o pedido.
- **Exclui:**
  - quando há uma causa raiz concreta (atraso, defeito, item errado) e o atendimento é só
    consequência; nesse caso vale a causa raiz (regra geral 3);
  - cancelamento ou falta de estoque (vai para `nao_recebido`).
- **Exemplos:**
  - `2f97a0e75596224896b36a3fe920d68c` (nota 2): "não respondem a e-mails, houve problema na
    entrega e nem deram muita satisfação nem importancia"
  - `f728c2517b00ca171dac670e094d262d` (nota 4): "Só não gostei, pois recebi um email dizendo
    que a compra tinha tido um problema, tem tentei solucionar por email e ninguém respondeu.
    Mas a compra chegou dias depois."

### `elogio`
**Definição:** avaliação positiva ou neutra sem nenhum problema concreto.

- **Inclui:**
  - "Ótimo", "Recomendo", "chegou antes do prazo";
  - satisfação neutra ("Ok", "Bom", "Tudo certo", "Entrega sem problemas").
- **Exclui:** qualquer texto com problema concreto (regra geral 2).
- **Exemplos:**
  - `44ee1d72759534d74ec07bd7da8bb813` (nota 5): "Amei o produto,amei comprar nesse site.
    Fácil de fazer a compra e chegou no prazo,melhor ainda bem antes do prazo..."
  - `567242d293a95247df6e29f6ff726c85` (nota 4): "Super rápida a entrega, e produto conforme
    esperava."

### `outro`
**Definição:** comentário sem causa coberta pelas classes acima.

- **Inclui:**
  - preço ou frete caro;
  - sugestões (manual, envio junto);
  - retirada nos Correios em vez de entrega em casa;
  - entrega em local diferente quando o cliente recebeu;
  - reclamação genérica sem causa identificável ("NUNCA MAIS COMPRO NESSA PORCARIA!");
  - textos vagos ("Pedido e entrega sem detalhes");
  - comentários sobre o uso do produto que não indicam falha.
- **Exclui:** qualquer texto que caiba numa classe específica.
- **Exemplos:**
  - `c7e94485297142c1aef3cbada0b74763` (nota 3): "O produto recebido é ótimo, pena q o frete
    encarece muito."
  - `16edf1427ade7c306ecc65556b6a6345` (nota 3): "O produto atende as expectativas. Somente a
    entrega não foi como sempre, ao invés de chegar em minha residência tive de ir aos
    Correios buscar."

## Casos difíceis encontrados na amostra

| Situação | Decisão |
|---|---|
| "Não recebi" sem sinal de perda (pedido entregue depois, em geral com atraso) | `atraso_entrega` |
| "Nunca recebi" no título, mas o texto diz "até o momento não recebi" | `atraso_entrega` (nada indica perda definitiva) |
| "São dois produtos, recebi um, no aguardo do segundo" | `pedido_incompleto_ou_errado` (entrega parcial sem previsão) |
| Produto errado + estorno não recebido | `pedido_incompleto_ou_errado` (causa raiz) |
| "Gostei, mas a panela veio com o cabo quebrado" (nota 4) | `produto_defeituoso_ou_danificado` |
| Lata amassada, "produto excelente" (nota 3) | `produto_defeituoso_ou_danificado` |
| "Achei o produto de uma categoria inferior ao que imaginava" | `produto_diferente_do_anunciado` (expectativa criada pelo anúncio) |
| Defeito + "não aparentava ser original" | `produto_defeituoso_ou_danificado` (aparece primeiro; regra 4) |
| Loja sem estoque cancela o pedido | `nao_recebido` |
| Nota 5 com produto extraviado | `nao_recebido` (a nota não decide) |
| Nota 1 sem causa ("NUNCA MAIS COMPRO") | `outro`, mesmo com o sinal objetivo indicando atraso: o rótulo é do texto |

## Leitura exploratória da amostra

Contagem feita pelo agente (Claude) ao ler as 100 avaliações para validar a taxonomia. **Não é
rótulo de avaliação** (o gold set é rotulado manualmente na Fase 2, sem esses IDs). A amostra
tem 20 avaliações por nota, então as proporções **não** representam o dataset, em que 49,5%
dos comentários são nota 5.

| Classe | Avaliações na amostra |
|---|---|
| `elogio` | 35 |
| `atraso_entrega` | 18 |
| `produto_defeituoso_ou_danificado` | 14 |
| `pedido_incompleto_ou_errado` | 11 |
| `outro` | 10 |
| `produto_diferente_do_anunciado` | 5 |
| `problema_atendimento_ou_comunicacao` | 4 |
| `nao_recebido` | 3 |

O que a leitura mostrou:
- **Nenhum tema fora da taxonomia apareceu com frequência** que justifique uma classe nova.
  `outro` ficou com 10 de 100, de temas variados.
- **Cerca de 1 em cada 10 comentários tem mais de uma causa** (atraso + atendimento, item
  errado + reembolso, defeito + "não original"). Daí as regras gerais 3 e 4 e os campos
  auxiliares.
- **`nao_recebido` e `problema_atendimento_ou_comunicacao` são raras.** Com ~250 avaliações
  no gold set, devem ficar com poucos exemplos e F1 instável. Isso será verificado na Fase 2.

## Mudanças em relação à proposta inicial

Nomes mantidos. O que esta versão definiu, com justificativa:
- **`nao_recebido` restrita a falha definitiva**, com "ainda não recebi" indo para atraso.
  Motivo: a evidência da seção 10 de `reports/fase1_dados.md`.
- **Cancelamento e falta de estoque em `nao_recebido`**, em vez de atendimento. Motivo: para
  o cliente, o pedido não chega. São raros (2 de 100), o que não justifica uma classe própria.
- **Qualidade física em `produto_defeituoso_ou_danificado`; expectativa criada pelo anúncio em
  `produto_diferente_do_anunciado`.**
- **`elogio` inclui satisfação neutra** ("Ok", "Bom"). Motivo: 13,3% dos comentários têm até 2
  palavras, quase sempre sem conteúdo de problema.

## Campos auxiliares (proposta, a confirmar nas Fases 2 e 3)

- `menciona_atraso` (sim/não): independente da causa principal. Permite comparar com
  `orders.is_late` mesmo quando a causa principal é outra.
- `area_responsavel`: `logistica` (transporte, prazo, avaria no transporte), `vendedor`
  (produto, anúncio, separação do pedido, estoque), `atendimento` ou `indefinida`.
- `gravidade`: `baixa` (incômodo, cliente satisfeito no geral), `media` (problema que exige
  ação), `alta` (não recebeu, produto inutilizável, pede reembolso ou troca).
- `pede_reembolso_troca` (sim/não).
