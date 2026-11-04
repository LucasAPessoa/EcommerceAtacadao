# Feature Specification: Estoque com o Bling como única fonte de saldo

**Feature Branch**: `spec/009-estoque-bling`

**Created**: 2026-11-01

**Status**: Draft

**Input**: User description: "O Bling é a única fonte de saldo. O pedido de venda é criado no Bling quando o pagamento é gerado e fica Em aberto, o que reserva o estoque no Bling para todos os canais. No pagamento, o site muda a situação e lança o estoque. Na expiração ou no cancelamento, o pedido vai para Cancelado e a reserva volta. Acaba a baixa local."

**Issues**: back #59 (esta spec). Absorve a parte de estoque e de criação do pedido da back #58. Relacionadas: back #60 (NF-e), #61 (situação do pedido), #119 (estoque no carrinho, entregue no #125), launch audit #6 (reserva presa) e specs 006 (FR-011, R5) e 008.

## Contexto

Hoje o estoque tem dois donos. A sincronização (spec 006) lê o saldo do Bling e desconta os pedidos pagos ainda não registrados lá, e o pagamento aprovado **também** abate o estoque local. Entre dois ciclos, a venda é descontada duas vezes, e o estorno local devolve quantidade a um saldo que o Bling já recalculou. Além disso, o site não enxerga as vendas dos outros canais até a próxima leitura, e os outros canais não enxergam as reservas do site.

Decisão do usuário (2026-11-01): o Bling é a única fonte de saldo, e a reserva também acontece no Bling. O site cria o pedido de venda no Bling, "Em aberto", no momento em que gera o pagamento. Com a reserva de estoque do Bling ligada para a situação "Em aberto", isso desconta o saldo virtual em todos os canais (Mercado Livre, Shopee e lojas físicas). O site nunca grava baixa nem estorno no próprio estoque.

Fatos verificados na conta Kalun (spike de 2026-11-01, variação 16599274330, app de teste):
- Depois que o usuário ligou "Considerar situações de vendas: Em aberto", criar o pedido (que nasce "Em aberto") baixou o saldo **virtual** de 23 para 22 na hora, e o físico continuou em 23. Passar o pedido para "Cancelado" devolveu o virtual a 23. Nenhum estoque foi lançado.
- Com a reserva desligada (teste anterior), o pedido em aberto não mudava o saldo. **A reserva no Bling é pré-requisito de cada cliente** (ver Assumptions).
- O pedido já nasce "Em aberto". Mandar essa situação na criação devolve erro 400 ("mesma situação"), **mas o pedido é criado assim mesmo**. Uma resposta de erro não garante que o pedido não exista.
- A conta tem um único depósito ("Geral"). As situações de venda incluem Em aberto, Atendido, Cancelado, Em andamento e as personalizadas "Pagamento aprovado" e "Em devolução" (herdam de Em aberto) e "Aguardando etiqueta".
- Os 10 pedidos mais recentes do Mercado Livre estão todos "Atendido". A API não informa se o estoque de um pedido foi lançado.

Neste documento:
- **Saldo virtual** é o saldo do Bling já descontadas as reservas de pedidos em aberto de todos os canais, inclusive os do site.
- **Reserva local** é a quantidade que o site segura entre o início do checkout e o momento em que o saldo lido do Bling já reflete o pedido criado lá. Normalmente dura segundos e se estende se o Bling estiver fora do ar.
- **Disponível no site** = saldo virtual − reservas locais, com mínimo 0.

## Clarifications

### Session 2026-11-01

