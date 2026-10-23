# Feature Specification: CI/CD para N clientes

**Feature Branch**: `spec/004-cicd-por-cliente`

**Created**: 2026-10-23

**Status**: Draft

**Input**: User description: "Hoje Migrate production, Migration gate e Deploy smoke pressupõem uma única produção. Um environment do GitHub por cliente; Migrate production por cliente; gate exige todos os clientes na revisão atual; smoke por domínio de cada cliente."

**Issues**: back #57. Depende de #51 (configuração por cliente, entregue). Consumidor: #65 (provisionamento de cliente novo).

## Clarifications

### Session 2026-10-23

- Q: Id do primeiro cliente? → A: `atacadao-da-china` (AtacadaoDaChina).
- Q: O deploy atual (`ecommerce-atacadao`, banco com seed) vira o primeiro cliente? → A: Não. Fica como **demo** (dados fictícios); o AtacadaoDaChina terá deploy e banco próprios, provisionados pela #65.
- Q: Aprovação da migração? → A: Um environment do GitHub por cliente, com o próprio `DATABASE_URL` e aprovação do usuário em cada um.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Migrar o banco de cada cliente com segurança (Priority: P1)

O operador dispara a migração para um cliente ou para todos; cada cliente pede aprovação separada, usa só a própria credencial de banco e registra a revisão aplicada.

**Independent Test**: com dois ambientes no registro (demo e um de teste), disparar "todos" e verificar um job e uma aprovação por ambiente, cada um com seu registro de revisão.

**Acceptance Scenarios**:

1. **Given** o registro com demo e AtacadaoDaChina ativos, **When** o operador dispara a migração para "todos", **Then** cada um roda em job próprio, com aprovação própria, e registra a revisão aplicada.
2. **Given** a migração de um cliente falha, **When** as outras rodam, **Then** só o cliente com falha fica sem registro novo e a falha é identificada pelo nome.
3. **Given** um disparo a partir de branch diferente da main, **When** é executado, **Then** nenhum banco é migrado.

### User Story 2 - Código só chega quando todos os bancos estão prontos (Priority: P1)

Um PR de código só pode ser mergeado se todos os clientes ativos já estão na revisão de migração exigida pelo código.

**Acceptance Scenarios**:

1. **Given** dois clientes ativos, um na revisão atual e outro atrasado, **When** um PR de código roda o gate, **Then** o gate falha nomeando o cliente atrasado.
2. **Given** um cliente cadastrado mas ainda não provisionado (inativo), **When** o gate roda, **Then** ele é ignorado.
3. **Given** PR só de migração ou só de docs, **When** o gate roda, **Then** o comportamento atual é mantido.

### User Story 3 - Verificar cada cliente depois do deploy (Priority: P2)

Depois de cada deploy de produção, o smoke de saúde, catálogo e CORS roda para o cliente daquele deploy; no disparo manual, roda para todos, e cada falha aparece individualmente.

**Acceptance Scenarios**:

1. **Given** um deploy de produção de um cliente, **When** termina, **Then** o smoke roda só para ele.
2. **Given** a origem do front do cliente não é aceita pela API, **When** o smoke roda, **Then** falha apontando CORS.
3. **Given** um disparo manual, **When** um cliente falha, **Then** os outros continuam e o resumo lista quem falhou.

### Edge Cases

- Registro com id duplicado, URL sem https ou campos ausentes: os workflows falham antes de qualquer ação, nomeando o problema.
- Cliente sem registro de revisão (primeira vez): o gate orienta o bootstrap (rodar a migração no-op).
- Nomes de environment da Vercel com um ou vários projetos ligados ao repositório (`Production` ou `Production – <projeto>`).

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: O sistema MUST manter um registro versionado de clientes, sem segredos, com id, estado (ativo/inativo), environment do GitHub, URL da API, URL do front e projeto Vercel.
- **FR-002**: A migração MUST rodar por cliente (um ou todos), com environment, credencial e aprovação próprios, só a partir da main, registrando a revisão aplicada por cliente.
- **FR-003**: O gate MUST exigir que todos os clientes ativos estejam na revisão do código; MUST nomear os atrasados; regras atuais para PR de migração/docs MUST ser mantidas.
- **FR-004**: O smoke MUST rodar por cliente (automático pelo deploy, manual para todos), checando saúde, rota com banco e CORS a partir da URL do front; falhas MUST ser individuais.
- **FR-005**: O ambiente demo MUST continuar funcionando com os nomes atuais (environment `production`, registro `database-production`, `ecommerce-atacadao.vercel.app`).
- **FR-006**: O registro MUST ser validado (ids únicos, URLs https, campos obrigatórios) antes de qualquer ação.
- **FR-007**: O passo a passo para adicionar um cliente MUST ficar documentado.

## Success Criteria *(mandatory)*

- **SC-001**: Nenhum código chega a um cliente ativo cujo banco não está migrado (casos de teste do gate com N clientes).
- **SC-002**: Uma falha de smoke ou migração identifica o cliente pelo nome em 100% dos casos.
- **SC-003**: O demo segue com migração, gate e smoke verdes sem nenhuma reconfiguração.

## Assumptions

- AtacadaoDaChina entra no registro como inativo até a #65 criar projeto Vercel, banco Neon e environment do GitHub.
- Só o usuário aprova migrações; nenhum segredo entra no registro.
