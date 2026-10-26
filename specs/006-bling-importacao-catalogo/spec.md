# Feature Specification: Importação do catálogo do Bling

**Feature Branch**: `spec/006-bling-importacao-catalogo`

**Created**: 2026-10-26

**Status**: Draft

**Input**: User description: "Importar o catálogo do Bling para a loja de forma idempotente, usando a conexão já existente. Extrair produtos, variações, categorias, saldo de estoque, preço, imagens, peso e medidas; gravar por identificador do Bling; categorias do Bling viram categorias do site. Desativar o que sumiu ou foi inativado no Bling. Produto sem peso/medidas fica fora de venda. Registrar cada execução. Duas execuções seguidas sem mudança no Bling não alteram nada."

**Issues**: back #54. Relacionadas: #56 (origem do preço por produto), #53/spec 003 (catálogo somente leitura), spec 001 (conexão com o Bling).

## Clarifications

### Session 2026-10-26

- Q: Até a origem do preço por produto (#56) existir, a importação grava o preço do Bling? → A: Só ao criar a variação; depois nunca sobrescreve. Alternar por produto entre preço do Bling e preço do site fica para depois do MVP (#56).
- Q: Como conciliar o saldo do Bling com vendas do site que ainda não chegaram ao Bling? → A: Estoque disponível no site = saldo do Bling − quantidades de pedidos pagos no site ainda não registrados no Bling (funciona como uma reserva). Quando o envio de pedidos ao Bling existir, cada pedido sai da conta ao ser registrado lá.
- Q: Anúncios entram nesta importação? → A: Não; os anúncios do Bling ligados a outros canais de venda ficam fora do MVP. Nome, descrição curta, descrição complementar, marca, unidade e demais dados exibidos vêm do cadastro do produto no Bling; a vitrine usa esses dados e as imagens do produto e das variações. Cada variação usa as imagens próprias que tiver no Bling; sem imagens próprias, herda as do produto.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Catálogo da loja reflete o Bling (Priority: P1)

O lojista cadastra e mantém produtos no Bling. Sem nenhuma ação no site, os produtos ativos e completos aparecem na vitrine com nome, categorias, variações, imagens, peso, medidas e estoque iguais aos do Bling.

**Why this priority**: sem isso a loja não tem catálogo real; hoje ele só entra pelo seed (constituição, princípio I).

**Independent Test**: com o Bling simulado contendo um conjunto de produtos, executar a importação e verificar que a vitrine mostra exatamente os produtos ativos e completos, com os dados de origem.

**Acceptance Scenarios**:

1. **Given** um produto ativo no Bling com peso, medidas e ao menos uma variação, **When** a importação roda, **Then** o produto, suas variações, categorias e imagens passam a existir na loja e o produto fica à venda.
2. **Given** um produto já importado que mudou no Bling (nome, imagem, estoque, medidas), **When** a importação roda, **Then** a loja passa a mostrar os dados novos.
3. **Given** um produto ativo no Bling sem peso ou sem medidas, **When** a importação roda, **Then** ele é gravado, mas fica fora de venda, e a execução registra o motivo.
4. **Given** uma categoria do Bling, **When** a importação roda, **Then** ela existe como categoria do site, e os produtos ficam ligados a ela.

---

### User Story 2 - Produto que sai do Bling sai da vitrine (Priority: P1)

Quando o lojista inativa ou exclui um produto no Bling, ele deixa de ser vendido no site, sem apagar histórico de pedidos.

**Why this priority**: vender produto descontinuado gera pedido impossível de atender.

**Independent Test**: importar, inativar/remover um produto no Bling simulado, importar de novo e verificar que ele some da vitrine e do checkout, enquanto pedidos antigos continuam íntegros.

**Acceptance Scenarios**:

1. **Given** um produto importado, **When** é inativado no Bling e a importação roda, **Then** ele some da vitrine e não pode ser comprado.
2. **Given** um produto importado, **When** deixa de existir no Bling e a importação roda, **Then** é desativado (não apagado), e pedidos que o contêm continuam consultáveis.
3. **Given** um produto desativado, **When** volta a ficar ativo e completo no Bling, **Then** volta à vitrine na próxima importação, sem duplicar.
4. **Given** um produto em carrinho, **When** é desativado, **Then** o checkout recusa o item com mensagem clara.

---

### User Story 3 - Importação segura, repetível e auditável (Priority: P1)

O administrador sabe quando o catálogo foi atualizado pela última vez e se houve erro; repetir a importação nunca duplica nem corrompe dados.

**Why this priority**: a importação roda sem supervisão; precisa ser idempotente e rastreável (constituição, princípio IV).

**Independent Test**: rodar a importação duas vezes sem mudança no Bling e verificar que nada muda na segunda; simular falha do Bling no meio e verificar que nada fica pela metade de forma inconsistente e que o erro fica registrado.

**Acceptance Scenarios**:

1. **Given** duas execuções seguidas sem mudança no Bling, **When** a segunda termina, **Then** nenhum dado do catálogo é alterado e o registro mostra zero alterações.
2. **Given** uma execução, **When** termina, **Then** fica registrado início, fim, situação (sucesso, parcial, falha), contagens (criados, atualizados, desativados, fora de venda, com erro) e os erros por produto.
3. **Given** falha passageira do Bling ou limite de requisições, **When** ocorre durante a importação, **Then** a importação tenta de novo dentro dos limites e, se não conseguir, termina como falha/parcial sem desativar produtos que apenas não puderam ser lidos.
4. **Given** a conexão com o Bling inexistente ou exigindo reconexão, **When** a importação seria executada, **Then** ela não roda, registra o motivo e o catálogo atual fica intacto.
5. **Given** uma importação em andamento, **When** outra é disparada, **Then** a segunda não roda em paralelo.
6. **Given** um administrador, **When** pede uma importação manual, **Then** ela é executada (respeitando o item anterior) e ele vê o resultado no registro.

### Edge Cases

- Produto com dados inválidos (SKU duplicado, campos obrigatórios ausentes): só esse produto falha; o restante da importação segue e o erro fica registrado.
- Imagem removida, reordenada ou trocada no Bling: o conjunto de imagens do produto na loja passa a ser igual ao do Bling.
- Variação removida no Bling de um produto que continua ativo: a variação é desativada; as demais seguem à venda.
- Categoria removida no Bling: deixa de ser exibida quando não tiver produtos ativos; não é apagada se houver vínculo histórico.
- Catálogo grande: a importação respeita o limite de requisições do Bling e conclui sem estourar o tempo máximo de uma execução, retomando na próxima se necessário.
- Estoque negativo ou ausente no Bling: tratado como zero.
- Pedido pago no site que zera o disponível: o produto aparece sem estoque até o saldo do Bling aumentar ou o pedido ser registrado no Bling.
- Faixas de preço por quantidade definidas no site nunca são alteradas pela importação.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: O sistema MUST importar do cadastro de produtos do Bling produtos (nome, descrição curta e complementar, marca, unidade, situação), variações, categorias, saldo total de estoque, imagens, peso e medidas, gravando cada item pelo identificador do Bling (cria se não existe, atualiza se existe).
- **FR-002**: Executar a importação duas vezes sem mudança no Bling MUST NOT alterar nenhum dado do catálogo.
- **FR-003**: Produtos inativos no Bling ou ausentes dele MUST ser desativados no site (fora da vitrine e do checkout), nunca apagados.
- **FR-004**: Produtos ou variações sem peso ou medidas MUST ficar fora de venda até serem completados no Bling.
- **FR-005**: Desativação por ausência MUST acontecer só quando a leitura do catálogo do Bling foi completa; leitura parcial MUST NOT desativar nada.
- **FR-006**: Cada execução MUST ser registrada com início, fim, situação, contagens e erros por item, sem dados sensíveis.
- **FR-007**: A importação MUST rodar periodicamente sem ação humana e MUST poder ser disparada manualmente pelo administrador; nunca duas ao mesmo tempo.
- **FR-008**: A importação MUST NOT rodar sem conexão ativa com o Bling e MUST respeitar o limite de requisições e o retry da conexão existente.
- **FR-009**: Falha em um produto MUST NOT interromper a importação dos demais.
- **FR-010**: Ao criar uma variação, a importação MUST gravar o preço do Bling como preço de venda; depois disso MUST NOT sobrescrever o preço da variação (editável no site). A escolha por produto entre preço do Bling e do site fica para depois do MVP (#56).
- **FR-011**: O estoque disponível no site MUST ser o saldo do Bling menos as quantidades de pedidos pagos no site ainda não registrados no Bling (e menos as reservas ativas do checkout, como hoje); resultado negativo vale zero. Hoje nenhum pedido é registrado no Bling, então todo pedido pago entra na conta até o envio de pedidos existir.
- **FR-012**: Anúncios do Bling vinculados a canais de venda (título, descrição, imagens e atributos de anúncio) MUST NOT ser importados no MVP; título e descrição exibidos vêm do cadastro do produto (FR-001). Imagens: cada variação MUST receber as imagens próprias do Bling; sem imagens próprias, MUST herdar as do produto.
- **FR-013**: O administrador MUST poder consultar as últimas execuções (situação, horário, contagens, erros).
- **FR-014**: Testes de integração MUST cobrir, com o Bling simulado: criação, atualização, idempotência, desativação, produto incompleto, falha parcial sem desativação indevida e bloqueio de execução simultânea.

### Key Entities

- **Item do catálogo vindo do Bling**: categoria, produto, variação (SKU, estoque, peso, medidas), imagem; identificado pelo identificador do Bling.
- **Execução da importação**: início, fim, gatilho (periódico ou manual, e quem disparou), situação, contagens e erros por item.
- **Situação de venda do produto/variação**: à venda, fora de venda (incompleto) ou desativado (inativo/ausente no Bling).

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: Após uma importação bem-sucedida, 100% dos produtos ativos e completos no Bling estão à venda na loja, e nenhum produto inativo ou ausente está.
- **SC-002**: Uma segunda execução sem mudanças no Bling registra zero alterações.
- **SC-003**: Uma mudança feita no Bling aparece na loja em até um ciclo periódico (meta: 1 hora).
- **SC-004**: Uma falha do Bling no meio da importação não desativa nenhum produto e fica visível no registro.
- **SC-005**: Um catálogo de 2.000 produtos é importado por completo em até 4 horas na primeira vez; depois, um ciclo sem mudanças conclui em uma única rodada.

## Assumptions

- A conexão OAuth com o Bling (spec 001) está ativa; a importação usa o mesmo cliente, com limite e retry já implementados.
- Webhooks do Bling ficam fora do MVP; a constituição exige a verificação periódica de qualquer forma.
- Categorias do Bling são gravadas como categorias do site, preservando o nome; hierarquia, se houver, não é exibida no MVP.
- O conjunto de imagens do produto é substituído pelo do Bling a cada mudança (sem identificador estável por imagem).
- O catálogo continua somente leitura pela API (spec 003); só preço e faixas são editáveis no site.
- O painel de consulta das execuções no front é issue própria do front, depois do contrato da API.
