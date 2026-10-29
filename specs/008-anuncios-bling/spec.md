# Feature Specification: Produtos do site como anúncios do Bling (loja API)

**Feature Branch**: `008-anuncios-bling`

**Created**: 2026-10-28

**Status**: Draft

**Input**: User description: "Todos os produtos do site serão anúncios no Bling, para terceirizar e centralizar a gestão de anúncios; a faixa de preços continua sendo gerenciada pelo site. O admin cria o anúncio no Bling, o site importa o anúncio (não mais os produtos) e o admin vai ao site configurar (ou apenas confirmar) os preços por quantidade; se só confirmar, a unidade é o preço do vínculo e as demais faixas ficam vazias. O preço de um produto vem da tabela de faixas, e todos os produtos têm o preço de 1 unidade cadastrado (igual ao preço do vínculo). Quando o admin edita o preço no site, o preço muda no Bling também."

**Issues**: back #128 (esta spec). Substitui back #91, #113 e #123 e front #73 e #81. Relacionadas: back #58 (pedido ao Bling), #59 (estoque), #119 (estoque no carrinho); specs 003, 006 e 007.

## Contexto

Hoje o site importa o **cadastro de produtos** do Bling e grava o preço só na criação; as faixas de preço pertencem ao produto e valem para qualquer variação (bug da back #91). O lojista já gerencia os canais de venda (Mercado Livre, Shopee) como **anúncios** no Bling. Com esta mudança, o site vira mais um canal: uma loja do tipo "API" no Bling, cujos produtos vinculados definem o que aparece no site.

Fatos verificados na conta demo (2026-10-28, spike com app de teste):
- O Bling tem o canal do tipo "API". Para esse tipo, a tela de Anúncios do Bling não oferece criação (só marketplaces); o "anúncio" do site é o **vínculo do produto com a loja do site**, criado na tela de produtos do Bling.
- O vínculo tem preço e preço promocional próprios da loja, e pode ser do produto pai (vale para todas as variações) ou de uma variação específica (preço próprio). Preço 0 = preço da loja não preenchido.
- Nome, descrição, imagens e variações vêm do cadastro do produto no Bling; imagens são links que expiram em 7 dias.
- O Bling não tem faixa de preço por quantidade, por isso as faixas ficam no site.

Neste documento, "anúncio do site" = vínculo de um produto com a loja do site no Bling.

## Clarifications

### Session 2026-10-28

- Q: Produto do Bling sem anúncio na loja do site aparece? → A: Não. Só produtos vinculados à loja do site aparecem.
- Q: Quem define nome, descrição e imagens? → A: O Bling (cadastro do produto, já que o vínculo com a loja API não tem esses campos). A edição desses campos no admin do site deixa de existir.
- Q: Como o Bling representa o anúncio de uma loja API? → A: Vínculo produto–loja (spike de 2026-10-28); a tela de Anúncios do Bling só cria anúncio para marketplaces.
- Q: Vínculo no produto pai ou na variação? → A: Os dois valem: vínculo no pai publica todas as variações com o preço do pai; vínculo na variação publica só ela com preço próprio, e prevalece sobre o do pai.
- Q: Vínculo com preço 0? → A: Preço não preenchido: a linha de 1 unidade usa o preço geral do produto no Bling e o admin vê um aviso; ao confirmar ou editar, o site grava o preço no vínculo.
- Q: Anúncio recém-importado aparece na loja antes de o admin confirmar os preços? → A: Depende de uma configuração do admin: "confirmação automática" ligada (entra na loja com a linha de 1 unidade = preço do vínculo) ou desligada (fica "aguardando preços" até o admin confirmar).
- Q: Preço do anúncio mudou no Bling depois da importação? → A: O site acompanha: a sincronização atualiza a linha de 1 unidade. A edição no site também vai para o Bling, então os dois lados ficam iguais.
- Q: Faixas por quantidade podem vir do Bling (lista de preços, campos customizados)? → A: Não. Ficam no site, uma tabela por variação.
- Q: O que acontece com as faixas atuais? → A: São removidas (3 faixas do seed, ligadas ao produto).

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Admin publica um produto no site criando o anúncio no Bling (Priority: P1)

O admin, no cadastro do produto no Bling, vincula o produto (ou variações dele) à loja do site e preenche o preço da loja. Na próxima sincronização, o anúncio aparece no admin do site. Com a confirmação automática ligada, ele já entra na loja com a linha de 1 unidade igual ao preço do vínculo; desligada, fica "aguardando preços".

**Why this priority**: É a nova porta de entrada de todo produto do site; sem ela a loja fica vazia.

**Independent Test**: Vincular um produto à loja do site no Bling (ou no Bling simulado), rodar a sincronização e conferir o produto no admin e, conforme a configuração, na loja.

**Acceptance Scenarios**:

1. **Given** confirmação automática ligada, **When** um produto vinculado é importado, **Then** o produto aparece na loja e cada variação publicada tem a linha de 1 unidade igual ao preço do vínculo, sem outras faixas.
2. **Given** confirmação automática desligada, **When** um produto vinculado é importado, **Then** o produto aparece no admin como "aguardando preços" e não aparece na loja.
3. **Given** um produto do Bling sem vínculo com a loja do site, **When** a sincronização roda, **Then** ele não aparece no site.
6. **Given** um produto com variações vinculado só no pai (R$ 100) e uma variação com vínculo próprio (R$ 200), **Then** a variação com vínculo próprio entra a R$ 200 e as demais a R$ 100.
4. **Given** o vínculo removido no Bling ou o produto inativado, **When** a sincronização roda, **Then** o produto sai da loja; as faixas configuradas ficam guardadas e voltam se o vínculo for recriado.
5. **Given** um produto vinculado só a outras lojas (Mercado Livre, Shopee), **Then** ele é ignorado.

---

### User Story 2 - Admin configura ou confirma a tabela de preços por variação (Priority: P1)

No admin do site, o admin abre o produto importado e, para cada variação, vê a tabela de preços: a linha de 1 unidade (preço do vínculo) e as faixas por quantidade. Ele pode só confirmar ou acrescentar faixas e então confirmar.

**Why this priority**: Corrige a cobrança errada da back #91 e é o que libera o produto na loja quando a confirmação automática está desligada.

**Independent Test**: Num produto "aguardando preços", acrescentar faixas a uma variação, confirmar e conferir loja e carrinho.

**Acceptance Scenarios**:

1. **Given** um produto aguardando preços, **When** o admin confirma sem mexer, **Then** cada variação fica só com a linha de 1 unidade (preço do vínculo) e o produto entra na loja.
2. **Given** a variação Pacote 5 kg (R$ 27,90), **When** o admin acrescenta "a partir de 10 un. R$ 25,90" e confirma, **Then** a loja mostra essa faixa só no Pacote 5 kg.
3. **Given** uma faixa com preço igual ou maior que a linha de 1 unidade, **When** o admin tenta salvar, **Then** é recusada com mensagem em português.
4. **Given** duas faixas com a mesma quantidade mínima na mesma variação, **Then** a segunda é recusada; em outra variação é aceita.

---

### User Story 3 - Cliente paga a faixa certa da variação (Priority: P1)

O preço de cada item no carrinho e no pedido vem da tabela da própria variação, pela quantidade daquela variação.

**Why this priority**: Fecha o prejuízo atual (10 sacas de 25 kg saindo a R$ 25,90).

**Independent Test**: Com uma faixa só no Pacote 5 kg, comprar 10 sacas (preço cheio), 10 pacotes (faixa) e 5 + 5 (sem faixa).

**Acceptance Scenarios**:

1. **Given** a Saca 25 kg só com a linha de 1 unidade (R$ 119,90), **When** o cliente leva 10 sacas, **Then** paga R$ 119,90 cada.
2. **Given** o Pacote 5 kg com "≥ 10 un. R$ 25,90", **When** o cliente leva 10 pacotes, **Then** paga R$ 25,90 e o pedido registra a faixa aplicada.
3. **Given** 5 pacotes e 5 sacas, **Then** nenhuma faixa se aplica.
4. **Given** um pedido criado, **When** a tabela muda depois, **Then** o pedido mantém o preço registrado.

---

### User Story 4 - Preço de 1 unidade sincronizado nos dois sentidos (Priority: P2)

Quando o admin edita a linha de 1 unidade no site, o preço do vínculo com a loja do site muda no Bling. Quando esse preço muda no Bling, a próxima sincronização atualiza a linha de 1 unidade no site.

**Why this priority**: Mantém um preço só nos dois sistemas; depende de US1 e US2.

**Independent Test**: Editar o preço no site e conferir o vínculo no Bling (simulado); mudar no Bling e conferir o site após a sincronização.

**Acceptance Scenarios**:

1. **Given** um produto ativo, **When** o admin muda a linha de 1 unidade de uma variação, **Then** o vínculo daquela variação no Bling passa a ter o novo preço (se ela só herdava o vínculo do pai, um vínculo próprio é criado para ela) e o site mostra o novo preço.
2. **Given** o Bling recusa ou está fora do ar, **When** o admin salva o preço, **Then** o site não muda o preço, mostra o motivo e permite tentar de novo.
3. **Given** o preço do vínculo mudou no Bling, **When** a sincronização roda, **Then** a linha de 1 unidade passa a ser o novo preço.
4. **Given** a nova linha de 1 unidade ficou igual ou abaixo de alguma faixa, **Then** a mudança é aceita, nenhuma faixa muda, o cliente paga o menor valor e o admin vê um aviso (lista, detalhe, dashboard e pendências).

---

### User Story 5 - Admin acompanha os anúncios importados (Priority: P2)

O admin vê no site a lista de produtos importados com o estado de cada um (aguardando preços, ativo, fora da loja do site, com aviso de faixa ou de preço não preenchido no Bling) e a configuração de confirmação automática.

**Why this priority**: Dá controle do novo fluxo; reaproveita a lista de produtos existente.

**Independent Test**: Com anúncios em estados diferentes, filtrar a lista por estado e alternar a confirmação automática.

**Acceptance Scenarios**:

1. **Given** anúncios aguardando preços, **Then** a lista mostra o estado e permite filtrar por ele; o dashboard mostra quantos estão aguardando.
2. **Given** o admin desliga a confirmação automática, **When** um novo anúncio chega, **Then** ele fica aguardando preços; os já ativos não mudam.
3. **Given** o admin abre o produto, **Then** nome, descrição e imagens aparecem como vindos do Bling, sem edição, com indicação de onde alterar.

### Edge Cases

- Vínculo só no produto pai: todas as variações recebem o preço do pai até o admin ajustar uma delas; o ajuste cria um vínculo próprio da variação no Bling.
- Variação removida ou inativada no Bling: sai da loja; a tabela fica guardada.
- Variação nova num produto já vinculado pelo pai: entra com a linha de 1 unidade do anúncio; se a confirmação automática estiver desligada, só essa variação fica aguardando preços.
- Edição simultânea do preço no site e no Bling: vale a última gravada no Bling; o site relê o vínculo antes de escrever e não altera outros campos dele.
- Vínculo com preço 0 (não preenchido): usa o preço geral do produto e mostra aviso; preço geral também 0 → não entra na loja e aparece como pendência.
- Produtos importados pelo fluxo antigo (sem vínculo): saem da loja na primeira sincronização nova. Na demo, a loja fica vazia até o admin vincular os produtos.
- Conexão com o Bling sem permissão de escrita em produtos/vínculos: a edição de preço fica bloqueada no admin com o motivo; a leitura continua.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: Cada deploy MUST ter configurada a loja do site no Bling (canal do tipo "API").
- **FR-002**: A sincronização MUST importar só os produtos vinculados à loja do site (vínculo no pai ou na variação), com nome, descrição, imagens, variações e o preço do vínculo, e MUST NOT importar produtos sem vínculo com ela.
- **FR-003**: Produto ou variação sem vínculo com a loja do site, inativo no Bling, ou vinculado só a outras lojas MUST NOT aparecer. Vínculo da variação MUST prevalecer sobre o do pai.
- **FR-004**: Toda variação visível MUST ter a linha de 1 unidade gravada na tabela de preços, igual ao preço do vínculo (da variação, senão do pai; preço 0 → preço geral do produto, com aviso).
- **FR-005**: O admin MUST poder ligar ou desligar a confirmação automática; desligada, produto ou variação nova MUST ficar "aguardando preços" e fora da loja até ser confirmada.
- **FR-006**: Confirmar sem alterações MUST deixar só a linha de 1 unidade.
- **FR-007**: O admin MUST poder criar, editar e remover faixas por variação (quantidade mínima ≥ 2, preço menor que a linha de 1 unidade, quantidade mínima única por variação), com mensagens em português.
- **FR-008**: O preço de cada item MUST vir da tabela da própria variação, pela quantidade dessa variação: o menor entre a linha de 1 unidade e a faixa elegível de maior quantidade mínima. O pedido MUST registrar o preço e a faixa aplicada.
- **FR-009**: Editar a linha de 1 unidade no site MUST gravar o preço no vínculo da variação com a loja do site no Bling (criando o vínculo da variação se ela só herdava o do pai) antes de valer no site; falha no Bling MUST manter o preço anterior e informar o admin.
- **FR-010**: A sincronização MUST atualizar a linha de 1 unidade quando o preço do vínculo mudar no Bling, sem alterar as faixas.
- **FR-011**: O site MUST avisar o admin (lista, detalhe, dashboard e pendências) quando uma faixa ficar igual ou acima da linha de 1 unidade, sem bloquear nem alterar preços.
- **FR-012**: Nome, descrição e imagens MUST vir do cadastro do produto no Bling; o admin do site MUST NOT editá-los. Visibilidade e destaque continuam no site.
- **FR-013**: A escrita no Bling MUST se limitar ao preço do vínculo com a loja do site (alterar ou criar o vínculo da variação) e MUST NOT alterar o cadastro do produto nem vínculos com outras lojas.
- **FR-014**: As faixas existentes, ligadas ao produto, MUST ser removidas.
- **FR-015**: A loja (produto e carrinho) MUST mostrar a tabela da variação selecionada e a faixa aplicada.

### Key Entities

- **Loja do site no Bling**: canal do tipo "API" cujo identificador é configurado por deploy.
- **Anúncio do site (vínculo)**: ligação de um produto do Bling (pai ou variação) com a loja do site; define o preço da loja. Nome, descrição, imagens e variações vêm do cadastro do produto.
- **Produto do site**: espelho de um produto vinculado; tem estado (aguardando preços, ativo, fora do ar) e, no site, visibilidade e destaque.
- **Variação**: unidade de venda com estoque e a sua tabela de preços.
- **Tabela de preços da variação**: linha de 1 unidade (preço do vínculo) e faixas por quantidade criadas no site; quantidade mínima única por variação.
- **Configuração de confirmação automática**: por loja, ligada ou desligada.
- **Item de pedido**: guarda o preço cobrado e a faixa aplicada.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: 100% dos produtos visíveis na loja têm vínculo com a loja do site e linha de 1 unidade igual ao preço do vínculo (ou ao preço geral, com aviso).
- **SC-002**: Em 100% dos testes, nenhuma variação é cobrada com faixa de outra nem atinge faixa somando outra variação.
- **SC-003**: Um produto vinculado no Bling aparece no admin do site em até 1 ciclo de sincronização (hoje 10 minutos).
- **SC-004**: Uma edição de preço no site aparece no vínculo do Bling na hora; uma edição no Bling aparece no site em até 1 ciclo de sincronização.
- **SC-005**: Com a confirmação automática ligada, o admin publica um produto no site sem abrir o admin do site.

## Assumptions

- O app OAuth do Bling de cada deploy terá permissão de leitura e escrita em produtos e vínculos produto–loja; mudar as permissões exige reconectar o Bling no admin.
- O estoque continua vindo do saldo do Bling (back #59).
- O envio de pedidos ao Bling (back #58) passará a indicar a loja do site; fora desta spec.
- Não há clientes reais: a loja demo pode ficar vazia entre o deploy e a criação dos anúncios.
- Entrega: back PR 1 (spec, docs, models e migração) → `Migrate production` → back PR 2 (código) → front PR. Documentação e implementação vão nos mesmos PRs.
- O formato do vínculo foi confirmado no spike de 2026-10-28 (registrado no plano).
