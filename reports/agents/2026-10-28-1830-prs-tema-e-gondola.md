# PRs do tema da loja (back #114) e da nova interface Gôndola (front) — 2026-10-28

## Entregue
- Back #114 dividida pelo migration gate: #117 (migration `a7c3e91b4d20` + model; **mergeado** `5712498`) e #118 (rotas `/store/theme` e `/admin/store/theme`; **mergeado** `58e5200`).
- Front empilhado: #69 fundação (**mergeado**, Closes #62), #70 telas da loja (**mergeado**), #71 Aparência (**mergeado** `68c38d3`, Closes #68).
- Reviewer `atacadao-reviewer`: approved nos 4 (back #117+#118, front #69, #70, #71). P2 do #69 corrigido por mim (`styles.css:1583` `--font-sans` → `--font-body`; README com `#1D6B57`).
- Verificação: back 434 unit, ruff/mypy no escopo do CI, `alembic check`; front 215/223/236 testes, Biome, tsc, build, isolamento; CI do GitHub verde em todos os merges.

## Incidente evitado
Ao separar a `feat/114`, o `checkout` por diff trouxe versões antigas de 4 arquivos do #116 (Mercado Pago). Corrigido antes do push; o diff do #118 contra a main ficou idêntico ao da branch original.

## Desfecho
`Migrate production` disparado e aprovado pelo agente a pedido explícito do usuário (run 40738128645, registro `a7c3e91b4d20`). Rerun do Migration gate do #118 → verde → merge `58e5200`; `/store/theme` 200 em produção; merge do front #71 `68c38d3`. Fechadas: back #114, front #62 e #68.

## P3 dos reviewers (não bloqueiam)
- Back: `created_at/updated_at` sem `server_default` na migration; `utcnow()` sem fuso.
- Front: cor da resposta de `/store/theme` sem validação antes do cache; `theme` guardado sem uso (um tema só); `packPlural` gera "500gs"; "+" do carrinho sem limite de estoque no cliente; foco vai ao body após "Dispensar"; CTA sem "estimado"; carregando sem `aria-busy`.

## Issues publicadas
Back #119–#121; front #72–#79; comentários em front #36, #38, #64, #67 e links cruzados; fechadas front #39 e #8.
