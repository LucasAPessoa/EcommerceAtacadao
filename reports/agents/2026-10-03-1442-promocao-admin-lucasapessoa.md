# Promoção manual para administrador — bloqueada

## 1. Objetivo e escopo

Promover manualmente a conta `lucasapessoa@outlook.com` para a role canônica
`admin`, sem alterar schema, código de produto, outros registros ou dados de
perfil.

## 2. Critérios de aceite

1. Encontrar exatamente um usuário com o e-mail solicitado.
2. Encontrar exatamente uma role com nome `admin`.
3. Atualizar exclusivamente `users.role_id` daquele usuário em uma transação.
4. Confirmar após o commit que a role efetiva é `admin`.
5. Não expor credenciais, URL do banco ou outros dados sensíveis.

## 3. Resumo de cada agente

- `ecommerce_frontend`: não há aplicação frontend. Confirmou que o contrato
  `GET /users/me` expõe a role e que a autorização consulta a role atual do
  banco em cada requisição. Nenhum arquivo alterado.
- `ecommerce_api`: confirmou `users.email` e `roles.name` como chaves únicas e
  que `role_id` é o campo correto. Não executou a transação: a configuração do
  banco não estava disponível ao processo por causa do arquivo `.env`
  protegido e da ausência de `DATABASE_URL` no ambiente.
- `ecommerce_reviewer`: classificou a conclusão como bloqueada, pois falta a
  evidência pós-commit no banco correto.

## 4. Decisões de contrato

- A autoridade de autorização é `users.role_id -> roles.name`, não
  `user_type`; a promoção não deve mudar `user_type`.
- Não existe endpoint HTTP de promoção; esta é uma operação administrativa
  direta no banco.
- Access e refresh tokens existentes continuam válidos. Como o usuário é
  recarregado com sua role por requisição, a nova permissão seria efetiva na
  próxima requisição autenticada após o commit.

## 5. Achados do revisor por prioridade

- P1 — **blocked**: não há conexão configurada ao banco neste ambiente e,
  portanto, não existe confirmação pós-commit. Não afirmar que a conta foi
  promovida.

## 6. Correções e ciclos de nova revisão

Nenhuma alteração de produto foi feita. A execução deve ocorrer em um ambiente
autorizado que tenha a configuração do banco, com uma transação condicional que
aborte se as contagens de usuário ou role não forem exatamente uma e que releia
o resultado após o commit. Em seguida, solicitar nova revisão da evidência.

## 7. Testes e verificações

- Inspeção de `src/models/identity.py` e da migração inicial: `users.email` é
  único e `users.role_id` referencia `roles.id`.
- Inspeção da autenticação e rota de perfil: a role é carregada do banco no
  fluxo autenticado.
- `git diff --check`: aprovado.
- Tentativa de execução com `uv run`: falhou antes de iniciar Python porque o
  cache padrão do `uv` é somente leitura. Não houve conexão, `UPDATE` ou
  `COMMIT`.

## 8. Riscos ou trabalho restante

Executar a promoção no ambiente que possui acesso ao banco e validar o estado
final. Não copiar credenciais para comandos, relatórios ou chat.

## 9. Veredito final do orquestrador

**blocked** — a promoção não foi aplicada. O bloqueio é de acesso à
configuração/conexão do banco, e não uma ambiguidade no usuário ou na role.
