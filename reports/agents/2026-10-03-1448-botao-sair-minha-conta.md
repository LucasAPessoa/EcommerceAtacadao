# Botão Sair na Minha Conta — bloqueado

## 1. Objetivo e escopo

Adicionar um botão de saída à tela “Minha Conta”, preservando o fluxo seguro de
revogação de refresh token.

## 2. Critérios de aceite

1. Localizar a tela do cliente que deve receber o botão.
2. Chamar o endpoint de logout autenticado com o refresh token.
3. Limpar credenciais e estado local apenas após uma saída bem-sucedida, com
   tratamento para sessão expirada.
4. Não criar uma aplicação frontend sem autorização explícita.

## 3. Resumo de cada agente

- `ecommerce_frontend`: confirmou que não há frontend, tela, TSX, HTML, CSS ou
  `package.json` no repositório. Não alterou arquivos. Mapeou o contrato e os
  estados UX necessários para uma implementação futura.
- `ecommerce_reviewer`: confirmou a ausência de UI e que não existe diff desta
  tarefa; classificou a entrega do botão como bloqueada.

## 4. Decisões de contrato

- O logout existente é `POST /api/v1/auth/logout`, com `Authorization: Bearer
  <access token>` e corpo `{ "refresh_token": "..." }`.
- Em sucesso, a API retorna HTTP 200 com `data.revoked: true` e revoga somente
  o refresh token pertencente ao usuário autenticado.
- A futura UI deve apagar tokens, cache de usuário e carrinho, e redirecionar
  para a entrada após o sucesso. Para 401/400 de sessão inválida, deve limpar a
  sessão local e redirecionar; em falha de rede/5xx, deve permitir nova tentativa
  sem descartar a sessão local.

## 5. Achados do revisor por prioridade

- P1 — **blocked**: não existe cliente ou tela “Minha Conta” onde o botão possa
  ser adicionado. Criar um scaffold excederia a autorização atual.

## 6. Correções e ciclos de nova revisão

Nenhum código foi alterado. Para prosseguir, o usuário deve indicar o
repositório/diretório do frontend ou autorizar expressamente a criação de um
cliente.

## 7. Testes e verificações

- Busca de arquivos confirmou ausência de artefatos de frontend.
- Inspeção de `src/api/v1/endpoints/identity/auth.py`, serviço, repositório e
  testes de autenticação confirmou o contrato, ownership e revogação de logout.
- Nenhum teste foi executado, pois não houve modificação.

## 8. Riscos ou trabalho restante

O logout não revoga o access token já emitido; ele expira normalmente. O contrato
atual também não oferece logout de todos os dispositivos.

## 9. Veredito final do orquestrador

**blocked** — a solicitação não pode ser implementada neste repositório sem uma
UI existente ou autorização explícita para criar uma.
