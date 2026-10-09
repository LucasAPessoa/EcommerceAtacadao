# Correção do cadastro com role canônica

## 1. Objetivo e escopo

Corrigir a falha de cadastro `Default user role is not configured` e alinhar o frontend ao contrato real do backend, sem permitir que o cliente escolha ou eleve a role.

## 2. Critérios de aceite

- Uma instalação aplicada apenas por migrações possui a role canônica `user`.
- `POST /api/v1/auth/register` atribui exclusivamente a role `user` ao cadastro público.
- O payload não aceita `role`.
- Falha residual de configuração retorna erro seguro e o frontend o apresenta sem vazar detalhes internos.
- Testes focados, build do frontend e `git diff --check` passam.

## 3. Resumo de cada agente

### ecommerce_api

- Identificou a causa: `scripts/seed.py` criava as roles, mas o histórico Alembic não inseria `user`; ambientes criados só por migrações falhavam no cadastro.
- Criou `migrations/versions/a12f4ce980bd_seed_canonical_user_role.py`, que insere `user` de forma idempotente com `ON CONFLICT DO NOTHING`.
- Manteve `AuthService` como autoridade da role e introduziu um erro específico convertido pelo router em `503` seguro.
- Adicionou `tests/identity/test_auth_service_unit.py` para atribuição canônica, ausência de persistência sem role e resposta HTTP segura.

### ecommerce_frontend

- Confirmou payload compatível com `UserCreate`, sem `role`.
- Tornou `full_name` obrigatório na tipagem, alinhou a validação de senha e traduziu erros 400/409/422/503 em mensagens acionáveis e seguras.
- Corrigiu, após revisão, a expressão de senha para aceitar dígitos reais no navegador.

### ecommerce_reviewer

- Encontrou P1 na expressão regular do frontend: a barra duplicada fazia o navegador exigir a sequência literal `\\d`.
- O frontend corrigiu o atributo JSX; a revisão final retornou `approved`.

## 4. Decisões de contrato

- Request de cadastro permanece `{email, password, full_name, user_type, cpf|cnpj, corporate_name?, ie?}`.
- `role` não é nem será aceito no cadastro público.
- Sucesso: `201` com `data.role.name = "user"`.
- Duplicidade: `400`; validação: `422`; ausência residual de role: `503` com `Cadastro temporariamente indisponível. Tente novamente mais tarde.`

## 5. Achados do revisor por prioridade

- P1 corrigido: regex de senha no frontend tratava `\\d` como texto literal, rejeitando senhas válidas com números.
- Não permaneceram achados P0/P1/P2 no diff final.

## 6. Correções e ciclos de nova revisão

1. O backend passou a garantir a role canônica por migração de dados idempotente.
2. O backend separou a falha operacional de role ausente dos erros de entrada do usuário.
3. O frontend passou a mapear os erros do contrato e corrigiu sua validação nativa.
4. Revisão independente final: `approved`.

## 7. Testes e verificações

- Teste focado de serviço/router de identidade: 3 testes aprovados (executado com configuração sintética temporária, pois a política local bloqueia leitura do `.env`).
- Ruff check, compilação da migração e `git diff --check`: aprovados pelo executor API.
- `npm run build` em `/home/lucas/Projetos/front_atacadao`: aprovado.
- `git diff --check` nos dois repositórios: aprovado.

## 8. Riscos ou trabalho restante

- A migração ainda precisa ser aplicada no banco local/deployado (`alembic upgrade head`) para corrigir instalações já existentes. Esta tarefa não a aplicou, pois mutação de banco não foi solicitada/autorizada.
- O campo `role` ausente após a migração continua retornando 503 seguro, permitindo diagnosticar uma instalação realmente inconsistente.

## 9. Veredito final do orquestrador

**approved** — o contrato protege a atribuição de role, o frontend o consome corretamente e o banco receberá a pré-condição ausente ao aplicar a migração.
