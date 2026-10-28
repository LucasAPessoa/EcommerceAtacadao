# store-theme-api (back #114)
Branch: feat/114-store-theme

Entregue
- Catálogo de temas: src/services/store/themes.py (`gondola` = "Gôndola"; DEFAULT_THEME).
- Modelo singleton `StoreSettings` (id=1 com CHECK, theme, brand_color, timestamps) + migration a7c3e91b4d20 (após efccebc32a0f). Não aplicada em banco compartilhado.
- Schemas (tema validado contra o catálogo, cor #RRGGBB normalizada para maiúsculas), repositório (upsert atômico ON CONFLICT) e serviço.
- Rotas: GET /api/v1/store/theme (público); GET /admin/store/themes e PUT /admin/store/theme (admin, via admin_router).
- Resposta no envelope BaseResponse: {status, message, data:{theme, brand_color, updated_at}}. Sem registro: updated_at null.
- Testes: tests/admin/test_store_theme.py; rotas adicionadas a tests/admin/test_auth.py; arquivo listado em scripts/run_api_tests.sh.

Checks
- ruff nos arquivos alterados: ok. mypy --explicit-package-bases --warn-unused-ignores src: ok.
- scripts/run_api_tests.sh em Postgres local descartável (já removido): 434 passed.
- Os 33 erros de ruff no repo já existiam na main.

Impacto no front: dados vêm em `data` (envelope padrão), não no topo como o texto da issue sugere.