- Q: Quem é a fonte do saldo? → A: Só o Bling. O site não grava baixa nem estorno no próprio estoque.
- Q: Quando ler o saldo? → A: No ciclo periódico da sync e também na hora, para as variações do carrinho, no início do checkout (Q1-B).
- Q: Pagamento aprovado sem saldo suficiente? → A: O site **cancela e estorna sozinho** o pedido, passa o pedido do Bling para Cancelado e avisa o cliente e o admin. É decisão do usuário (Q2-B) e contraria a recomendação técnica, que era aceitar e marcar "pago a descoberto". Porquê: o usuário prefere não vender o que pode não ter a deixar o lojista resolvendo caso a caso. Com a reserva no Bling, o caso fica raro.
- Q: Um ou vários depósitos? → A: Todos. Vale o saldo total, porque o usuário não pretende usar depósito separado (Q3).
- Q: Onde fica a reserva? → A: No Bling. O pedido é criado "Em aberto" na geração do pagamento; no pagamento, muda de situação e lança o estoque; na expiração ou no cancelamento, vai para "Cancelado" (Q4). O botão "lançado no Bling manualmente" do rascunho cai.
- Q: Variação sem saldo no Bling? → A: Vale 0, fica fora de venda e aparece com aviso no admin (Q5-A).
- Q: Para qual situação o pedido do Bling vai no pagamento aprovado? → A: "Atendido", a situação padrão do Bling e a mesma dos pedidos do Mercado Livre. O id da situação fica numa configuração, sem tela. A situação fina (separação, envio) fica para a #61 (Q6-A).
- Q: Quanto tempo o cliente tem para pagar? → A: O pedido fica "Em aberto" no Bling, segurando estoque, pelo **mesmo** prazo da validade do QR/link do Mercado Pago. Os dois saem de um valor só, hoje `STOCK_RESERVATION_MINUTES=15`. Reserva e QR nunca podem ter prazos diferentes (Q7).

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Cliente compra e o estoque é reservado e baixado no Bling (Priority: P1)

O cliente fecha o carrinho e gera o pagamento. O site cria o pedido no Bling "Em aberto", e o saldo virtual cai em todos os canais. Quando o pagamento é aprovado, o pedido muda de situação e o estoque é lançado no Bling. Em nenhum momento o site desconta a mesma venda duas vezes.

**Why this priority**: É o problema da #59 e o coração da #58. Sem isso, o estoque oscila e há sobrevenda entre canais.

**Independent Test**: Com o Bling simulado e saldo 10, comprar 3. Conferir o pedido Em aberto e o virtual 7; depois do pagamento, conferir o estoque lançado (físico 7, virtual 7) e o disponível no site 7 em todas as etapas.

**Acceptance Scenarios**:

1. **Given** saldo virtual 10, **When** o cliente inicia o checkout com 3, **Then** o saldo das variações do carrinho é lido na hora e o site segura 3 em reserva local (disponível 7).
2. **Given** a reserva local, **When** o pagamento é gerado, **Then** existe exatamente um pedido no Bling, "Em aberto", identificado pelo código do pedido do site, e o saldo virtual passa a 7.
3. **Given** o pedido criado no Bling, **When** o saldo lido já reflete esse pedido, **Then** a reserva local deixa de contar e o disponível continua 7 (nunca 4).
4. **Given** o pagamento aprovado, **When** o site confirma o pedido, **Then** o pedido do Bling muda para a situação de pago e o estoque é lançado uma única vez. O saldo físico passa a 7, o virtual continua 7 e o disponível no site continua 7.
5. **Given** dois clientes disputando as últimas 2 unidades, **When** os dois iniciam o checkout ao mesmo tempo, **Then** só um consegue reservar.

---

### User Story 2 - Pagamento expira, falha ou o cliente desiste (Priority: P1)

A reserva volta para todos os canais sem ninguém mexer no Bling.

**Why this priority**: Uma reserva que não volta prende o estoque em todos os canais, inclusive no Mercado Livre.

**Independent Test**: Gerar o pagamento, deixar expirar e conferir o pedido do Bling em Cancelado, o virtual de volta e nenhum estoque lançado.

**Acceptance Scenarios**:

