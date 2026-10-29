# Feature Specification: Faixas de preço por variação

**Feature Branch**: `005-faixas-por-variacao`

**Created**: 2026-10-28

**Status**: Draft

**Input**: User description: "Faixa de preço por variação (opção A, decisão de 2026-10-23): cada embalagem tem as próprias faixas; a faixa de uma variação nunca se aplica a outra e a quantidade considerada é a da própria variação. Preço da faixa abaixo do preço-base. Faixas existentes migradas sem perda. Contrato de pricing-tiers por variação. A sync do Bling não recria faixas por produto."

**Issues**: back #91 (esta spec a implementa), front #73 (consumo na loja e no admin). Aviso de faixa acima do preço-base: back #123 e front #81 (depois desta spec). Relacionadas: back #53, #56, #80, #113; front #24, #31, #33.

## Contexto

Hoje a faixa de preço pertence ao produto e vale para qualquer embalagem dele, contando a quantidade somada de todas as embalagens. No seed, o "Arroz Tipo 1" tem Pacote 5 kg (R$ 27,90) e Saca 25 kg (R$ 119,90), com a faixa "a partir de 10 un., R$ 25,90" pensada para o pacote: 10 sacas saem a R$ 25,90 cada, e 5 pacotes + 5 sacas também atingem a faixa. É prejuízo direto em cada pedido assim.

O preço-base de cada embalagem vem do Bling (gravado na criação pela sincronização e editável no admin). O Bling não tem faixas de preço por quantidade: as faixas são configuração só do site, por embalagem (esclarecido pelo usuário em 2026-10-28).

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Cliente paga a faixa certa da embalagem que comprou (Priority: P1)

O cliente adiciona uma embalagem ao carrinho e o preço unitário cai para a faixa só quando a quantidade daquela embalagem atinge uma faixa dela. Outras embalagens do mesmo produto não contam nem emprestam faixas.

**Why this priority**: É o defeito que gera prejuízo; sem isso a loja não pode vender produtos com mais de uma embalagem.

**Independent Test**: Com o seed, adicionar 10 sacas de 25 kg cobra R$ 119,90 cada; 10 pacotes de 5 kg cobram R$ 25,90 cada; 5 pacotes + 5 sacas cobram o preço-base de cada um.

**Acceptance Scenarios**:

1. **Given** a Saca 25 kg sem faixas próprias, **When** o cliente leva 10 sacas, **Then** o carrinho e o pedido cobram R$ 119,90 por saca.
2. **Given** o Pacote 5 kg com faixa "≥ 10 un. R$ 25,90", **When** o cliente leva 10 pacotes, **Then** cobra R$ 25,90 e o pedido registra a faixa aplicada (quantidade mínima e preço).
3. **Given** 5 pacotes e 5 sacas no carrinho, **When** o cliente fecha o pedido, **Then** nenhuma faixa se aplica.
4. **Given** um pedido já criado, **When** as faixas mudam depois, **Then** o pedido mantém o preço e a faixa registrados no momento da compra.

---

### User Story 2 - Admin cadastra faixas por embalagem (Priority: P1)

O administrador cria, edita e remove faixas escolhendo a embalagem; a loja exibe cada embalagem só com as próprias faixas.

**Why this priority**: Sem cadastro por embalagem a correção do US1 não tem como ser configurada; o front #73 depende deste contrato.

**Independent Test**: Criar faixa para a Saca 25 kg e conferir que ela aparece só nessa embalagem no catálogo e no admin.

**Acceptance Scenarios**:

1. **Given** um produto com duas embalagens, **When** o admin cria uma faixa para uma delas, **Then** a faixa aparece apenas nessa embalagem.
2. **Given** uma embalagem de R$ 119,90, **When** o admin tenta salvar faixa de R$ 119,90 ou mais, **Then** é recusada com mensagem em português.
3. **Given** uma faixa "≥ 10" já existe na embalagem, **When** o admin cria outra "≥ 10" na mesma embalagem, **Then** é recusada; na outra embalagem é aceita.
4. **Given** uma tentativa de criar faixa sem indicar a embalagem, **Then** é recusada.

---

### User Story 3 - Faixas existentes continuam valendo após a migração (Priority: P2)

