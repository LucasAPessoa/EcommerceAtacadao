# Issue #4 — autoria e moderação de avaliações e perguntas

## Objetivo e critérios
- O cliente não pode escolher outro autor, aprovar a própria avaliação nem criar uma resposta privilegiada.
- A issue também pede testes de spoofing e de visibilidade.

## Agentes (perfis `atacadao-*`)
- api (sonnet), ciclo 1: autoria e moderação. Reviewer: `changes_required` (visibilidade).
- api (o mesmo agente, retomado), ciclo 2: visibilidade. Reviewer (o mesmo, retomado): `approved`.
- Orquestrador:
  - comparou ruff e mypy com o HEAD;
  - ajustou o `front_atacadao` AdminPage (2 linhas);
  - não usou o tester, porque os comandos eram poucos.

## Decisões de contrato
- `POST /catalog/product-reviews/` aceita `product_id`, `rating` e `comment?`. `POST /catalog/product-questions/` aceita `product_id` e `question_text`.
- Os campos `user_id`, `is_approved` e `answer_text` dão 422 (`extra="forbid"`), inclusive para admin.
- O autor vem sempre do token. A review nasce não aprovada e a question nasce sem resposta.
- A moderação continua no PATCH, só para admin, com contrato inalterado.
- O GET de reviews usa auth opcional (`get_optional_current_user`):
  - anônimo ou `user` vê só as aprovadas; pendente dá 404 no GET por id;
  - admin vê tudo;
  - token inválido é tratado como anônimo, nunca como 401;
  - o filtro está na query SQL, antes da paginação.

## Arquivos
- `src/core/sec.py`, `src/api/v1/endpoints/catalog/{_crud_factory,product_reviews,product_questions}.py`.
- Schemas, services e `product_review_repository.py` de review e question.
- Testes: `tests/catalog/test_review_question_authorship_unit.py` (14).
- Front: `front_atacadao/src/features/admin/AdminPage.tsx`, exemplos de create.

## Testes
- 62 testes unitários (catalog authorship, core, main, checkout, Mercado Pago): ok. `npm run build` no front: ok.
- Em relação ao HEAD, o ruff caiu de 14 para 6 avisos (E501 antigos). O mypy ficou igual (9 em `_crud_factory.py`, 1 em `sec.py:75`).

## Riscos e pendências
- Se um CDN ou proxy de cache entrar na frente da API, os GETs de reviews precisam de `Vary: Authorization` ou `Cache-Control: private`.
- `ProductReview.is_approved` tem default True no model; o seed e criações fora do service nascem aprovados.
- O `user_id` aparece no GET público de reviews aprovadas.
- O `limit` não tem teto (é a issue #9).

## Veredito
approved.
