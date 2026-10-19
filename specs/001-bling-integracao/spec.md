# Feature Specification: Integração com o Bling (conexão da conta)

**Feature Branch**: `spec/001-bling-integracao`

**Created**: 2026-10-18

**Status**: Draft

**Input**: User description: "Integração com o Bling: cada cliente autoriza a própria conta Bling uma única vez; o sistema guarda e renova esse acesso com segurança e oferece uma conexão confiável (com limites de requisição e erros tratados) para o sincronismo de catálogo, envio de pedidos e consulta de NF-e."

**Issues**: #50 (estudo das APIs), #52 (cliente Bling e autorização). Consumidores desta conexão: #54 (sincronismo), #58 (pedidos), #60 (NF-e).

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Conectar a conta Bling da loja (Priority: P1)

O administrador da loja (normalmente acompanhado pelo operador da plataforma) abre o painel administrativo, escolhe "Conectar Bling", entra na própria conta Bling, aprova o acesso e volta ao painel, que passa a mostrar a loja como conectada, com a identificação da empresa Bling vinculada.

**Why this priority**: sem a conta conectada nenhuma outra parte do MVP funciona: catálogo, pedidos e NF-e dependem dela.

**Independent Test**: numa loja sem conexão, executar o fluxo de conexão com uma conta Bling de teste e verificar que o painel mostra "Conectado" com a empresa correta e que uma consulta simples ao Bling (ex.: dados da empresa) funciona.

**Acceptance Scenarios**:

1. **Given** uma loja sem conta Bling conectada, **When** o administrador conclui a aprovação no Bling, **Then** o painel mostra "Conectado", o nome/identificação da empresa Bling e a data da conexão.
2. **Given** o administrador está na tela de aprovação do Bling, **When** ele recusa ou cancela, **Then** o painel volta mostrando "Não conectado" e uma mensagem clara, sem registrar conexão parcial.
3. **Given** uma tentativa de conexão iniciada por outra pessoa ou em outra sessão, **When** a resposta do Bling chega sem corresponder a uma tentativa legítima desta loja, **Then** a conexão é recusada.
4. **Given** um usuário sem perfil de administrador, **When** ele tenta iniciar ou ver os detalhes da conexão, **Then** o acesso é negado.

---

### User Story 2 - Acesso contínuo sem nova autorização (Priority: P2)

Depois de conectada, a loja continua acessando o Bling indefinidamente sem que ninguém precise autorizar de novo, enquanto a autorização não for revogada no Bling.

**Why this priority**: o sincronismo roda a cada ~15 minutos e os pedidos chegam a qualquer hora; uma conexão que expira silenciosamente para catálogo, pedidos e NF-e.

**Independent Test**: conectar uma conta de teste, deixar o acesso expirar naturalmente e confirmar que as consultas seguintes continuam funcionando sem ação humana; depois revogar a autorização no Bling e confirmar que o painel passa a mostrar "Reconexão necessária".

**Acceptance Scenarios**:

1. **Given** uma loja conectada cujo acesso temporário expirou, **When** qualquer processo precisar do Bling, **Then** o acesso é renovado automaticamente e o processo continua.
2. **Given** dois processos que precisam renovar o acesso ao mesmo tempo, **When** ambos tentam, **Then** a renovação acontece uma única vez e os dois seguem com o acesso válido.
3. **Given** a autorização foi revogada no Bling (ou a renovação é recusada definitivamente), **When** um processo tenta acessar, **Then** a loja passa a "Reconexão necessária", o painel exibe um aviso destacado, um alerta operacional é registrado e os processos dependentes pausam sem perder trabalho pendente.
4. **Given** uma loja em "Reconexão necessária", **When** o administrador conecta de novo a mesma empresa Bling, **Then** a loja volta a "Conectado" e os processos pausados retomam.

---

### User Story 3 - Conexão confiável para os processos da loja (Priority: P3)

O sincronismo de catálogo, o envio de pedidos e a consulta de NF-e usam a mesma conexão, que respeita os limites de uso do Bling, tenta novamente falhas passageiras e informa com clareza as falhas definitivas.

