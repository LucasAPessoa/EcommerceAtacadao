# Feature Specification: Portal de admin e gestão de produtos

**Feature Branch**: `spec/007-portal-admin`

**Created**: 2026-10-26

**Status**: Implementada (escopo fechado em 2026-10-26)

> **Atualização 2026-10-28 (spec 008, back #128):** a camada de apresentação fica só com visibilidade e destaque; nome, descrição e categorias vêm do Bling. Preço do site e faixas passam à tabela de preços por variação. Ver `specs/008-anuncios-bling/`.

**Input**: User description: "Substituir o admin atual do front (tela única com CRUD por JSON cru) por um portal com Dashboard, Produtos, Pedidos e Bling. Produtos com busca, filtros, paginação com total, detalhe somente leitura do que vem do Bling, preço do site e faixas, e camada de apresentação do site por produto com override por campo (nome, descrições, categorias) que a sync do Bling nunca sobrescreve, mais visibilidade e destaque. Pedidos com filtros e ações existentes. Dashboard calculado no servidor. Bling com acompanhamento da importação e pendências. Só administradores."

**Issues**: front #32 (painel administrativo independente; esta spec a implementa, com sessão própria em vez de compartilhada). PRs: back #106–#109, front #52, #54 e #60. Relacionadas: spec 003 (catálogo somente leitura), spec 006 (importação do catálogo), constituição v1.1.0 (princípio I, camada de apresentação).

## Clarifications

### Session 2026-10-26

- Q: Como funciona a trava por campo? → A: Override por campo em dados próprios do site; travar = personalizar; destravar descarta a personalização e restaura o valor do Bling na hora. Campos: nome, descrição, descrição complementar e categorias.
- Q: Quando um produto conta como estoque baixo? → A: Estoque disponível somado das variações ativas ≤ limiar configurável por loja, padrão 5.
- Q: Produto oculto fica fora de venda? → A: Não. Some de listagens, busca, categorias e destaques, mas continua comprável pelo endereço direto.
- Q: A moderação de avaliações e perguntas (hoje só no editor por JSON) entra no portal? → A: Sim, como área própria.
- Q: Onde fica o portal? → A: É uma aplicação separada da loja, no mesmo deploy, em `/admin/`, aberta em nova guia. Tem login e sessão próprios e não compartilha interface, estilos nem sessão com a loja.
- Q: Qual o visual do portal? → A: Painel enxuto, com tokens próprios e preparado para temas. A gestão de temas (da loja e do admin) é plano futuro, fora desta spec.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Encontrar e inspecionar produtos (Priority: P1)

O administrador abre a área de produtos e encontra rapidamente qualquer item do catálogo. Pode buscar por nome, código, SKU ou GTIN, filtrar por situação e navegar por páginas sabendo quantos resultados existem. No detalhe vê tudo o que veio do Bling (variações, preços, estoque, imagens, situação), sem poder alterar esses dados.

**Why this priority**: hoje não há como achar um produto no admin sem conhecer seu identificador interno. É a base de todas as outras ações sobre produtos.

**Independent Test**: com um catálogo importado de algumas centenas de produtos, buscar por parte do nome, por SKU e por GTIN, aplicar filtros combinados e conferir que a contagem total e as páginas batem com o catálogo.

**Acceptance Scenarios**:

1. **Given** um catálogo importado, **When** o admin busca por um SKU de variação, **Then** a lista mostra o produto dono daquela variação.
2. **Given** filtros de categoria e "estoque baixo" aplicados, **When** a lista carrega, **Then** só aparecem produtos que atendem aos dois, e o total informado corresponde à quantidade real.
3. **Given** um produto fora de venda (inativo no Bling ou com dados incompletos) ou com variações fora de venda, **When** o admin abre o detalhe, **Then** vê o produto e todas as variações, cada uma com sua situação e o motivo quando houver.
4. **Given** um filtro e uma página escolhidos, **When** o admin recarrega a tela ou compartilha o endereço, **Then** a mesma busca, os filtros e a página são restaurados.

---

### User Story 2 - Personalizar a apresentação do produto na loja (Priority: P1)

O administrador quer que, na loja, um produto apareça com nome, descrição ou categorias diferentes dos cadastrados no Bling. No detalhe do produto, cada um desses campos tem a escolha "usar do Bling" ou "personalizar no site". Ao personalizar, o campo fica travado: novas importações do Bling não mudam o que a loja mostra. Ao voltar para "usar do Bling", a loja passa a mostrar o valor do Bling na hora. O admin sempre vê o valor do Bling ao lado do personalizado.

**Why this priority**: é a principal lacuna de gestão relatada. O catálogo vem do Bling, mas a loja precisa de textos e organização próprios sem perder a sincronização.

**Independent Test**: personalizar o nome e as categorias de um produto, rodar a importação com o nome alterado no Bling, conferir que a loja mantém o nome personalizado; voltar para "usar do Bling" e conferir que a loja mostra o nome atual do Bling.

**Acceptance Scenarios**:

1. **Given** um produto sem personalização, **When** o admin personaliza a descrição e salva, **Then** a loja passa a mostrar a descrição personalizada.
2. **Given** um nome personalizado, **When** a importação traz um nome novo do Bling, **Then** a loja continua mostrando o personalizado, e o admin vê o novo valor do Bling ao lado.
3. **Given** um campo personalizado, **When** o admin escolhe "usar do Bling", **Then** a loja mostra o valor atual do Bling sem esperar uma nova importação.
4. **Given** categorias personalizadas, **When** um cliente navega pela categoria escolhida no site, **Then** o produto aparece nela, e não aparece nas categorias do Bling que deixaram de valer.
5. **Given** a tela de detalhe, **When** o admin procura editar estoque, peso, medidas, SKU ou GTIN, **Then** esses dados aparecem somente para leitura, identificados como vindos do Bling.

---

### User Story 3 - Controlar visibilidade, destaque e preço (Priority: P1)

O administrador oculta produtos da loja ou os coloca em destaque, um a um ou vários de uma vez a partir da lista. No detalhe ajusta o preço do site de cada variação e as faixas de preço por quantidade.

**Why this priority**: são as ações mais frequentes do dia a dia da loja. Preço e faixas já são permitidos pela spec 003, mas hoje exigem JSON digitado à mão.

**Independent Test**: ocultar três produtos de uma vez pela lista, conferir que somem da vitrine e da busca pública; destacar um e conferir que aparece entre os destaques; alterar o preço de uma variação e conferir o novo valor no carrinho.

**Acceptance Scenarios**:

1. **Given** vários produtos selecionados na lista, **When** o admin escolhe "ocultar da loja", **Then** todos deixam de aparecer no catálogo público, e a lista do admin mostra a nova situação.
2. **Given** um produto oculto e à venda, **When** um cliente acessa o endereço direto dele, **Then** o produto é exibido e pode ser comprado normalmente (ex.: venda combinada por WhatsApp).
3. **Given** uma variação, **When** o admin altera o preço do site para um valor maior que zero, **Then** o novo preço vale nas novas compras, e o servidor continua sendo o único a calcular o total.
4. **Given** faixas de preço por quantidade, **When** o admin cria, altera ou remove uma faixa, **Then** a vitrine e o checkout passam a usá-la.
5. **Given** um preço inválido (zero, negativo ou não numérico), **When** o admin tenta salvar, **Then** o campo mostra o erro e nada é gravado.

---

### User Story 4 - Operar pedidos (Priority: P2)

O administrador lista pedidos filtrando por situação, período e cliente, abre o detalhe (itens, valores, pagamento, entrega, histórico de situação) e executa as ações já existentes: cancelar, reconciliar pagamento e solicitar reembolso. Também acompanha a fila de pagamentos aguardando reconciliação.

**Why this priority**: hoje o admin só vê os oito pedidos mais recentes, sem detalhe nem ações, embora as ações já existam no servidor.

**Independent Test**: com pedidos em várias situações e datas, filtrar por "pago" num período, abrir um pedido, cancelar um pedido aguardando pagamento e conferir a nova situação e o histórico.

**Acceptance Scenarios**:

1. **Given** pedidos em várias situações, **When** o admin filtra por situação e período, **Then** só aparecem os pedidos correspondentes, com o total de resultados.
2. **Given** um pedido aguardando pagamento, **When** o admin o cancela e confirma, **Then** a situação muda para cancelado e o histórico registra quem cancelou.
3. **Given** uma ação não permitida para a situação atual do pedido, **When** a tela mostra o pedido, **Then** a ação não é oferecida, e uma tentativa direta é recusada pelo servidor com mensagem clara.
4. **Given** pagamentos aguardando reconciliação, **When** o admin abre a fila, **Then** vê cada pedido pendente e pode reconciliá-lo.

---

### User Story 5 - Visão geral no dashboard (Priority: P2)

Ao entrar no portal, o administrador vê um resumo do período escolhido: faturamento, quantidade de pedidos por situação, ticket médio, quantidade de produtos com estoque baixo e de pendências do Bling, com atalhos para as listas correspondentes.

**Why this priority**: hoje o resumo é somado no navegador a partir de todos os pedidos, o que é lento e fica incorreto conforme o volume cresce.

**Independent Test**: com pedidos conhecidos em datas conhecidas, escolher um período e conferir faturamento, contagens e ticket médio contra o cálculo manual.

**Acceptance Scenarios**:

1. **Given** pedidos pagos e não pagos no período, **When** o admin abre o dashboard, **Then** o faturamento considera apenas pedidos pagos (pagos, em processamento, enviados ou entregues), e o ticket médio é o faturamento dividido pela quantidade desses pedidos.
2. **Given** um período sem pedidos, **When** o dashboard carrega, **Then** mostra zeros, e não erros.
3. **Given** o indicador de estoque baixo, **When** o admin o seleciona, **Then** vai para a lista de produtos já filtrada por estoque baixo.

---

### User Story 6 - Acompanhar o Bling e suas pendências (Priority: P3)

Dentro do portal, o administrador vê a situação da conexão com o Bling, inicia a importação do catálogo, acompanha a execução em andamento até o fim e consulta a lista de pendências por produto e variação, com o motivo de cada uma (ex.: variação fora de venda por preço zero, produto sem peso ou medidas).

**Why this priority**: conexão e importação já funcionam (specs 001 e 006). Falta trazê-las ao portal e explicar por que um produto não está à venda.

**Independent Test**: iniciar a importação pelo portal e ver a execução avançar até concluir sem recarregar a página; abrir as pendências e encontrar uma variação com preço zero, ajustar o preço e vê-la sair da lista após a próxima importação.

**Acceptance Scenarios**:

1. **Given** uma importação em andamento, **When** o admin está na tela do Bling, **Then** o progresso se atualiza sozinho até a execução terminar.
2. **Given** variações fora de venda por motivo conhecido, **When** o admin abre as pendências, **Then** vê produto, variação e motivo, com acesso direto ao detalhe do produto.
3. **Given** uma importação já em andamento, **When** o admin tenta iniciar outra, **Then** recebe aviso claro de que já existe uma em execução.

---

### User Story 7 - Moderar avaliações e perguntas (P2)

O administrador vê as avaliações aguardando aprovação e as perguntas sem resposta de todos os produtos, numa fila única por tipo. Pode aprovar ou ocultar avaliações, responder ou editar a resposta de perguntas e excluir as impróprias.

**Why this priority**: novas avaliações nascem não aprovadas e só aparecem na loja depois da moderação. Hoje isso só é possível pelo editor por JSON, que esta spec remove.

**Independent Test**: um cliente cria uma avaliação e uma pergunta; o admin as encontra nas filas, aprova a avaliação e responde a pergunta; ambas passam a aparecer na página do produto.

**Acceptance Scenarios**:

1. **Given** avaliações novas, **When** o admin abre a fila "aguardando aprovação", **Then** vê nota, comentário, produto, autor e data, com o total de pendentes.
2. **Given** uma avaliação pendente, **When** o admin a aprova, **Then** ela aparece na página do produto e sai da fila.
3. **Given** uma pergunta sem resposta, **When** o admin responde e salva, **Then** a resposta aparece na página do produto e a pergunta sai da fila de não respondidas.
4. **Given** uma avaliação ou pergunta imprópria, **When** o admin a exclui e confirma, **Then** ela some da loja e das filas.

---

### User Story 8 - Acessar o portal separado da loja (P1)

O administrador entra no portal por um endereço próprio (`/admin/`), que o site também oferece como link em nova guia para quem é admin. O portal tem tela de login própria e sessão independente da conta usada na loja. Fechar a sessão em um não afeta o outro.

**Why this priority**: é a base de acesso de todas as outras histórias e atende à exigência de isolar o admin do site.

**Independent Test**: logado como cliente comum na loja, abrir `/admin/` e ver a tela de login do portal; entrar como admin no portal, sair da loja e conferir que o portal continua autenticado; conferir que a loja não carrega código nem estilos do portal.

**Acceptance Scenarios**:

1. **Given** um admin logado na loja, **When** clica em "Painel admin", **Then** o portal abre em nova guia, na tela de login do portal (sessões independentes).
2. **Given** um usuário sem papel de admin, **When** entra com as credenciais dele no portal, **Then** o acesso é recusado com mensagem clara e nenhuma sessão do portal fica aberta.
3. **Given** um admin autenticado no portal, **When** sai da loja na outra guia, **Then** o portal continua autenticado, e vice-versa.
4. **Given** um visitante da loja, **When** navega pelo site, **Then** nenhum código ou estilo do portal é baixado.

---

### Edge Cases

- Produto personalizado que é inativado ou some do Bling: sai de venda normalmente, conforme a spec 006. A personalização é mantida e volta a valer se o produto voltar.
- Categoria escolhida numa personalização que é desativada pelo Bling: deixa de ser exibida, o produto continua visível pelas demais categorias, e o admin é avisado no detalhe.
- Personalização com o mesmo texto do Bling: é aceita e continua travada, para que futuras mudanças no Bling não a alterem.
- Personalização com texto vazio: é recusada. Para usar o valor do Bling, o admin escolhe "usar do Bling".
- Produto oculto que está no carrinho de um cliente: a compra segue normalmente. Ocultar não tira o produto de venda; para isso vale a situação no Bling (spec 006).
- Dois administradores editando o mesmo produto: vale a última gravação.
- Busca sem resultados ou filtros incompatíveis: a lista mostra estado vazio com opção de limpar filtros.
- Usuário que perde o papel de admin com a tela aberta: a próxima ação é recusada, e ele é levado para fora do portal.
- Sessão ainda carregando ao abrir o portal: a tela aguarda, sem mostrar "acesso restrito" por engano.
- Retorno da autorização do Bling: o endereço de retorno usado hoje (`/admin/integracoes/bling?...`) continua funcionando dentro do portal, preservando o resultado informado na URL.
- Avaliação editada pelo cliente depois de aprovada: não existe hoje (só admin edita); fica como está.

## Requirements *(mandatory)*

### Functional Requirements

**Acesso**

- **FR-001**: Toda consulta e alteração do portal MUST exigir usuário autenticado com papel de administrador. Outros usuários recebem recusa por falta de permissão antes de qualquer gravação.
- **FR-002**: O portal MUST ser uma aplicação separada da loja, servida em `/admin/` no mesmo domínio, com navegação entre Dashboard, Produtos, Pedidos, Moderação e Bling. Ele substitui o editor genérico por JSON do admin atual. A loja MUST NOT carregar código ou estilos do portal, e o portal MUST NOT depender da interface ou dos estilos da loja.
- **FR-002a**: O portal MUST ter login e sessão próprios, independentes da sessão da loja. Login de quem não é admin é recusado sem abrir sessão. Recusa por falta de permissão durante o uso encerra a sessão do portal e volta ao login.
- **FR-002b**: A loja MUST oferecer, só para usuários admin, um link "Painel admin" que abre `/admin/` em nova guia.
- **FR-002c**: O portal MUST exibir no menu as seções previstas e ainda sem tela (Clientes, Entrega, Despacho e Configurações), cada uma com rota própria mostrando "em breve". Elas são entregues fora desta spec: Entrega na front #27, Despacho na front #26, Clientes e Configurações em specs futuras.

**Produtos — consulta**

- **FR-003**: A lista de produtos MUST permitir busca textual por nome (do Bling ou personalizado), código do produto, SKU e GTIN das variações.
- **FR-004**: A lista MUST permitir filtrar por categoria, situação de venda (à venda / fora de venda, conforme a importação do Bling), visibilidade na loja, destaque, estoque baixo, existência de pendência do Bling e existência de campos personalizados, combinando os filtros.
- **FR-005**: A lista MUST permitir ordenar por nome, preço, estoque e data de atualização, e MUST paginar informando o total de resultados.
- **FR-006**: O detalhe do produto MUST mostrar os dados vindos do Bling (incluindo variações e itens inativos, estoque, imagens, peso e medidas) como somente leitura, identificados como "vem do Bling", e o motivo de cada variação fora de venda quando conhecido.
- **FR-007**: Busca, filtros, ordenação e página MUST ficar refletidos no endereço da tela, para recarregar e compartilhar.

**Produtos — camada de apresentação**

- **FR-008**: Para cada produto, o admin MUST poder personalizar individualmente nome, descrição, descrição complementar e categorias exibidas. Cada campo fica em "usar do Bling" ou "personalizado".
- **FR-009**: Um campo personalizado MUST prevalecer sobre o valor do Bling em toda a loja (vitrine, busca, detalhe, categorias), e a importação do Bling MUST NOT alterá-lo nem removê-lo.
- **FR-010**: Voltar um campo para "usar do Bling" MUST descartar a personalização e fazer a loja exibir o valor atual do Bling imediatamente.
- **FR-011**: O detalhe MUST mostrar, para cada campo personalizável, o valor atual do Bling ao lado do valor personalizado.
- **FR-012**: As categorias personalizadas MUST ser escolhidas entre as categorias existentes no site e, quando personalizadas, substituem por completo as categorias do Bling daquele produto.
- **FR-013**: O admin MUST poder marcar um produto como oculto ou visível na loja e como destacado ou não, individualmente ou em lote a partir da lista.
- **FR-014**: Produto oculto MUST NOT aparecer em listagens, buscas, categorias ou destaques públicos, mas continua acessível e comprável pelo endereço direto, desde que esteja à venda pelas regras da spec 006.
- **FR-015**: Estoque, peso, medidas, SKU, GTIN e situação no Bling MUST NOT ser editáveis pelo portal. Checkout e frete continuam usando os dados do Bling.

**Produtos — preço**

- **FR-016**: O admin MUST poder alterar o preço do site de cada variação e criar, alterar e remover faixas de preço por quantidade, com validação por campo (valor maior que zero, quantidade mínima inteira positiva, sem faixas duplicadas).

**Pedidos**

- **FR-017**: A lista de pedidos MUST permitir filtrar por situação, período de criação e cliente (nome ou e-mail), com paginação e total de resultados.
- **FR-018**: O detalhe do pedido MUST mostrar itens, valores, pagamento, endereço de entrega e histórico de situação.
- **FR-019**: O portal MUST oferecer, com confirmação, as ações já existentes de cancelar, reconciliar pagamento e solicitar reembolso, apenas quando permitidas pela situação do pedido. O servidor continua validando cada ação.
- **FR-020**: O portal MUST exibir a fila de pagamentos aguardando reconciliação.

**Dashboard**

- **FR-021**: O sistema MUST fornecer, para um período escolhido, faturamento e ticket médio de pedidos pagos (pagos, em processamento, enviados ou entregues), quantidade de pedidos por situação, quantidade de produtos com estoque baixo e quantidade de produtos com pendência do Bling, tudo calculado no servidor.
- **FR-022**: O período MUST oferecer atalhos (hoje, últimos 7 dias, últimos 30 dias, mês atual) e um intervalo personalizado, considerando o fuso horário de Brasília (America/Sao_Paulo).
- **FR-023**: Um produto à venda MUST contar como "estoque baixo" quando o estoque disponível somado das variações ativas for menor ou igual ao limiar configurado para a loja na configuração do cliente (spec 002), com padrão de 5 unidades.

**Bling**

- **FR-024**: O portal MUST mostrar a situação da conexão com o Bling, permitir conectar, desconectar e iniciar a importação, e atualizar sozinho o andamento de uma importação em execução até ela terminar.
- **FR-025**: O sistema MUST listar as pendências por produto e variação, com o motivo de estar fora de venda (ex.: preço ausente ou zero, peso ou medidas ausentes), com acesso ao detalhe do produto.

**Qualidade da interface**

- **FR-026**: Todas as telas do portal MUST ter estados de carregamento, vazio e erro, mostrar erros de validação junto ao campo e confirmar ações destrutivas ou em lote.
- **FR-027**: O visual do portal MUST ser um painel enxuto, com estilos próprios baseados em variáveis de tema, sem cores fixas nos componentes. Nome e cor da loja aparecem só como acento. A gestão de temas fica fora desta spec.

**Moderação**

- **FR-028**: O portal MUST listar, de todos os produtos, as avaliações por situação (aguardando aprovação, aprovadas, todas) e as perguntas por situação (sem resposta, respondidas, todas), com produto, autor, data, paginação e total.
- **FR-029**: O admin MUST poder aprovar e ocultar avaliações, responder e editar a resposta de perguntas e excluir avaliações e perguntas (com confirmação), e a loja MUST refletir a mudança imediatamente.

### Key Entities

- **Apresentação do produto no site**: dados próprios do site para um produto, separados dos dados do Bling. Guarda os campos personalizados (nome, descrição, descrição complementar), se as categorias estão personalizadas, a visibilidade na loja e o destaque. Um campo sem valor personalizado significa "usar do Bling".
- **Categorias do produto no site**: vínculo entre um produto e as categorias do site escolhidas pelo admin. Só vale quando as categorias do produto estão personalizadas.
- **Produto, variação, categoria (Bling)**: continuam como definidos nas specs 003 e 006. São somente leitura no portal, exceto o preço do site.
- **Faixa de preço**: quantidade mínima e preço unitário por produto, como hoje.
- **Pedido e histórico de situação**: como hoje. O portal só consulta e dispara as ações existentes.
- **Pendência do Bling**: um produto ou variação fora de venda, com o motivo identificado na importação.
- **Resumo do período**: indicadores agregados do dashboard para um intervalo de datas.
- **Avaliação e pergunta de produto**: como hoje (spec 003). Avaliações nascem não aprovadas; perguntas têm resposta opcional do vendedor.
- **Sessão do portal**: sessão de administrador própria do portal, independente da sessão da loja, com a mesma conta de usuário.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: O admin encontra qualquer produto por nome, SKU ou GTIN em menos de 10 segundos, com um catálogo de até 5.000 produtos.
- **SC-002**: Personalizar um campo de um produto, ou desfazer a personalização, leva no máximo 3 interações a partir do detalhe, e o efeito aparece na loja na hora.
- **SC-003**: Em 100% das importações, nenhum campo personalizado é alterado, e campos não personalizados refletem o Bling.
- **SC-004**: Ocultar ou destacar 20 produtos de uma vez leva menos de 30 segundos.
- **SC-005**: Os indicadores do dashboard batem com o cálculo manual sobre os mesmos pedidos, sem diferença de centavos.
- **SC-006**: Nenhuma tarefa do portal exige digitar identificadores internos ou estruturas de dados à mão.
- **SC-007**: 100% das consultas e alterações do portal feitas por quem não é administrador são recusadas.
- **SC-008**: A loja não baixa nenhum recurso do portal (verificável no build: nenhum arquivo do portal é referenciado pela entrada da loja).
- **SC-009**: Uma avaliação nova pode ser aprovada em no máximo 2 interações a partir da fila.

## Assumptions

- O catálogo de cada loja tem até alguns milhares de produtos. Volumes muito maiores ficam fora do alvo desta spec.
- Só existe o papel "administrador" com acesso total ao portal. Papéis diferenciados (ex.: operador só de pedidos) ficam para depois.
- A gestão de clientes (lista, detalhe, papéis, bloqueio) fica fora desta spec. A lista simples de usuários do admin atual deixa de existir junto com ele e volta numa spec própria de clientes. No portal, Clientes, Entrega (front #27), Despacho (front #26) e Configurações aparecem só como "em breve" (FR-002c).
- Temas selecionáveis (da loja e do portal) são um plano futuro; esta spec só garante estilos baseados em variáveis de tema.
- O site não cria categorias próprias. As personalizações usam as categorias existentes, vindas do Bling.
- Imagens não são personalizáveis nesta spec.
- Remessa, etiqueta, nota fiscal e mudança manual de situação de pedido continuam fora de escopo. O portal só usa as ações existentes.
- Não há histórico ou auditoria de alterações da apresentação do produto além da data da última alteração. Vale a última gravação.
- "Oculto" só tira o produto da vitrine; não o tira de venda. Tirar de venda continua sendo feito pelo Bling.
- Valores em dinheiro seguem as invariantes da constituição (princípio II), e os períodos usam o fuso de Brasília. Hoje não existe fuso configurável por loja; se surgir um cliente fora desse fuso, ele entra na configuração do cliente (spec 002).
