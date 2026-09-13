# Recuperação de CORS e Vite local

## 1. Objetivo e escopo

Diagnosticar o bloqueio CORS persistente entre o frontend local e a API e
restabelecer um ambiente local funcional.

## 2. Critérios de aceite

- A API deve devolver o header CORS para a origem real do Vite.
- O processo Vite deve servir o projeto movido para `front_atacadao`.
- O catálogo deve responder `200` com `Access-Control-Allow-Origin` correto.

## 3. Resumo de cada agente

- `ecommerce_api`: confirmou que o único middleware CORS da aplicação raiz
  envolve catálogo, preflight e erros.
- `ecommerce_frontend`: confirmou URL da API, ausência de service worker e a
  estratégia de recuperação de uma aba/processo Vite antigo.
- `ecommerce_reviewer`: revisou o diagnóstico e emitiu `approved`.

## 4. Decisões de contrato

As origens locais permitidas continuam
`http://127.0.0.1:5173` e `http://localhost:5173`, sem wildcard e com
credenciais.

## 5. Achados do revisor por prioridade

Nenhum achado adicional.

## 6. Correções e ciclos de nova revisão

A API ativa já devolvia os headers corretos. O problema efetivo era o processo
Vite da porta 5173, iniciado pelo caminho antigo
`EcommerceAtacadao/frontend`, embora seu diretório atual já fosse
`front_atacadao`. O processo obsoleto foi encerrado e Vite foi reiniciado no
novo projeto.

## 7. Testes e verificações

- GET do catálogo com origem `localhost:5173`: `200` e header CORS correto.
- OPTIONS do catálogo com `authorization,content-type`: `200` e preflight
  correto.
- GET com origem `127.0.0.1:5173`: `200` e header CORS correto.
- Vite novo em `http://127.0.0.1:5173/`: `200`.

## 8. Riscos ou trabalho restante

Use a URL exibida pelo Vite atual e evite iniciar o cliente a partir do caminho
antigo. O processo Vite está ativo na porta 5173.

## 9. Veredito final do orquestrador

**approved**. O catálogo está disponível ao frontend local sem bloqueio CORS.