1. **Given** o pedido Em aberto no Bling, **When** o prazo do pagamento passa, **Then** o pedido vai para Cancelado e o saldo virtual volta.
2. **Given** uma falha ao iniciar o pagamento no provedor, **When** o checkout termina com erro, **Then** a reserva local é liberada e o pedido do Bling, se tiver sido criado, vai para Cancelado.
3. **Given** que o Bling está fora do ar no momento de cancelar, **Then** o cancelamento fica pendente e é tentado de novo até dar certo, e o admin vê a pendência.

---

### User Story 3 - Saldo do Bling não cobre um pagamento aprovado (Priority: P2)

Uma reserva local que ainda não chegou ao Bling, um ajuste manual no Bling ou um pagamento aprovado depois da expiração deixam o pedido pago sem saldo.

**Why this priority**: Fica raro com a reserva no Bling, mas precisa de uma regra previsível (Q2-B).

**Independent Test**: Aprovar o pagamento de um pedido cujo pedido do Bling já foi cancelado por expiração, com o saldo virtual abaixo da quantidade.

**Acceptance Scenarios**:

1. **Given** o pagamento aprovado e a quantidade acima do disponível, **When** o site processa a aprovação, **Then** o site cancela o pedido, estorna o pagamento integralmente, mantém (ou põe) o pedido do Bling em Cancelado, não lança estoque e avisa o cliente.
2. **Given** um pagamento aprovado depois da expiração e com saldo suficiente, **When** o site processa a aprovação, **Then** o pedido segue normalmente: o site cria ou reabre o pedido no Bling e lança o estoque, sem pedido duplicado.
3. **Given** um pedido cancelado por falta de saldo, **Then** o admin vê o pedido marcado e o contador no dashboard.

---

### User Story 4 - Pedido pago cancelado ou estornado depois (Priority: P2)

O admin cancela um pedido pago, ou o pagamento sofre estorno ou chargeback.

**Why this priority**: O estoque já foi lançado no Bling, então precisa voltar lá.

**Independent Test**: Cancelar um pedido pago e conferir o estoque estornado no Bling e o pedido em Cancelado.

**Acceptance Scenarios**:

1. **Given** um pedido pago com estoque lançado, **When** o pedido é cancelado ou estornado no site, **Then** o estoque é estornado no Bling uma única vez e o pedido vai para Cancelado.
2. **Given** o pedido já enviado ou com NF-e emitida, **Then** o site não estorna o estoque sozinho e marca o pedido para o admin resolver no Bling (devolução fora do escopo).

---

### User Story 5 - Admin entende o estoque e as pendências com o Bling (Priority: P3)

**Acceptance Scenarios**:

1. **Given** uma variação, **Then** o admin vê o saldo físico e o virtual do Bling, as reservas locais, o disponível no site e a hora da última leitura.
2. **Given** um pedido do site, **Then** o admin vê o número do pedido no Bling, a situação lá e as pendências de envio (criação, troca de situação, lançamento ou estorno), com a última tentativa e o erro.
3. **Given** uma leitura de saldo atrasada além do limite, ou pendências com o Bling, **Then** o dashboard mostra os contadores.

### Edge Cases

