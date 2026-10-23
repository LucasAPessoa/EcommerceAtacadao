# Feature Specification: Catálogo somente leitura (dados vêm do Bling)

**Feature Branch**: `spec/003-catalogo-somente-leitura`

**Created**: 2026-10-21

**Status**: Draft

**Input**: User description: "O site não pode alterar produtos; tudo vem do Bling. Exceção: preço do site. Remover as rotas de escrita das entidades vindas do Bling, mantendo leitura e moderação de perguntas/avaliações."

**Issues**: back #53. Relacionadas: #54 (importação Bling → catálogo), #56 (origem do preço por produto). Front: issue a abrir para o admin de catálogo (contrato muda).

## Clarifications

### Session 2026-10-21

- Q: Quando cortar a escrita, se o sincronismo (#54) ainda não existe? → A: Já. Até o #54, o catálogo entra pelo seed/script; só o preço continua editável pelo site.
- Q: Faixas de preço por quantidade ficam editáveis? → A: Sim. O site tem preços próprios e por faixa de quantidade, independentemente do Bling.
- Q: Anúncios (listings, imagens e atributos de anúncio) ficam editáveis? → A: Não; são tratados como vindos do Bling e bloqueados.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Catálogo protegido contra edição pelo site (Priority: P1)

O lojista mantém produtos, categorias, variações, imagens e anúncios no Bling. Ninguém, nem o administrador, consegue criar, alterar ou apagar esses dados pelo site; o site apenas os exibe.

**Why this priority**: edição no site seria sobrescrita pelo sincronismo ou deixaria o site divergente do Bling (constituição, princípio I).

**Independent Test**: como administrador, tentar criar, alterar e apagar cada tipo de dado do catálogo vindo do Bling e verificar que todas as tentativas são recusadas e nada muda; a consulta continua igual.

**Acceptance Scenarios**:

1. **Given** um administrador autenticado, **When** tenta criar, alterar ou apagar categoria, produto, variação, imagem de produto, anúncio, imagem de anúncio ou atributo de anúncio, **Then** a operação é recusada como não permitida e o dado não muda.
2. **Given** qualquer visitante, **When** consulta listas e detalhes do catálogo, **Then** recebe os mesmos dados de antes da mudança.
3. **Given** a documentação da API, **When** é consultada, **Then** não lista operações de escrita para esses dados.

---

### User Story 2 - Administrador ajusta o preço do site (Priority: P1)

O administrador continua definindo o preço de venda de cada variação no site e as faixas de preço por quantidade de cada produto, sem depender do Bling.

**Why this priority**: o preço é a única decisão comercial que o lojista precisa fazer no site.

**Independent Test**: como administrador, alterar o preço de uma variação e criar/alterar/apagar uma faixa de preço; verificar que a vitrine e o checkout usam os novos valores e que mais nenhum campo da variação pode ser alterado.

**Acceptance Scenarios**:

1. **Given** um administrador, **When** altera o preço de uma variação, **Then** o novo preço passa a valer na vitrine e no checkout.
2. **Given** um administrador, **When** tenta alterar, junto com o preço, qualquer outro campo da variação (nome, SKU, estoque, medidas, ativo), **Then** a operação é recusada por dados inválidos e nada muda.
3. **Given** um administrador, **When** cria, altera ou apaga uma faixa de preço por quantidade, **Then** a operação é aceita com as mesmas regras de hoje (quantidade mínima maior que 1, preço não negativo, uma faixa por quantidade mínima por produto).
4. **Given** um usuário que não é administrador, **When** tenta alterar preço ou faixa, **Then** o acesso é negado.

---

### User Story 3 - Perguntas e avaliações seguem moderáveis (Priority: P2)

Clientes continuam enviando perguntas e avaliações, e o administrador continua respondendo, aprovando e removendo.

**Why this priority**: não são dados do Bling; a mudança não pode quebrá-los.

**Independent Test**: fluxo atual de pergunta/avaliação (criar como cliente, responder/aprovar/apagar como admin) continua funcionando.

**Acceptance Scenarios**:

1. **Given** um cliente, **When** envia pergunta ou avaliação, **Then** funciona como hoje.
2. **Given** um administrador, **When** responde, aprova ou apaga pergunta/avaliação, **Then** funciona como hoje.

### Edge Cases

- Requisição de escrita sem autenticação num recurso bloqueado: recusada como não permitida (a operação não existe), sem revelar mais nada.
- Alteração de preço com corpo vazio ou só com campos proibidos: recusada por dados inválidos.
- Preço negativo: recusado como hoje.
- Variação apagada (inativa logicamente): alteração de preço segue a regra atual de "não encontrado".
- O seed e os scripts internos continuam gravando o catálogo diretamente no banco (não usam a API).

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: O sistema MUST recusar criação, alteração e exclusão via API de categorias, produtos, variações, imagens de produto, anúncios, imagens de anúncio e atributos de anúncio, para qualquer usuário, como operação não permitida.
- **FR-002**: Consultas (lista e detalhe) desses dados MUST continuar com o mesmo comportamento e formato de resposta.
- **FR-003**: O administrador MUST poder alterar somente o preço de venda de uma variação; qualquer outro campo enviado na alteração MUST ser recusado por dados inválidos.
- **FR-004**: O administrador MUST poder criar, alterar e apagar faixas de preço por quantidade, com as regras atuais.
- **FR-005**: Perguntas e avaliações MUST manter criação pelo cliente e moderação pelo administrador como hoje.
- **FR-006**: A documentação da API MUST refletir só as operações disponíveis.
- **FR-007**: Testes de API MUST cobrir a recusa de cada operação bloqueada (inclusive como administrador), a alteração de preço permitida e proibida, e as faixas de preço.
- **FR-008**: O front MUST ser avisado da mudança de contrato antes do merge (issue no repositório do front).

### Key Entities

- **Dados do catálogo vindos do Bling** (somente leitura): categoria, produto, variação (exceto preço), imagem de produto, anúncio, imagem de anúncio, atributo de anúncio.
- **Preço do site** (editável): preço de venda da variação e faixas de preço por quantidade do produto.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: 100% das operações de escrita dos 7 tipos de dado bloqueados são recusadas nos testes, inclusive para administrador.
- **SC-002**: O administrador consegue mudar um preço e uma faixa de preço e ver o valor novo na vitrine na primeira tentativa.
- **SC-003**: Nenhum teste existente de consulta do catálogo, carrinho, checkout, perguntas ou avaliações regride.

## Assumptions

- "Preço" = preço de venda da variação; a escolha entre preço do Bling e preço do site (origem) fica com #56, que poderá alterar este contrato.
- Até o #54, produtos novos entram pelo seed/scripts internos, aceitos pelo usuário.
- Estoque, medidas e dados fiscais da variação vêm do Bling e não são editáveis no site.
- O painel administrativo do front passará a exibir o catálogo só para consulta (exceto preço/faixas), em issue própria do front.
