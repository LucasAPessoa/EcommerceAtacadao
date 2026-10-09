# Páginas de autenticação e reorganização visual

## Objetivo e escopo

Corrigir o cabeçalho duplicado percebido no storefront, criar páginas próprias
de login e cadastro, melhorar a organização visual e garantir que o cadastro
público respeite o contrato de identidade.

## Critérios de aceite

- Um único cabeçalho com navegação responsiva.
- Rotas públicas `/entrar` e `/cadastro`, sem modal de autenticação.
- Cadastro de pessoa física e empresa com campos coerentes.
- Cadastro público não pode criar usuários administrativos.
- Carrinho, Checkout Pro, conta, painel administrativo e filtros existentes
  permanecem funcionais.

## Resumo dos agentes

- Frontend: implementou as rotas, formulários próprios, 404, cabeçalho unificado,
  estados e estilos responsivos.
- API: não iniciou no tempo disponível; o orquestrador corrigiu o validador de
  cadastro e acrescentou testes unitários.
- Revisor: pediu nome acessível para o campo de busca. A correção foi aplicada e
  recebeu veredito `approved`.

## Decisões de contrato

- O `UserCreate` público aceita somente `INDIVIDUAL` e `COMPANY`.
- Pessoa física exige CPF; empresa exige CNPJ e razão social. Campos do outro
  tipo são limpos no servidor.
- A role continua atribuída como `user` por `AuthService`; `ADMIN` não pode ser
  enviado pelo formulário nem aceito pelo schema público.

## Alterações

- Frontend: `App.tsx`, `components/Layout.tsx`, `features/auth/AuthPages.tsx`,
  cliente HTTP, catálogo, retorno de pagamento e estilos.
- Backend: `UserCreate` e testes de schema em
  `tests/identity/test_user_schema_unit.py`.

## Correções após revisão

- O input de busca recebeu `aria-label="Buscar produtos"` e o ícone foi marcado
  como decorativo.
- A confirmação de cadastro aparece somente em `/entrar`, sem aviso duplicado.

## Testes e verificações

- Frontend: `npm run build` — aprovado.
- Backend: `uv run pytest tests/identity/test_user_schema_unit.py tests/test_main_unit.py -q`
  — 6 aprovados.
- Backend: Ruff focado — aprovado.
- Navegador local: um único elemento `header`, sem overflow horizontal em desktop
  e viewport móvel de 390px.
- `git diff --check` nos dois repositórios — aprovado.

## Riscos e trabalho restante

O frontend não possui suíte automatizada própria; a cobertura atual é build,
checagem de tipos e inspeção manual responsiva. Permanecem avisos preexistentes
de deprecação de configuração Pydantic fora deste escopo.

## Veredito final

`approved` pelo revisor independente e pelo orquestrador.