**Why this priority**: sem isso, picos de uso geram bloqueios do Bling e falhas passageiras viram trabalho manual; mas só tem valor depois das histórias 1 e 2.

**Independent Test**: simular respostas do Bling de "limite excedido", indisponibilidade temporária e erro definitivo, e verificar o comportamento de cada caso sem depender das features consumidoras.

**Acceptance Scenarios**:

1. **Given** um volume de chamadas acima do limite permitido pelo Bling, **When** os processos fazem as chamadas, **Then** elas são espaçadas para respeitar o limite e nenhuma é perdida.
2. **Given** o Bling responde com indisponibilidade temporária ou limite excedido, **When** uma chamada falha, **Then** ela é repetida algumas vezes com intervalo crescente antes de ser considerada falha.
3. **Given** uma falha definitiva (dados inválidos, recurso inexistente, permissão negada), **When** a chamada falha, **Then** ela não é repetida e o processo consumidor recebe um erro classificado e uma mensagem compreensível.
4. **Given** qualquer falha, **When** ela é registrada, **Then** o registro não contém credenciais, tokens nem dados pessoais desnecessários.

---

### User Story 4 - Ver e encerrar a conexão (Priority: P3)

O administrador vê o estado da conexão (conectado, reconexão necessária, não conectado), a última renovação bem-sucedida e o último erro, e pode desconectar a conta.

**Why this priority**: dá visibilidade operacional e permite encerrar o acesso, mas a loja funciona sem a tela de detalhes.

**Independent Test**: com uma loja conectada, abrir a tela de status, conferir as informações e desconectar; verificar que o sistema deixa de acessar o Bling e descarta as credenciais.

**Acceptance Scenarios**:

1. **Given** uma loja conectada, **When** o administrador abre a tela de status, **Then** vê o estado, a empresa vinculada, a última renovação e o último erro (se houver).
2. **Given** uma loja conectada, **When** o administrador confirma "Desconectar", **Then** as credenciais são descartadas, o estado vira "Não conectado" e os processos dependentes pausam.

### Edge Cases

