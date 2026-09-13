# Preparação Vercel e commits modulares

## Objetivo e escopo

Organizar o backend e o frontend em repositórios Git independentes, com commits
atômicos e configuração suficiente para importação separada na Vercel. Não houve
publicação, alteração de variáveis remotas, migration aplicada ou acesso a
credenciais.

## Critérios de aceite

- Backend FastAPI com entrypoint explícito e documentação de variáveis,
  CORS, PostgreSQL externo e migrations.
- Frontend Vite com rota SPA preservada e URL da API configurada por ambiente.
- Nenhum segredo ou `.env` incluído no Git.
- Commits coesos e verificações de backend/frontend aprovadas.

## Resumo dos agentes

- `ecommerce_frontend`: preparou o Vite para Vercel, com rewrite SPA e README;
  confirmou build e ausência de segredos no cliente.
- `ecommerce_api`: não concluiu a inspeção de deploy no tempo disponível.
- `ecommerce_reviewer`: revisou os commits integrados e aprovou entradas,
  ignore rules, documentação de CORS, migration externa e rotas do frontend.

## Commits criados

### Backend (`EcommerceAtacadao`)

1. `932dc5f` `chore: add ecommerce agent workflow`
2. `38358fe` `feat: harden cart pricing shipping and checkout`
3. `0ff3c82` `feat: add Mercado Pago Checkout Pro Orders`
4. `a5c9e42` `chore: prepare FastAPI deployment on Vercel`
5. `bd6e7de` `docs: add implementation coordination reports`

### Frontend (`front_atacadao`)

1. `6804b1b` `chore: configure Vercel storefront deployment`
2. `216ed78` `feat: add customer storefront and Checkout Pro journey`

## Configuração de deploy

- Vercel detecta o backend por `[tool.vercel] entrypoint = "src.main:app"`.
- O frontend usa Vite, publica `dist` e mantém `/carrinho` e
  `/pagamento/retorno` por rewrite para `index.html`.
- O projeto frontend requer `VITE_API_BASE_URL` contendo a URL pública da API e
  `/api/v1`.
- A API requer `CORS_ALLOWED_ORIGINS` com a origem HTTPS exata do frontend,
  junto das variáveis de banco, identidade, Melhor Envio e Mercado Pago.
- Migrations Alembic devem ser executadas externamente contra PostgreSQL antes
  da promoção; nunca pelo build ou por requisição serverless.

## Testes e verificações

- Backend: 30 testes focalizados passaram.
- Lint focal e `git diff --check`: aprovados.
- Frontend: `npm run build` passou.
- Revisão independente: **approved**.

## Veredito do orquestrador

**Concluído e aprovado.** Os repositórios estão prontos para serem enviados a
hosts Git separados e importados como dois projetos Vercel. A configuração de
valores no painel Vercel e o deploy continuam ações externas a serem feitas pelo
responsável pela infraestrutura.