- **Erro na criação que criou o pedido assim mesmo** (visto no spike): antes de criar ou tentar de novo, o site procura o pedido pelo código do site no Bling. Nunca existem dois pedidos do Bling para o mesmo pedido do site.
- **Bling fora do ar ao gerar o pagamento**: o pagamento é gerado assim mesmo (o checkout não trava, constituição IV). A reserva local continua valendo até o pedido existir no Bling e o saldo refletir isso. A criação do pedido fica pendente e é tentada de novo.
- **Pagamento aprovado antes de o pedido existir no Bling**: o site cria o pedido e, na sequência, faz a transição de pago e o lançamento, nessa ordem.
- **Variação sem saldo no Bling**: vale 0, fica fora de venda e aparece com aviso no admin.
- **Reserva do Bling desligada num cliente**: o saldo virtual não cai com o pedido em aberto. O site detecta isso pela leitura depois da criação e avisa o admin, e a reserva local continua até o pagamento ou a expiração (ver FR-013).
- **Pedido do Bling alterado à mão** (situação ou itens mudados pelo lojista): o site não sobrescreve. Ele registra a divergência para o admin e não tenta lançar nem estornar em cima de um estado inesperado.
- **Variação despublicada ou excluída** com pedido em aberto: segue a regra de expiração ou pagamento. Nada mexe no saldo fora do pedido.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: O sistema MUST tratar o saldo do Bling como a única fonte de estoque. Nenhuma operação do site altera o saldo guardado da variação; o efeito no estoque acontece no Bling, pelo pedido de venda.
- **FR-002**: O disponível no site MUST ser o saldo virtual do Bling (todos os depósitos) menos as reservas locais, com mínimo 0, e MUST ser o mesmo número no carrinho, no checkout, na loja e no admin.
- **FR-003**: No início do checkout, o sistema MUST ler na hora o saldo das variações do carrinho e criar a reserva local com a garantia atual contra concorrência. Se a leitura falhar, usa o último saldo conhecido. O saldo também é lido no ciclo periódico da sync.
- **FR-004**: Ao gerar o pagamento, o sistema MUST criar no Bling um pedido de venda "Em aberto" com o cliente, os itens por variação, o frete e o total, identificado pelo código do pedido do site. Esse pedido MUST ser único por pedido do site, mesmo com retentativas e respostas de erro.
- **FR-005**: A reserva local MUST deixar de contar só quando o saldo lido do Bling já reflete o pedido criado lá (leitura posterior à criação).
- **FR-006**: Na aprovação do pagamento, o sistema MUST mudar o pedido do Bling para "Atendido" (id da situação em configuração, Q6) e lançar o estoque do pedido uma única vez, sem que a reserva e o lançamento descontem a mesma venda duas vezes.
- **FR-007**: Na expiração do pagamento, na falha ou no cancelamento antes do pagamento, o sistema MUST passar o pedido do Bling para "Cancelado" e liberar a reserva local. O prazo da reserva (local e do pedido "Em aberto" no Bling) e o prazo em que o Mercado Pago aceita o pagamento MUST sair de um único valor configurado (hoje 15 minutos) e MUST ser iguais: o pagamento nunca vive além da reserva, e a reserva nunca expira enquanto o pagamento ainda pode ser feito. Nenhuma configuração pode desligar o prazo do Mercado Pago e deixar só o da reserva (Q7). Um teste automatizado MUST falhar se os dois prazos se separarem.
- **FR-008**: Quando o pagamento for aprovado e a quantidade não couber no disponível, o sistema MUST cancelar o pedido, estornar o pagamento integralmente, manter ou pôr o pedido do Bling em "Cancelado" sem lançar estoque, avisar o cliente e marcar o pedido para o admin (Q2-B). Se o estorno falhar, o pedido entra na reconciliação existente.
- **FR-009**: Cancelamento, estorno ou chargeback de pedido pago com estoque lançado MUST estornar o estoque no Bling uma única vez e passar o pedido para "Cancelado", salvo se o pedido já tiver sido enviado ou faturado. Nesse caso, fica marcado para o admin.
- **FR-010**: Toda ação no Bling (criar, mudar situação, lançar, estornar) MUST passar por uma fila persistida, gravada na mesma transação da mudança de estado do pedido no site, com retentativa limitada e sem efeito em dobro. Falha do Bling não perde a ação nem trava o checkout.
- **FR-011**: Uma verificação periódica MUST conferir os pedidos do site contra o Bling (existência, situação) e corrigir ou sinalizar divergências, inclusive pedidos criados por uma resposta de erro.
- **FR-012**: O admin MUST ver, por variação, o saldo físico e o virtual, as reservas locais, o disponível e a última leitura. Por pedido, MUST ver o número no Bling, a situação e as pendências. O dashboard MUST contar as pendências com o Bling, as variações sem saldo ou com leitura atrasada e os pedidos cancelados por falta de saldo.
- **FR-013**: Se o saldo virtual não cair depois da criação de um pedido em aberto (reserva do Bling desligada), o sistema MUST avisar o admin e manter a reserva local daquele pedido até o pagamento ou a expiração.