As faixas cadastradas antes da mudança passam a pertencer a uma embalagem, sem perda.

**Why this priority**: Evita que a correção apague configuração existente; só roda uma vez.

**Independent Test**: Contar as faixas antes e depois da migração e conferir a embalagem atribuída a cada uma.

**Acceptance Scenarios**:

1. **Given** produto com uma embalagem, **Then** suas faixas vão para essa embalagem.
2. **Given** produto com várias embalagens, **Then** cada faixa vai para a embalagem ativa de menor preço-base acima do preço da faixa; sem nenhuma, para a de menor preço-base.
3. **Given** o seed, **Then** a faixa de R$ 25,90 do arroz fica no Pacote 5 kg.

### Edge Cases

- Embalagem inativa ou removida: suas faixas não aparecem na loja nem se aplicam.
- Mudança do preço-base (no admin ou, no futuro, pelo Bling) para valor igual ou abaixo de uma faixa existente: a alteração é aceita, nenhuma faixa muda e o checkout cobra o menor entre o preço-base e a faixa elegível. O aviso ao admin é escopo da back #123 / front #81.
- Faixa migrada com preço igual ou acima de todas as embalagens: vai para a de menor preço-base e entra no aviso da back #123.
- Duas faixas no backfill que caem na mesma embalagem com a mesma quantidade mínima: impossível hoje (unicidade por produto já impede).
- Produto sem embalagens com faixas cadastradas: a faixa órfã é mantida para revisão e não se aplica.
- Sincronização do Bling cria ou atualiza embalagens: não cria, move nem apaga faixas.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: Toda faixa de preço MUST pertencer a exatamente uma embalagem (variação) de produto.
- **FR-002**: O preço unitário de um item MUST considerar só as faixas da própria embalagem e a quantidade dessa embalagem no carrinho ou pedido.
- **FR-003**: Carrinho e checkout MUST recalcular o preço no servidor com a regra do FR-002; o pedido MUST registrar o preço e a quantidade mínima da faixa aplicada.
- **FR-004**: O preço cobrado MUST ser o menor entre o preço-base e o da faixa elegível de maior quantidade mínima.
- **FR-005**: Criar ou editar faixa MUST exigir a embalagem e recusar preço igual ou maior que o preço-base dela, com mensagem em português. Alterar o preço-base MUST NOT ser bloqueado nem alterar faixas.
- **FR-006**: A quantidade mínima MUST ser única por embalagem (não por produto).
- **FR-007**: O catálogo da loja e o admin MUST expor as faixas dentro de cada embalagem; a listagem administrativa de faixas MUST permitir filtrar por embalagem.
- **FR-008**: As faixas existentes MUST ser atribuídas a uma embalagem pela regra do US3, sem perda de registros.
- **FR-009**: A sincronização com o Bling MUST NOT criar, mover ou apagar faixas.
- **FR-010**: O contrato novo MUST estar documentado para o front antes do merge do PR de código.

### Key Entities

- **Faixa de preço**: quantidade mínima (> 1) e preço unitário de uma embalagem; única por (embalagem, quantidade mínima).
- **Embalagem (variação)**: unidade de venda com preço-base e estoque; tem zero ou mais faixas.
- **Item de pedido**: guarda o preço cobrado e a quantidade mínima da faixa aplicada (snapshot).

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: Em 100% dos testes, nenhuma embalagem é cobrada com faixa de outra nem atinge faixa somando outra embalagem.
- **SC-002**: O número de faixas depois da migração é igual ao de antes.
- **SC-003**: Nenhum item é cobrado acima do preço-base da sua embalagem.
- **SC-004**: O front consegue mostrar as faixas por embalagem só com o contrato publicado, sem consultas extras.

## Assumptions

- Entrega em dois PRs por causa do migration gate: migração aditiva (vínculo com a embalagem, backfill e unicidade nova; o vínculo com o produto permanece) e PR de código.
- A loja e o admin (front #73) podem ficar em transição entre os PRs; não há clientes reais.
- Fora de escopo: faixas por categoria ou por cliente, desconto percentual, faixas vindas do Bling e o aviso de faixa acima do preço-base (back #123 / front #81).
- Carrinhos abertos são recalculados a cada leitura; não há preço congelado no carrinho.
