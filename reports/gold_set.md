# Gold set: distribuição dos rótulos

_Gerado por `python -m src.labeling.report`. Não edite à mão._

- Rotulados: **250 de 250** (faltam 0).
- Ambíguos / não sei: 17 de 250 (6.8%); dev 4/100 (4.0%); test 13/150 (8.7%). Ficam fora das métricas principais e são reportados à parte (D-028).
- Classes com poucos exemplos (< 5 no dev ou < 8 no test): `produto_diferente_do_anunciado`, `problema_atendimento_ou_comunicacao`.

## Classes por split

| classe | dev | test | total | % amostra (não ambíguos) | % reponderado | área (D-027) |
|---|---|---|---|---|---|---|
| atraso_entrega | 8 | 12 | 20 | 8.6% | 5.0% | logistica |
| nao_recebido | 10 | 19 | 29 | 12.4% | 8.7% | logistica |
| produto_defeituoso_ou_danificado | 6 | 9 | 15 | 6.4% | 4.3% | vendedor |
| produto_diferente_do_anunciado | 8 | 7 | 15 | 6.4% | 3.9% | vendedor |
| pedido_incompleto_ou_errado | 12 | 18 | 30 | 12.9% | 8.3% | vendedor |
| problema_atendimento_ou_comunicacao | 3 | 2 | 5 | 2.1% | 1.3% | atendimento |
| elogio | 39 | 55 | 94 | 40.3% | 63.3% | nenhuma |
| outro | 10 | 15 | 25 | 10.7% | 5.3% | indefinida |
| ambiguo | 4 | 13 | 17 |  |  | indefinida |

Pesos por nota usados na reponderação (participação no universo / na amostra):

| nota | peso |
|---|---|
| 1 | 1.10 |
| 2 | 0.27 |
| 3 | 0.44 |
| 4 | 0.72 |
| 5 | 2.48 |

## Classes × nota (todos os rotulados)

| classe | nota 1 | nota 2 | nota 3 | nota 4 | nota 5 |
|---|---|---|---|---|---|
| atraso_entrega | 4 | 5 | 6 | 5 | 0 |
| nao_recebido | 15 | 10 | 4 | 0 | 0 |
| produto_defeituoso_ou_danificado | 7 | 5 | 3 | 0 | 0 |
| produto_diferente_do_anunciado | 5 | 5 | 4 | 1 | 0 |
| pedido_incompleto_ou_errado | 13 | 11 | 5 | 1 | 0 |
| problema_atendimento_ou_comunicacao | 1 | 1 | 1 | 2 | 0 |
| elogio | 1 | 2 | 8 | 33 | 50 |
| outro | 2 | 6 | 12 | 5 | 0 |
| ambiguo | 2 | 5 | 7 | 3 | 0 |

## Campos auxiliares

| campo | itens | % dos rotulados |
|---|---|---|
| menciona_atraso | 0 | 0.0% |
| pede_reembolso_troca | 0 | 0.0% |
| com causa secundária | 13 | 5.2% |

## Causa secundária

13 de 250 itens têm causa secundária (5.2%).

| causa | causa_secundaria | dev | test | total |
|---|---|---|---|---|
| nao_recebido | problema_atendimento_ou_comunicacao | 2 | 0 | 2 |
| pedido_incompleto_ou_errado | problema_atendimento_ou_comunicacao | 1 | 1 | 2 |
| atraso_entrega | elogio | 1 | 0 | 1 |
| atraso_entrega | outro | 0 | 1 | 1 |
| atraso_entrega | problema_atendimento_ou_comunicacao | 1 | 0 | 1 |
| atraso_entrega | produto_diferente_do_anunciado | 0 | 1 | 1 |
| outro | elogio | 1 | 0 | 1 |
| pedido_incompleto_ou_errado | atraso_entrega | 0 | 1 | 1 |
| pedido_incompleto_ou_errado | outro | 1 | 0 | 1 |
| produto_defeituoso_ou_danificado | problema_atendimento_ou_comunicacao | 1 | 0 | 1 |
| produto_diferente_do_anunciado | problema_atendimento_ou_comunicacao | 0 | 1 | 1 |

## Notas livres

27 itens com nota livre, agrupadas pelo texto da nota (minúsculas).

| nota | causa | dev | test | total |
|---|---|---|---|---|
| qualidade ruim | outro | 6 | 12 | 18 |
| embalagem danificada | outro | 3 | 1 | 4 |
| frete caro | outro | 1 | 1 | 2 |
| frete caro | pedido_incompleto_ou_errado | 1 | 0 | 1 |
| frete caros | outro | 0 | 1 | 1 |
| qualidade ruim | atraso_entrega | 0 | 1 | 1 |

## Verificações de consistência

Contagens que apontam rótulos a revisar; não alteram nenhum rótulo. Os termos de texto são uma busca grosseira (`atras|demor|n[aã]o (?:recebi|chegou)` e `reembols|estorn|devolv|devolu|\btroc|dinheiro de volta`) e podem ter falsos positivos (por exemplo, "não atrasou").

| verificação | dev | test | total |
|---|---|---|---|
| `atraso_entrega` com menciona_atraso = não | 8 | 12 | 20 |
| texto com termo de atraso e menciona_atraso = não | 13 | 20 | 33 |
| texto com termo de reembolso/troca e pede_reembolso_troca = não | 5 | 8 | 13 |
| `elogio` como causa secundária (a classe exclui problema concreto) | 2 | 0 | 2 |
