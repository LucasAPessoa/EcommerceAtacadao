# Feature Specification: Configuração centralizada por cliente

**Feature Branch**: `spec/002-configuracao-cliente`

**Created**: 2026-10-21

**Status**: Draft

**Input**: User description: "Configuração centralizada por cliente (back #51). Cada cliente (tenant) tem deploy, banco e domínio próprios a partir do mesmo repositório; tudo o que varia por cliente deve ser lido de um único objeto de configuração carregado de env por deploy: marca, domínio/URL do front, remetente, postagem, margem e prazo de manuseio, credenciais Bling/Melhor Envio/Mercado Pago e mapeamento de situações do Bling. Segredos nunca em log, repr ou resposta HTTP. Valores obrigatórios ausentes ou inválidos falham na inicialização com mensagem clara. Nenhum código lê dados de cliente fora desse objeto."

**Issues**: back #51. Consumidores desta configuração: #57 (CI/CD por cliente), #54 (sincronismo Bling), #58 (pedidos no Bling), #62/#64 (frete e entrega própria), etiquetas e NF-e.

## Clarifications

### Session 2026-10-21

- Q: Quais credenciais são obrigatórias? → A: Melhor Envio obrigatório; Bling e Mercado Pago opcionais em grupo. Tudo o que depende do Bling continua opcional.
- Q: Margem e prazo de manuseio já se aplicam ao frete? → A: Não; só entram na configuração (padrão zero). Aplicação fica com a issue de frete (#62).
- Q: Remetente e postagem obrigatórios já? → A: Não; opcionais e validados quando preenchidos, até a feature que os consome.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Subir a loja de um novo cliente só com configuração (Priority: P1)

O operador da plataforma cria o deploy de um novo cliente a partir do mesmo repositório e preenche, num único conjunto de variáveis daquele deploy, os dados do cliente: nome da loja, endereço do front, dados do remetente, postagem, margem e prazo de manuseio, credenciais das integrações e o mapeamento de situações do Bling. A loja passa a usar esses dados em todos os pontos (cotação de frete, checkout, retorno da conexão Bling, identificação da API) sem nenhuma alteração de código.

**Why this priority**: o closed beta tem 3 clientes; sem um ponto único de configuração, cada cliente novo exige mudança de código ou deixa dados de outro cliente vazarem.

**Independent Test**: subir a aplicação duas vezes com conjuntos de configuração diferentes (cliente A e cliente B) e verificar que cotação de frete, checkout e identificação da API refletem o cliente de cada execução.

**Acceptance Scenarios**:

1. **Given** um deploy configurado com os dados do cliente A, **When** um consumidor cota frete, **Then** a origem usada é o CEP do remetente do cliente A.
2. **Given** o mesmo código com a configuração do cliente B, **When** a aplicação inicia, **Then** nome da loja, URL do front e remetente exibidos/usados são os do cliente B, sem nenhum resquício do cliente A.
3. **Given** a configuração completa de um cliente, **When** o operador consulta a lista de variáveis esperadas, **Then** encontra num único lugar documentado cada dado do cliente, se é obrigatório e seu formato.

---

### User Story 2 - Falhar cedo quando a configuração está errada (Priority: P1)

Se o operador esquecer um dado obrigatório ou preencher um valor inválido (CEP, CNPJ, e-mail, URL ou mapeamento de situações malformado), a aplicação não sobe e informa exatamente qual dado está faltando ou inválido, em vez de falhar no meio de uma compra.

**Why this priority**: um erro de configuração descoberto no checkout de um consumidor final custa uma venda e a confiança do cliente.

**Independent Test**: iniciar a aplicação removendo, um de cada vez, cada dado obrigatório e trocando cada dado validado por um valor inválido; verificar que a inicialização falha e que a mensagem nomeia o dado.

**Acceptance Scenarios**:

1. **Given** um deploy sem o CEP do remetente, **When** a aplicação inicia, **Then** a inicialização falha com mensagem que nomeia o dado ausente.
2. **Given** um CNPJ com dígito verificador errado ou um CEP com formato inválido, **When** a aplicação inicia, **Then** a inicialização falha com mensagem que nomeia o dado e o motivo.
3. **Given** vários dados ausentes ou inválidos, **When** a aplicação inicia, **Then** a mensagem lista todos de uma vez.
4. **Given** um segredo (credencial) com valor inválido, **When** a inicialização falha, **Then** a mensagem nomeia o dado mas não exibe o valor.

---

### User Story 3 - Segredos do cliente nunca expostos (Priority: P2)

Credenciais do Bling, Melhor Envio e Mercado Pago e chaves de assinatura/criptografia do cliente nunca aparecem em logs, mensagens de erro, representações de depuração ou respostas HTTP.

**Why this priority**: um vazamento compromete a conta de um cliente real nas integrações; a constituição (princípio III) exige isso.

**Independent Test**: carregar uma configuração com segredos de valor conhecido, provocar a impressão/registro da configuração e erros de inicialização, e verificar que nenhum valor de segredo aparece em nenhuma saída.

**Acceptance Scenarios**:

1. **Given** uma configuração com segredos preenchidos, **When** a configuração é impressa, registrada ou serializada para diagnóstico, **Then** cada segredo aparece mascarado.
2. **Given** qualquer endpoint público ou administrativo, **When** é chamado, **Then** nenhuma resposta contém valor de segredo.

---

### Edge Cases

- Dado opcional ausente (ex.: credenciais de uma integração ainda não contratada): a aplicação sobe e a funcionalidade dependente responde "não configurado", como hoje acontece com o Bling.
- Valores com espaços extras, CEP/CNPJ com ou sem máscara: são normalizados (só dígitos) antes da validação.
- Mapeamento de situações do Bling referenciando uma situação interna inexistente, ou duas situações Bling apontando de forma conflitante: a inicialização falha nomeando o item.
- Deploys já existentes (produção atual) que ainda não têm as variáveis novas: ver FR-010.
- Configuração da plataforma (papel da aplicação, lista de clientes do redirecionador) não faz parte do objeto do cliente e continua independente.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: O sistema MUST reunir todos os dados que variam por cliente num único objeto de configuração, carregado das variáveis do deploy na inicialização.
- **FR-002**: O objeto MUST conter: identificação do cliente; marca (nome da loja); endereço público do front; remetente (razão social, CNPJ, inscrição estadual, endereço completo com CEP, telefone, e-mail); postagem (modalidade agência ou coleta e agência padrão); margem sobre o frete e prazo de manuseio em dias; credenciais do Bling, Melhor Envio e Mercado Pago; mapeamento de situações do Bling para os estados internos do pedido.
- **FR-003**: Nenhum ponto do código MUST ler dado de cliente fora desse objeto (hoje: CEP de origem na cotação e no checkout, nome do projeto na identificação da API, URL do front e identificação do cliente na conexão Bling); um teste MUST impedir regressões.
- **FR-004**: Dados obrigatórios ausentes MUST impedir a inicialização com mensagem que nomeia cada dado ausente.
- **FR-005**: O sistema MUST validar formato de CEP (8 dígitos), CNPJ (dígitos verificadores), e-mail, URL (https fora de ambiente local), telefone, margem (não negativa), prazo de manuseio (inteiro não negativo), modalidade de postagem, mapeamento de situações, chave de criptografia de tokens do Bling (formato válido) e chave de assinatura do Bling (no mínimo 32 caracteres); valores inválidos MUST impedir a inicialização com mensagem que nomeia o dado e o motivo.
- **FR-006**: Todos os problemas de configuração MUST ser reportados juntos numa única falha de inicialização.
- **FR-007**: Segredos MUST ficar mascarados em qualquer representação textual, log e mensagem de erro, e nunca MUST ser incluídos em respostas HTTP.
- **FR-008**: As credenciais do Melhor Envio MUST ser obrigatórias. As do Bling e do Mercado Pago MUST ser opcionais e validadas como grupo: ou o grupo está completo, ou ausente; grupo parcial MUST impedir a inicialização. Integração ausente MUST resultar em "não configurado" nas funcionalidades dependentes. Tudo o que depende do Bling (credenciais, mapeamento de situações) permanece opcional.
- **FR-009**: Margem sobre o frete e prazo de manuseio MUST ter valores padrão neutros (zero) quando não informados. Esta feature apenas os disponibiliza na configuração; aplicá-los à cotação fica com a issue de frete (#62).
- **FR-010**: A mudança MUST manter o deploy de produção atual funcionando sem novas variáveis. Remetente (exceto o CEP de origem, já obrigatório hoje) e postagem MUST ser opcionais nesta entrega, validados quando preenchidos; a feature que os consumir (etiqueta, NF-e) passa a exigi-los.
- **FR-011**: O sistema MUST documentar, num único lugar versionado, cada variável do cliente com nome, obrigatoriedade, formato e exemplo fictício.
- **FR-012**: A marca e os dados de contato da vitrine continuam vindo da configuração do próprio deploy do front; nenhum endpoint público de configuração é criado nesta feature.

### Key Entities

- **Configuração do cliente**: conjunto imutável durante a execução, com seções: identificação, marca, front, remetente, postagem, frete (margem, manuseio), integrações (Bling, Melhor Envio, Mercado Pago) e mapeamento de situações do Bling.
- **Remetente**: razão social, CNPJ, IE, endereço (logradouro, número, complemento, bairro, cidade, UF, CEP), telefone, e-mail.
- **Mapeamento de situações do Bling**: pares "identificador da situação no Bling → estado interno do pedido".
- **Configuração da plataforma** (fora do escopo): papel da aplicação e lista de clientes do redirecionador central; continua separada.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: Um novo cliente é colocado no ar sem nenhuma alteração de código, apenas preenchendo as variáveis documentadas.
- **SC-002**: 100% dos dados de cliente usados pelo código passam pelo objeto de configuração (verificado por teste automatizado).
- **SC-003**: Para cada dado obrigatório ou validado, existe um teste em que sua ausência ou invalidez impede a inicialização com mensagem que o nomeia.
- **SC-004**: Zero ocorrências de valor de segredo em logs, mensagens de erro e respostas HTTP nos testes.
- **SC-005**: O deploy de produção atual continua respondendo ao smoke (saúde e catálogo) depois da entrega.

## Assumptions

- Um deploy atende exatamente um cliente; não há troca de cliente em tempo de execução.
- A configuração vem só de variáveis de ambiente do deploy (e do arquivo local em desenvolvimento); não há painel para editá-la nesta feature.
- Configurações técnicas que não variam por cliente de forma de negócio (banco, pool, limites de requisição, CORS, chaves JWT) permanecem onde estão; apenas os dados de cliente listados em FR-002 entram no objeto.
- O front white-label já recebe marca e contato pela configuração do próprio deploy; por isso não há endpoint de configuração da vitrine (princípio VI).
- O mapeamento de situações do Bling é só configuração nesta feature; seu uso fica com a issue de pedidos (#58). Nenhuma parte depende do Bling real.
- Nomes atuais de variáveis em uso em produção são preservados ou aceitos como alternativos, para não exigir mudança simultânea na Vercel.
