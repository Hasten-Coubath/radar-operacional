# Taxonomia de causas — v1.1

**Versão:** v1.1 (D-034, 2026-10-20). Deriva da v1 da Fase 1 por mudanças mecânicas decididas
depois da rotulagem do gold set: fusão de `atraso_entrega` e `nao_recebido` em
`problema_entrega` e criação de `qualidade_insatisfatoria`. As 8 classes continuam 8. O que
mudou e por quê está em "Mudanças da v1 para a v1.1", no fim. Qualquer mudança futura gera
nova versão, com o motivo registrado em `docs/decisoes.md`.

**Como a v1 foi validada:** leitura de 100 comentários sorteados com semente 42, 20 por nota
(1 a 5), entre as avaliações com comentário (`python -m src.data.sample_taxonomy --show`). Os
IDs estão em `data/samples/amostra_taxonomia.csv` e **ficam fora do gold set** (Fase 2), porque
os exemplos abaixo saem dessa amostra. Nenhum exemplo vem do gold set. A evidência quantitativa
citada vem de `reports/fase1_dados.md` (seção 10) e de `reports/gold_set.md`.

## Regras gerais

1. **Uma causa principal por avaliação**, decidida pelo texto (título + mensagem). A nota pode
   ser vista, mas não decide a causa: há nota 5 com extravio e nota 1 sem causa nenhuma.
2. **Problema concreto vence elogio.** Se o texto descreve uma falha específica (quebrou,
   faltou item, atrasou, veio errado), a causa é essa falha, mesmo com elogios em volta e mesmo
   que o cliente minimize ("veio com uma mancha pequena, mas recomendo"). A gravidade baixa fica
   registrada em outro campo. Ressalvas vagas sem falha específica, num texto positivo no geral
   ("peca um pouquinho na qualidade, mas as crianças amaram"), não são problema concreto.
3. **Várias causas: escolha a causa raiz**, isto é, o que deu errado com o pedido ou o produto.
   `problema_atendimento_ou_comunicacao` só é a causa principal quando a queixa central é o
   suporte ou o processo (falta de resposta, devolução, reembolso, nota fiscal), ou quando é a
   única queixa. Exemplo: "recebi o produto errado, fiz o estorno e não recebi meu dinheiro" é
   `pedido_incompleto_ou_errado`.
4. **Desempate entre causas raiz de mesmo peso:** a que aparece primeiro no texto.
5. **Na dúvida entre duas classes, use as regras de fronteira de cada classe.** Se nenhuma
   resolver, escolha a classe mais específica e marque confiança baixa. `outro` é para o que
   não cabe em nenhuma classe, não para dúvida.
6. **Causa secundária é informativa.** Na rotulagem pode-se registrar uma segunda causa, mas ela
   não entra em nenhuma métrica e o classificador não a prevê.

## Classes

### `problema_entrega`
**Definição:** a queixa principal é a entrega do pedido: atrasou, está demorando, ainda não
chegou, o prazo é longo demais, ou o pedido não vai chegar (extravio, cancelamento).

- **Inclui:**
  - atraso, demora, "ainda não recebi", "não chegou até hoje";
  - perguntas sobre quando o pedido chega;
  - percepção de demora mesmo dentro do prazo ("demorou mas chegou");
  - extravio ou roubo; "consta como entregue, mas não recebi";
  - entrega a outra pessoa ou em endereço errado sem que o cliente tenha recebido;
  - pedido cancelado pela loja, falta de estoque depois da compra, devolução ao remetente.
- **Exclui:**
  - entrega em local diferente quando o cliente recebeu (vai para `outro`);
  - entrega parcial, com parte dos itens faltando (vai para `pedido_incompleto_ou_errado`);
  - produto que chegou danificado (vai para `produto_defeituoso_ou_danificado`).
- **Por que atraso e não recebido são uma classe só (v1.1):** pelo texto não dá para separar
  "ainda não chegou" de "não vai chegar". Em 3.506 pares avaliação–pedido com expressões do tipo
  "não recebi" ou "não chegou", 79,2% dos pedidos **foram entregues depois**
  (`reports/fase1_dados.md`, seção 10). A distinção entre atraso e falha definitiva fica para o
  sinal objetivo (`orders`), não para o texto.
- **Observação:** a percepção de demora dentro do prazo vai discordar do sinal objetivo de
  atraso (`orders.is_late`). Essa discordância é esperada.