### Key Entities

- **Variação (estoque)**: guarda o último saldo físico e o virtual do Bling e a data da última leitura. O disponível é calculado.
- **Reserva local**: quantidade por variação ligada a um pedido do site, com prazo e datas. Deixa de contar quando o Bling reflete o pedido, quando expira ou quando o pedido é cancelado.
- **Pedido do site**: ganha o id e o número do pedido no Bling, a situação lá, se o estoque foi lançado ou estornado e o motivo "cancelado por falta de saldo".
- **Ação pendente com o Bling**: o que precisa acontecer no Bling para um pedido (criar, mudar situação, lançar, estornar), com tentativas, último erro e próxima tentativa.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: Em 100% dos cenários de teste (compra, expiração, falha do pagamento, cancelamento antes e depois do pagamento, estorno), o saldo do Bling termina igual ao inicial menos as vendas efetivadas, sem dupla baixa nem estoque preso.
- **SC-002**: Nenhum pedido do site gera mais de um pedido no Bling, mesmo com N retentativas e respostas de erro simuladas.
- **SC-003**: Em teste de concorrência com N checkouts disputando K unidades (N > K), no máximo K reservas são criadas.
- **SC-004**: Com o Bling fora do ar por 1 hora, nenhum checkout é bloqueado por isso e todas as ações pendentes são concluídas depois que o Bling volta, sem intervenção manual.
- **SC-005**: Uma venda no site aparece descontada no saldo virtual do Bling (e, portanto, nos outros canais) no mesmo minuto em que o pagamento é gerado, quando o Bling está disponível.

## Assumptions

- **Pré-requisito por cliente**: a reserva de estoque do Bling ligada para a situação "Em aberto" ("Considerar situações de vendas"). Ela entra no checklist de provisionamento (#65), e o site avisa quando ela não estiver ligada (FR-013).
- O saldo usado é o saldo virtual total, de todos os depósitos (Q3). Hoje a conta tem um só ("Geral"). O lançamento usa o depósito padrão.
- O cliente vira um contato no Bling quando o pagamento é gerado, mesmo que não chegue a pagar. O usuário aceita esse efeito colateral: contatos de quem não comprou e pedidos cancelados no Bling a cada pagamento abandonado.
- Ficam fora desta spec: a NF-e (#60), as demais transições de situação depois do pago, como enviado e entregue (#61), o despacho (#63) e o registro detalhado de forma de pagamento e parcelas no pedido do Bling (resto da #58).
- A ordem exata entre mudar o pedido para "Atendido" e lançar o estoque (FR-006), e a confirmação de que "Atendido" não continua reservando depois do lançamento, são validadas no plano com um spike na conta de teste. A spec só exige o resultado: uma baixa só.
- A garantia contra concorrência do checkout (locks por variação) continua como está.
- **Prazo do Mercado Pago (Q7)**: o site manda o `expiration_time` da Order (Checkout Pro) a partir do mesmo valor da reserva. O spike de 2026-11-02 mostrou que o MP não fecha a Order no segundo exato (uma Order `PT1M` seguia `created` 1 min e 39 s depois de vencer e só apareceu `canceled/expired` cerca de 3 min depois). Por isso, a reserva local e o pedido "Em aberto" do Bling só são liberados depois que o cancelamento remoto da Order é confirmado: o estoque fica segurado enquanto o pagamento for possível, e o valor segue em 15 min (research R1). Um pagamento aprovado depois disso cai no FR-008.
