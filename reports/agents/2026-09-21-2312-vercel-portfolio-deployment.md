# Deploy de portfólio no Vercel

## Objetivo e escopo

Publicar os projetos já existentes no Vercel como portfólio pessoal não
comercial, usando o plano Hobby e sem habilitar serviços pagos. Os projetos
permanecem separados: API FastAPI e storefront Vite.

## Critérios de aceite

- Usar somente o plano Hobby já existente.
- Atualizar variáveis pelo `.env` sem expor valores no chat ou no Git.
- Publicar API e storefront em produção.
- Configurar o cliente para a API HTTPS e o CORS para a origem exata.
- Verificar health, CORS e rotas SPA públicas.

## Resumo dos agentes

### ecommerce_api

Confirmou a saúde pública da API e o preflight CORS. O health respondeu `200`
e a API aceita apenas `https://frontatacadao.vercel.app`; uma origem não
confiável recebeu `400`.

### ecommerce_frontend

Confirmou `200` para a raiz, `/carrinho` e `/pagamento/retorno`. O rewrite da
SPA está ativo e o bundle publicado usa
`https://ecommerce-atacadao.vercel.app/api/v1`.

### ecommerce_reviewer

Revisou a publicação sob o escopo de portfólio pessoal não comercial. Veredito
final: `approved`.

## Decisões de infraestrutura

- API: `https://ecommerce-atacadao.vercel.app`
- Storefront: `https://frontatacadao.vercel.app`
- A API recebeu as variáveis não vazias do `.env` e URLs públicas coerentes para
  CORS, retorno e webhook do Mercado Pago. Valores não foram registrados neste
  relatório.
- O storefront recebeu `VITE_API_BASE_URL` apontando para a API HTTPS com
  `/api/v1`.
- Foram criados novos deploys de produção dos dois projetos, sem criar serviços
  adicionais, domínios personalizados, banco, marketplace ou plano pago.

## Achados do revisor

- O Hobby é apropriado somente enquanto este projeto for portfólio pessoal e
  não comercial. A documentação foi corrigida para refletir esse escopo.
- Neon, Mercado Pago e Melhor Envio possuem condições e possíveis custos
  próprios; devem permanecer em modalidades gratuitas para respeitar a
  exigência do usuário.
- O health não executa checkout nem valida a conectividade com Neon.

## Correções e ciclos de revisão

O README inicialmente bloqueava qualquer publicação no Hobby. Após a
confirmação explícita de uso não comercial, foi corrigido para permitir este
portfólio pessoal e manter a vedação de uso comercial.

## Testes e verificações

- `GET https://ecommerce-atacadao.vercel.app/health` — `200`.
- Preflight CORS do storefront para a API — `200`, com origem exata e
  credenciais habilitadas.
- Preflight de origem não confiável — `400`.
- Storefront, `/carrinho` e `/pagamento/retorno` — `200`.
- `git diff --check` — aprovado.

## Riscos e trabalho restante

O fluxo autenticado, checkout e webhook não foram executados contra produção.
Não aplicar migrações durante build ou requisição; mudanças de schema devem
continuar em ambiente controlado. Reavalie hospedagem e custos antes de qualquer
uso comercial ou aumento significativo de tráfego.

## Veredito final do orquestrador

`approved` para publicação do portfólio pessoal no Vercel Hobby. Os deploys
estão ativos e as integrações públicas básicas foram verificadas.