- **Exemplos:**
  - `1bfec3e913196c72c1ea06fc8816bd9c` (nota 1): "[entrega atrasada] o prazo terminou e nao
    recebi meu produto"
  - `95e88f02a69c50b2141483c5416bff46` (nota 1): "Comprei a mais de um mês e não chegou até
    hoje!" (o pedido foi entregue 27 dias após a data estimada)
  - `26e781176657ab402172f4428c5f306b` (nota 5): "correios alega o produto foi extraviado, já
    fui lá varias vezes, e não localizaram o produto."
  - `b1db86411f885467912c2992eb18e734` (nota 2): "Nao tinha o produto e ja respondi o
    questionario, ficaram de devolver o valor"

### `produto_defeituoso_ou_danificado`
**Definição:** o produto recebido é o pedido, mas tem problema físico ou de funcionamento.

- **Inclui:**
  - defeito, "não liga", "parou de funcionar";
  - quebra, amassado, vazamento, mancha, peça solta;
  - avaria no transporte que atingiu o produto;
  - material que se rompeu, soltou ou se desfez (descrição física de uma falha).
- **Exclui:**
  - item diferente do que o anúncio mostrava (vai para `produto_diferente_do_anunciado`);
  - item errado ou faltando (vai para `pedido_incompleto_ou_errado`);
  - queixa de qualidade sem falha física descrita (vai para `qualidade_insatisfatoria`);
  - embalagem danificada com o produto intacto (vai para `outro`).
- **Fronteira:** dano de transporte e defeito de fabricação ficam na mesma classe. A
  distinção, que importa para operações, não é feita pela taxonomia (limitação de D-027).
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
  por ele ("inferior ao que imaginava"), vai para esta classe. Se descreve uma falha física,
  vai para `produto_defeituoso_ou_danificado`. Se só julga a qualidade como ruim, sem anúncio
  nem falha física, vai para `qualidade_insatisfatoria`.
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

### `qualidade_insatisfatoria`
**Definição (nova na v1.1):** a queixa central é a qualidade do produto, julgada como ruim,
sem descrever uma falha física específica e sem comparar com o anúncio.

- **Inclui:**
  - "qualidade ruim", "material fraco", "acabamento ruim", "não vale o que custa" quando a
    queixa é a qualidade;
  - insatisfação com a qualidade como mensagem principal do texto.
- **Exclui:**
  - falha física descrita: quebrou, descosturou, não funciona (vai para
    `produto_defeituoso_ou_danificado`);
  - comparação com o anúncio ou com a expectativa criada por ele (vai para
    `produto_diferente_do_anunciado`);
  - ressalva vaga de qualidade num texto positivo no geral (vai para `elogio`, regra geral 2).
- **Origem:** na rotulagem do gold set, as queixas genéricas de qualidade foram para `outro` com
  a nota livre "qualidade ruim"; na v1.1 esses itens foram remapeados para esta classe sem
  novo julgamento (D-034).
- **Exemplos:** a amostra da taxonomia não tem um caso típico, e exemplos do gold set não são
  usados aqui. Caso de fronteira da amostra: `cafcf2436e980eebf92da859451cf7d0` (nota 5): "O
  produto peca um pouquinho na qualidade, entretanto as crianças amaram." é `elogio`, porque o
  texto é positivo no geral.

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
  - cancelamento ou falta de estoque (vai para `problema_entrega`).
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
  - embalagem danificada com o produto intacto (regra explícita na v1.1);
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
| "Não recebi" sem sinal de perda (pedido entregue depois, em geral com atraso) | `problema_entrega` |
| "Nunca recebi" no título, mas o texto diz "até o momento não recebi" | `problema_entrega` |
| "São dois produtos, recebi um, no aguardo do segundo" | `pedido_incompleto_ou_errado` (entrega parcial sem previsão) |
| Produto errado + estorno não recebido | `pedido_incompleto_ou_errado` (causa raiz) |
| "Gostei, mas a panela veio com o cabo quebrado" (nota 4) | `produto_defeituoso_ou_danificado` |
| Lata amassada, "produto excelente" (nota 3) | `produto_defeituoso_ou_danificado` (o produto foi atingido) |
| Caixa amassada, produto em ordem | `outro` (embalagem danificada com produto intacto) |
| "Achei o produto de uma categoria inferior ao que imaginava" | `produto_diferente_do_anunciado` (expectativa criada pelo anúncio) |
| "Qualidade ruim", sem falha física nem anúncio | `qualidade_insatisfatoria` |
| Defeito + "não aparentava ser original" | `produto_defeituoso_ou_danificado` (aparece primeiro; regra 4) |
| Loja sem estoque cancela o pedido | `problema_entrega` |
| Nota 5 com produto extraviado | `problema_entrega` (a nota não decide) |
| Nota 1 sem causa ("NUNCA MAIS COMPRO") | `outro`, mesmo com o sinal objetivo indicando atraso: o rótulo é do texto |