- O administrador tenta conectar uma **empresa Bling diferente** da que já está vinculada: a tentativa é recusada com mensagem e a conexão atual permanece intacta (FR-012).
- O Bling fica indisponível por horas: os processos pausam e retomam sozinhos quando ele volta, sem duplicar efeitos.
- A renovação falha por erro passageiro (não por revogação): o sistema tenta de novo e só marca "Reconexão necessária" se a recusa for definitiva.
- O deploy é reiniciado durante uma renovação: a conexão continua válida depois do reinício.
- A resposta do Bling ao final da autorização chega duas vezes (ex.: usuário recarrega a página): a conexão é registrada uma única vez.
- Uma loja nunca conectada recebe uma chamada de processo dependente: o processo recebe "não conectado" e não falha de forma desordenada.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: O sistema MUST permitir que um administrador da loja inicie a conexão com o Bling a partir do painel administrativo e conclua a aprovação na própria conta Bling.
- **FR-002**: O sistema MUST validar que a resposta do Bling ao final da autorização corresponde a uma tentativa legítima iniciada nesta loja e recente; caso contrário, MUST recusar a conexão.
- **FR-003**: O sistema MUST registrar a empresa Bling vinculada (identificação e nome) e mostrá-la no painel.
- **FR-004**: O sistema MUST guardar as credenciais de acesso de forma protegida (ilegíveis para quem tiver acesso apenas ao armazenamento) e MUST NOT expô-las em telas, respostas, registros ou mensagens de erro.
- **FR-005**: O sistema MUST renovar o acesso automaticamente antes ou no momento em que ele expirar, sem ação humana.
- **FR-006**: O sistema MUST garantir que renovações simultâneas resultem em uma única renovação efetiva, sem invalidar o acesso de nenhum processo.
- **FR-007**: O sistema MUST distinguir recusa definitiva (revogação, autorização inválida) de falha passageira na renovação; só a recusa definitiva leva ao estado "Reconexão necessária".
- **FR-008**: Em "Reconexão necessária" ou "Não conectado", o sistema MUST pausar os processos dependentes sem perder o trabalho pendente, exibir aviso no painel e registrar um alerta operacional. Nesta feature, a conexão sinaliza o estado com erros classificados; a pausa sem perda é responsabilidade de cada processo consumidor (#54, #58, #60) e deve constar nos critérios de aceite deles.
- **FR-009**: O sistema MUST respeitar os limites de uso do Bling por conta, espaçando chamadas quando necessário.
- **FR-010**: O sistema MUST repetir chamadas que falharem por indisponibilidade temporária ou limite excedido, com número máximo de tentativas e intervalo crescente, e MUST NOT repetir falhas definitivas.
- **FR-011**: O sistema MUST entregar aos processos consumidores erros classificados (não conectado, reconexão necessária, limite/indisponibilidade esgotados, erro definitivo do Bling) com mensagem compreensível.
- **FR-012**: Depois que uma loja tiver uma empresa Bling vinculada, o sistema MUST aceitar apenas a reconexão da **mesma** empresa; a conexão de qualquer outra empresa MUST ser recusada com mensagem clara, sem alterar a conexão nem os dados existentes. A troca de empresa com procedimento formal de reinício fica para depois do MVP (#68).
- **FR-013**: O administrador MUST conseguir ver o estado da conexão, a empresa vinculada, a data da última renovação bem-sucedida e o último erro.
- **FR-014**: O administrador MUST conseguir desconectar a conta, o que descarta as credenciais e pausa os processos dependentes.
- **FR-015**: Apenas usuários com perfil de administrador MUST poder iniciar, ver detalhes ou encerrar a conexão.
- **FR-016**: Cada loja (cliente) MUST ter sua própria conexão, isolada das demais; nenhuma loja acessa a conta Bling de outra.
- **FR-017**: O sistema MUST registrar eventos da conexão (conectado, renovado, falha de renovação, reconexão necessária, desconectado) com data e motivo, sem dados sensíveis.

### Key Entities

- **Conexão Bling da loja**: uma por loja. Estado (não conectado, conectado, reconexão necessária), empresa Bling vinculada (identificação e nome), data da conexão, data da última renovação bem-sucedida, último erro e credenciais protegidas.
- **Tentativa de autorização**: registro temporário de uma conexão iniciada (quem iniciou, quando, validade), usado para validar a resposta do Bling e descartado depois.
- **Evento da conexão**: histórico de mudanças de estado e falhas relevantes, com data e motivo, para diagnóstico e alertas.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: Um administrador conecta a conta Bling da loja em menos de 2 minutos, sem ajuda técnica além das próprias credenciais do Bling.
- **SC-002**: Em 30 dias de operação normal, nenhuma loja do beta precisa reautorizar o Bling, exceto por revogação feita no próprio Bling.
- **SC-003**: Quando a autorização é revogada, a loja aparece como "Reconexão necessária" e o alerta é registrado em até 15 minutos.
- **SC-004**: Pelo menos 99% das falhas passageiras do Bling são recuperadas sem intervenção humana.
- **SC-005**: Nenhuma credencial ou token aparece em telas, respostas ou registros (verificado em revisão e em teste).
- **SC-006**: Picos de chamadas dos processos da loja não provocam bloqueio da conta por excesso de uso.

## Assumptions

- Existe um único aplicativo da plataforma registrado no Bling (criado pelo operador); cada loja autoriza esse aplicativo na própria conta.
- Cada loja é um deploy separado com banco próprio (constituição, princípio III); "isolada" significa que credenciais de uma loja nunca são usadas por outra.
- Quem aprova no Bling é alguém com acesso à conta Bling do cliente; no beta, o operador da plataforma conduz o processo junto com o cliente.
- O alerta operacional usa o mecanismo de alertas da issue #12; até ele existir, basta o aviso no painel e o registro do evento.
- Os limites exatos de uso, a duração do acesso e o formato dos erros do Bling serão confirmados no estudo da API (#50) durante o planejamento.
- Webhooks do Bling estão fora do escopo do MVP; sincronismo de catálogo, envio de pedidos e consulta de NF-e são features separadas que usam esta conexão.
