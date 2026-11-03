# Revisão UX/design completa — loja e admin (2026-10-28)

Base: front `feat/68-admin-aparencia`, back `feat/114-store-theme`. Stack local descartável (pg 55433, API 8001, Vite 5173).
Agentes: atacadao-api (stack + fluxos HTTP), 5× atacadao-ux (loja descoberta, loja restante, carrinho/conta/auth, admin A, admin B), atacadao-designer (vs. Gôndola).
Capturas: 27 telas × 2 larguras (1366/360) via Playwright; só `adm/produtos/:id` mobile rola na horizontal (276px); zero erro de console.

## Veredito
changes_required em todos os grupos; nenhum P0. Loja: desvio leve da Gôndola. Admin: desvio forte (não usa o Sistema).

## Principais P1
- Faixa de preço por produto aplicada a qualquer embalagem (Saca 25kg a R$ 25,90) — back #91 + par no front.
- "a unidade" exibido para embalagem; adicionar ao carrinho sem retorno — front #36.
- Busca só no cliente (limit=100), nav por <button>, header fora de sincronia — front #67; back sem `q`/`meta`.
- Carrinho: pagamento desabilitado sem explicação; quantidade só por −/+.
- Admin mobile: `.adm-stack` sem coluna, `@media .adm-dl` anulado, menu sobre a topbar, tabelas cortadas.
- Admin pedidos: filtro de status em fieldset alto; diálogo "Cancelar/Confirmar" ambíguo.
- Admin Bling: hierarquia de CTA e "Importar" habilitado sem conexão.
- Back: carrinho aceita quantidade acima do estoque; 500 na fila de conciliação (#110); erros em inglês e "che.".

## Decisões propostas (aguardando aprovação do usuário; nada publicado)
- Fechar no merge da feat/68: front #62, #68, #39, #8.
- Comentar escopo: front #36, #64, #67, #38.
- Criar: front F1–F8, back B1–B3.
- Rascunhos: scratchpad `rascunhos-issues.md` da sessão.

## Não verificado
Foco/teclado e leitor de tela; retorno de pagamento com pedido real (MP externo); cotação de frete real (Melhor Envio fictício → 502).

## Stack
Derrubar: `pkill -f "uvicorn src.main:app --host 127.0.0.1 --port 8001"; docker rm -f ux-review-pg ux-review-redis`; Vite em 5173.
