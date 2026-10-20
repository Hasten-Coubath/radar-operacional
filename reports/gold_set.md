# Gold set: distribuição dos rótulos (taxonomia v1.1)

_Gerado por `python -m src.labeling.report`. Não edite à mão._

- Rotulados: **250 de 250** (faltam 0).
- Ambíguos / não sei: 17 de 250 (6.8%); dev 4/100 (4.0%); test 13/150 (8.7%). Ficam fora das métricas principais e são reportados à parte (D-031).
- Classes com poucos exemplos (< 5 no dev ou < 8 no test): `produto_diferente_do_anunciado`, `problema_atendimento_ou_comunicacao`, `outro`.
- Os rótulos v1.1 saem mecanicamente dos rótulos v1 (`data/gold/labels_v1.csv`) via `python -m src.labeling.migrate` (D-034); ver a última seção.

## Classes por split

| classe | dev | test | total | % amostra (não ambíguos) | % reponderado | área (D-027) |
|---|---|---|---|---|---|---|
| problema_entrega | 18 | 31 | 49 | 21.0% | 13.6% | logistica |
| produto_defeituoso_ou_danificado | 6 | 9 | 15 | 6.4% | 4.3% | vendedor |
| produto_diferente_do_anunciado | 8 | 7 | 15 | 6.4% | 3.9% | vendedor |
| pedido_incompleto_ou_errado | 12 | 18 | 30 | 12.9% | 8.3% | vendedor |
| qualidade_insatisfatoria | 6 | 12 | 18 | 7.7% | 3.7% | vendedor |
| problema_atendimento_ou_comunicacao | 3 | 2 | 5 | 2.1% | 1.3% | atendimento |
| elogio | 39 | 55 | 94 | 40.3% | 63.3% | nenhuma |
| outro | 4 | 3 | 7 | 3.0% | 1.6% | indefinida |
| ambiguo | 4 | 13 | 17 |  |  | indefinida |

Pesos por nota usados na reponderação (participação no universo / na amostra):

| nota | peso |
|---|---|
| 1 | 1.10 |
| 2 | 0.27 |
| 3 | 0.44 |
| 4 | 0.72 |
| 5 | 2.48 |

## Composição de classes por nota

Contagem e participação de cada classe dentro de cada nota, com todos os rotulados (dev + test; 50 itens por nota).

| classe | nota 1 | nota 2 | nota 3 | nota 4 | nota 5 |
|---|---|---|---|---|---|
| problema_entrega | 19 (38.0%) | 15 (30.0%) | 10 (20.0%) | 5 (10.0%) | 0 |
| produto_defeituoso_ou_danificado | 7 (14.0%) | 5 (10.0%) | 3 (6.0%) | 0 | 0 |
| produto_diferente_do_anunciado | 5 (10.0%) | 5 (10.0%) | 4 (8.0%) | 1 (2.0%) | 0 |
| pedido_incompleto_ou_errado | 13 (26.0%) | 11 (22.0%) | 5 (10.0%) | 1 (2.0%) | 0 |
| qualidade_insatisfatoria | 2 (4.0%) | 5 (10.0%) | 9 (18.0%) | 2 (4.0%) | 0 |
| problema_atendimento_ou_comunicacao | 1 (2.0%) | 1 (2.0%) | 1 (2.0%) | 2 (4.0%) | 0 |
| elogio | 1 (2.0%) | 2 (4.0%) | 8 (16.0%) | 33 (66.0%) | 50 (100.0%) |
| outro | 0 | 1 (2.0%) | 3 (6.0%) | 3 (6.0%) | 0 |
| ambiguo | 2 (4.0%) | 5 (10.0%) | 7 (14.0%) | 3 (6.0%) | 0 |

### Cobertura de uma classificação restrita a notas ≤ 3

Notas 1 a 3 são 36.1% dos comentários do universo. A tabela mostra a fração reponderada do volume de cada classe que está em notas ≤ 3 (sem ambíguos), ou seja, o que a Fase 6 alcançaria classificando só essas notas. `n` é o número de itens da classe; com n pequeno, a fração é instável.

| classe | dev | test | total |
|---|---|---|---|
| problema_entrega | 88.0% (n=18) | 89.6% (n=31) | 89.0% (n=49) |
| produto_defeituoso_ou_danificado | 100.0% (n=6) | 100.0% (n=9) | 100.0% (n=15) |
| produto_diferente_do_anunciado | 100.0% (n=8) | 84.6% (n=7) | 92.2% (n=15) |
| pedido_incompleto_ou_errado | 100.0% (n=12) | 93.8% (n=18) | 96.4% (n=30) |
| qualidade_insatisfatoria | 79.8% (n=6) | 86.5% (n=12) | 83.8% (n=18) |
| problema_atendimento_ou_comunicacao | 15.6% (n=3) | 100.0% (n=2) | 55.6% (n=5) |
| elogio | 3.3% (n=39) | 3.4% (n=55) | 3.4% (n=94) |
| outro | 61.4% (n=4) | 23.3% (n=3) | 42.3% (n=7) |
| todas exceto elogio | 88.2% (n=57) | 88.9% (n=82) | 88.6% (n=139) |

## Causa secundária

13 de 250 itens têm causa secundária (5.2%). É informativa e não entra nas métricas (D-034).

| causa | causa_secundaria | dev | test | total |
|---|---|---|---|---|
| problema_entrega | problema_atendimento_ou_comunicacao | 3 | 0 | 3 |
| pedido_incompleto_ou_errado | problema_atendimento_ou_comunicacao | 1 | 1 | 2 |
| outro | elogio | 1 | 0 | 1 |
| pedido_incompleto_ou_errado | outro | 1 | 0 | 1 |
| pedido_incompleto_ou_errado | problema_entrega | 0 | 1 | 1 |
| problema_entrega | elogio | 1 | 0 | 1 |
| problema_entrega | outro | 0 | 1 | 1 |
| problema_entrega | produto_diferente_do_anunciado | 0 | 1 | 1 |
| produto_defeituoso_ou_danificado | problema_atendimento_ou_comunicacao | 1 | 0 | 1 |
| produto_diferente_do_anunciado | problema_atendimento_ou_comunicacao | 0 | 1 | 1 |

## Notas livres

27 itens com nota livre, agrupadas pelo texto da nota (minúsculas).

| nota | causa | dev | test | total |
|---|---|---|---|---|
| qualidade ruim | qualidade_insatisfatoria | 6 | 12 | 18 |
| embalagem danificada | outro | 3 | 1 | 4 |
| frete caro | outro | 1 | 1 | 2 |
| frete caro | pedido_incompleto_ou_errado | 1 | 0 | 1 |
| frete caros | outro | 0 | 1 | 1 |
| qualidade ruim | problema_entrega | 0 | 1 | 1 |

## Migração v1 → v1.1

Itens cuja causa principal mudou (regras mecânicas de D-034; nenhum item rejulgado):

| v1 | v1.1 | dev | test | total |
|---|---|---|---|---|
| nao_recebido | problema_entrega | 10 | 19 | 29 |
| atraso_entrega | problema_entrega | 8 | 12 | 20 |
| outro | qualidade_insatisfatoria | 6 | 12 | 18 |

Evidência usada para justificar a v1.1, calculada **só no dev** com os rótulos v1:

| evidência (dev, rótulos v1) | itens |
|---|---|
| `nao_recebido` com pedido entregue depois | 5 de 10 |
| `atraso_entrega` com pedido entregue depois | 8 de 8 |
| `outro` com nota "qualidade ruim" | 6 de 10 |
| `outro` com nota "embalagem danificada" | 3 de 10 |