## Leitura exploratória da amostra (v1)

Contagem feita pelo agente (Claude) ao ler as 100 avaliações para validar a v1. **Não é rótulo
de avaliação** (o gold set é rotulado manualmente na Fase 2, sem esses IDs). Fica registrada
com as classes da v1. A amostra tem 20 avaliações por nota, então as proporções **não**
representam o dataset, em que 49,5% dos comentários são nota 5.

| Classe (v1) | Avaliações na amostra |
|---|---|
| `elogio` | 35 |
| `atraso_entrega` | 18 |
| `produto_defeituoso_ou_danificado` | 14 |
| `pedido_incompleto_ou_errado` | 11 |
| `outro` | 10 |
| `produto_diferente_do_anunciado` | 5 |
| `problema_atendimento_ou_comunicacao` | 4 |
| `nao_recebido` | 3 |

O que a leitura mostrou na época:
- Nenhum tema fora da taxonomia apareceu com frequência que justificasse uma classe nova.
  **A rotulagem do gold set mostrou o contrário para "qualidade ruim"** (ver abaixo).
- Cerca de 1 em cada 10 comentários tem mais de uma causa. No gold set, 5,2% têm causa
  secundária registrada.
- `nao_recebido` e `problema_atendimento_ou_comunicacao` são raras. No gold set,
  `nao_recebido` não foi rara (29 de 250 na v1); `problema_atendimento_ou_comunicacao` foi
  (5 de 250).

## Mudanças em relação à proposta inicial (v1)

Nomes mantidos na v1. O que ela definiu, com justificativa:
- **`nao_recebido` restrita a falha definitiva**, com "ainda não recebi" indo para atraso.
  Motivo: a evidência da seção 10 de `reports/fase1_dados.md`. (Na v1.1 as duas classes foram
  fundidas.)
- **Cancelamento e falta de estoque em `nao_recebido`**, em vez de atendimento. (Na v1.1, em
  `problema_entrega`.)
- **Qualidade física em `produto_defeituoso_ou_danificado`; expectativa criada pelo anúncio em
  `produto_diferente_do_anunciado`.**
- **`elogio` inclui satisfação neutra** ("Ok", "Bom"). Motivo: 13,3% dos comentários têm até 2
  palavras, quase sempre sem conteúdo de problema.

## Mudanças da v1 para a v1.1

Decididas pelo usuário em 2026-10-20 (D-034), aplicadas aos rótulos por regras mecânicas
(`python -m src.labeling.migrate`), sem rejulgar itens:

| Mudança | Regra aplicada aos rótulos |
|---|---|
| `atraso_entrega` + `nao_recebido` → `problema_entrega` | as duas viram `problema_entrega`, na causa principal e na secundária |
| Nova classe `qualidade_insatisfatoria` (área `vendedor`) | causa principal `outro` com nota livre "qualidade ruim" |
| Embalagem danificada com produto intacto | permanece em `outro` (regra escrita, nenhum rótulo muda) |
| Causa secundária | informativa, fora das métricas; secundária que ficaria igual à principal é apagada |

Os campos `menciona_atraso` e `pede_reembolso_troca` deixaram de existir (D-033).

## Campos do classificador

- `causa`: uma das 8 classes.
- `gravidade`: `baixa` (incômodo, cliente satisfeito no geral), `media` (problema que exige
  ação), `alta` (não recebeu, produto inutilizável). Não é rotulada no gold set; não tem
  métrica de acerto.
- `confianca` (0 a 1) e `justificativa` curta.
- `area_responsavel` não é prevista: vem do mapeamento fixo causa → área (D-027, revisado em
  D-034).
