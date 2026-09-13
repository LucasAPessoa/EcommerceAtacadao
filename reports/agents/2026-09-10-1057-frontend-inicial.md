# Frontend inicial do Ecommerce Atacadão

## 1. Objetivo e escopo

Criar a primeira vitrine web do Ecommerce Atacadão em `frontend/`, inspirada na
estrutura comercial da referência compartilhada (oferta, busca, conta, carrinho,
categorias, vitrine e rodapé), sem reproduzir sua marca, conteúdo ou assets.
O cliente deve respeitar o `IDEA.md` e o contrato real da API.

## 2. Critérios de aceite

- Interface simples, responsiva, acessível e com identidade visual própria.
- Consumo configurável do catálogo, autenticação, carrinho, endereços, frete e
  checkout existentes.
- Estados de carregamento, catálogo vazio/indisponível, autenticação, frete e
  revisão de checkout tratados de forma clara.
- Preço, desconto, estoque e frete continuam sob autoridade do servidor.
- Nenhum segredo, pagamento, ERP, remessa ou cadastro inexistente é simulado.

## 3. Resumo de cada agente

- `ecommerce_frontend`: criou a aplicação React/Vite em `frontend/`, incluindo
  vitrine, busca, modal de produto e frete, login, carrinho autenticado,
  endereço, preview e confirmação idempotente. Corrigiu mensagens de rede e
  fluxo de sessão após revisão.
- `ecommerce_api`: inspecionou os contratos reais sem editar o backend. Apontou
  lacunas de faixas atacadistas por produto, produto inativo na listagem,
  cadastro individual e semântica de erro do preview.
- `ecommerce_reviewer`: revisou o diff, identificou e confirmou a correção do
  tratamento de `401` em login e em recursos privados. Veredito final:
  `approved`.

## 4. Decisões de contrato

- A URL da API vem de `VITE_API_BASE_URL`, com padrão local
  `http://127.0.0.1:8000/api/v1`.
- O cliente usa o preço enviado pelo catálogo e confirma o preço comercial,
  frete, estoque e desconto exclusivamente pelo preview do checkout.
- A confirmação envia uma `Idempotency-Key` UUID que se mantém no retry da
  mesma revisão.
- O login é oferecido; o cadastro fica fora da interface enquanto o validador
  do backend não suportar o fluxo individual corretamente.

## 5. Achados do revisor por prioridade

- P2 corrigido: uma resposta `401` ao login poderia abrir novamente um diálogo
  já aberto e limpar uma sessão válida. Falha de login agora mantém diálogo e
  sessão; somente recursos privados expiram a sessão.
- P2 corrigido: a indisponibilidade da API mostrava `Failed to fetch` cru. A
  interface agora apresenta orientação estável em português e estado próprio de
  catálogo indisponível.

## 6. Correções e ciclos de nova revisão

Após a primeira implementação, a inspeção visual local levou à correção da
mensagem de rede. A revisão independente identificou o tratamento incorreto de
`401`; o frontend separou falhas de login de expiração de recursos privados. O
revisor aprovou o novo diff.

## 7. Testes e verificações

- `cd frontend && npm run build`: passou, com TypeScript e build Vite.
- `git diff --check`: passou.
- Inspeção no navegador local confirmou a estrutura semântica, foco de teclado,
  links de salto e o estado de API indisponível com mensagem segura.

## 8. Riscos ou trabalho restante

- A lista de produtos atual não inclui faixas atacadistas por produto. Uma rota
  filtrada ou tiers no detalhe do produto permitirá explicar descontos antes do
  checkout sem baixar dados globais.
- O backend ainda pode devolver produto inativo na listagem e possui uma falha
  no cadastro individual; a interface evita expor esse cadastro e filtra itens
  marcados inativos.
- Refresh token, recuperação de sessão, cadastro e integração de pagamento
  ficam para uma próxima etapa. Configure `CORS_ALLOWED_ORIGINS` e
  `VITE_API_BASE_URL` nos ambientes reais.

## 9. Veredito final do orquestrador

**approved**. A versão inicial do frontend está funcional contra o contrato
atual, é explícita sobre seus limites e passou pela revisão independente.
