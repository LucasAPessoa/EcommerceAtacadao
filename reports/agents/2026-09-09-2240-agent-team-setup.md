# Report: estrutura de coding agents

## Objetivo e escopo

Criar uma equipe especializada para o EcommerceAtacadao com um orquestrador,
especialistas de frontend e API e um revisor independente. O detalhe do trabalho
deve permanecer nas threads e neste report; a resposta ao usuário deve conter
somente o resumo executivo.

## Critérios de aceite

- quatro papéis especializados e específicos para o projeto;
- comunicação entre agentes e ciclos de correção definidos;
- divisão de posse que evite conflitos de edição;
- revisão independente antes do julgamento final;
- reports consolidados em `reports/agents/`;
- configuração válida e integrada à skill do projeto.

## Estrutura criada

| Papel | Perfil | Responsabilidade | Escrita |
| --- | --- | --- | --- |
| Orquestrador | `ecommerce_orchestrator` | Decompõe, delega, arbitra e reporta | Apenas coordenação/reports |
| Frontend | `ecommerce_frontend` | Jornada de compra e contrato consumidor | Frontend, quando existir |
| API | `ecommerce_api` | FastAPI, domínio, banco, integrações e testes | Backend |
| Revisor | `ecommerce_reviewer` | Segurança, integridade, contrato e cobertura | Nenhuma; somente leitura |

O agente principal assume o papel de orquestrador. Assim, o limite de três
subthreads simultâneas corresponde exatamente aos três especialistas.

## Comunicação

1. O orquestrador publica objetivo, critérios e posse de arquivos.
2. Frontend e API trocam decisões de contrato diretamente ou por encaminhamento
   do orquestrador.
3. Cada executor envia um handoff com arquivos, decisões, testes e riscos.
4. O revisor lê o diff integrado e envia achados ao dono e ao orquestrador.
5. O orquestrador solicita correções, espera nova revisão e emite o veredito.

Escritas paralelas no mesmo arquivo são proibidas. Nesses casos, o trabalho é
serializado para evitar conflitos e perda de alterações.

## Decisões específicas do projeto

- O frontend ainda não existe. O especialista atua em jornada, estados e contrato
  e só cria uma aplicação quando isso for pedido explicitamente.
- A API é dona de `src/`, `migrations/`, `tests/` e `scripts/`.
- O revisor prioriza ownership, autenticação, autoridade do servidor, `Decimal`,
  idempotência, locks, reservas, rollback, migrações e testes.
- Reset de banco, mutações externas, publicação e commits conservam as mesmas
  fronteiras de autorização, mesmo quando delegados.

## Arquivos

- `AGENTS.md`: política executável para o agente principal.
- `agents/ecommerce-orchestrator.toml`: perfil do juiz final.
- `agents/ecommerce-frontend.toml`: perfil do especialista frontend.
- `agents/ecommerce-api.toml`: perfil do especialista backend.
- `agents/ecommerce-reviewer.toml`: perfil do revisor independente.
- `agents/config.toml`: habilitação e limite de concorrência.
- `skills/ecommerce-atacadao/references/agents.md`: integração com a skill.

## Validações

- Todos os arquivos TOML foram carregados com `tomllib` sem erro.
- A skill `ecommerce-atacadao` passou no `quick_validate.py`.
- `git diff --check` não encontrou problemas de whitespace.

## Limitação de instalação

A documentação oficial do Codex define `.codex/agents/*.toml` como localização
nativa de agentes específicos do projeto. A pasta `.codex` deste workspace está
montada como somente leitura e não pôde receber arquivos, inclusive após tentativa
com permissão elevada. Os perfis foram mantidos em `agents/` e são aplicados pelo
`AGENTS.md`, que é descoberto pelo agente principal.

Quando a montagem permitir, os perfis podem ser copiados sem alteração para
`.codex/agents/`, e `agents/config.toml` pode ser instalado como
`.codex/config.toml`.

## Riscos e trabalho restante

- A seleção automática dos perfis TOML pelo nome só ocorrerá após instalação em
  `.codex/agents`; até lá, o `AGENTS.md` instrui o orquestrador a carregar as
  instruções no prompt de criação de cada agente.
- Uma execução real da equipe deve ser feita na próxima tarefa adequada para
  validar o comportamento dos handoffs, não apenas a sintaxe da configuração.

## Veredito final

`approved_with_installation_limitation`

A estrutura está pronta e operacional via `AGENTS.md`, com os quatro papéis,
comunicação, revisão e reports definidos. A única restrição é o local nativo
`.codex/agents`, indisponível para escrita neste ambiente.
