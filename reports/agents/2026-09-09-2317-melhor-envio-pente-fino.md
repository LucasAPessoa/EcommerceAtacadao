# Integração Melhor Envio e pente fino

## 1. Objetivo e escopo

Concluir a integração de cotação do Melhor Envio e revisar a aplicação usando
`IDEA.md` como referência, com foco em frete, checkout, segurança do navegador e
preço atacadista. O escopo abrange `src/` e testes relacionados; não inclui
chamadas reais ao provedor, migrações, reset de banco, deploy ou commits.

## 2. Critérios de aceite

- Falhas do provedor não expõem payload, credenciais, configuração ou detalhes
  internos.
- CEP, catálogo ativo, dados logísticos e valores monetários são validados antes
  da cotação.
- Preview e confirmação preservam a consistência entre cotação, endereço,
  produto, frete e checkout transacional.
- O carrinho mostra o preço atacadista aplicável à quantidade consolidada.
- CORS não permite origens arbitrárias em requisições com credenciais.
- Testes focados e validações estáticas passam; revisão independente aprova o
  diff.

## 3. Resumo de cada agente

- `ecommerce_frontend`: analisou a jornada catálogo -> carrinho -> cotação ->
  preview -> confirmação -> pedido. Não editou arquivos porque não há frontend.
  Identificou o vazamento do provedor, fallback logístico, catálogo inativo,
  descompasso de cotação, CORS e preço atacadista como riscos.
- `ecommerce_api`: removeu o vazamento, tornou a cotação segura e validada,
  protegeu o checkout contra mudanças concorrentes de produto e endereço,
  introduziu CORS por allowlist e centralizou preço atacadista reutilizado pelo
  carrinho e checkout. Incluiu testes unitários focados.
- `ecommerce_reviewer`: encontrou a corrida entre cotação e atualização de
  endereço, além de CORS e preço do carrinho. Após as correções e nova inspeção,
  aprovou o diff.

## 4. Decisões de contrato

- `POST /operations/shipping/calculate` normaliza CEP para oito dígitos. SKU
  indisponível, logística inválida ou ausência de opção retorna `422`; falha do
  Melhor Envio retorna `502` com mensagem estável e segura.
- No checkout, alterações de endereço, preço aplicado, quantidade ou dados
  logísticos entre cotação e seção bloqueada exigem nova revisão; não criam
  pedido parcial.
- `CORS_ALLOWED_ORIGINS` aceita lista separada por vírgulas. O padrão vazio
  permite apenas chamadas same-origin e `*` é descartado.
- A faixa atacadista é calculada pela quantidade consolidada do produto e é
  compartilhada pelo carrinho e checkout.

## 5. Achados do revisor por prioridade

- P1 corrigido: `CheckoutService.confirm` poderia cotar pelo CEP anterior e
  persistir snapshot de endereço atualizado concorrentemente.
- P1 corrigido: CORS aceitava qualquer origem com credenciais.
- P2 corrigido: `CartResponseSchema.total_amount` usava preço-base e podia
  divergir do preview/checkout.
- P2 resolvido por evidência: os testes HTTP com `TestClient` não falhavam; o
  timeout observado pelo revisor era efeito do sandbox/cache. A execução final
  concluiu normalmente.

## 6. Correções e ciclos de nova revisão

O primeiro ciclo corrigiu exposição de `response.text`, dados logísticos
inventados, CEP, catálogo inativo, `Decimal` e alterações concorrentes de
produto. A revisão exigiu uma segunda correção para o endereço concorrente e
status de falhas públicas. No terceiro ciclo, CORS e preço atacadista do
carrinho foram corrigidos. A revisão final emitiu `approved`.

## 7. Testes e verificações

- `uv run pytest tests/operations/test_shipping_unit.py
  tests/sales/test_checkout_unit.py tests/sales/test_cart_unit.py
  tests/test_main_unit.py -q`: **24 passed**.
- `uv run ruff check` nos arquivos de produção e testes alterados: passou.
- `git diff --check`: passou.

Foram emitidos avisos de deprecação do `TestClient`/Starlette e de schemas
Pydantic legados; não bloquearam a suíte e não foram ampliados neste escopo.
Ruff amplo ainda encontra problemas preexistentes fora dos arquivos alterados.

## 8. Riscos ou trabalho restante

Não houve cotação contra o Melhor Envio real, deliberadamente: não foram usadas
credenciais nem feita mutação externa. A allowlist CORS precisa receber as
origens reais no ambiente de implantação. Pagamento, etiquetas/coleta, ERP,
entrega regional e frontend continuam fora do escopo já declarado do projeto.

## 9. Veredito final do orquestrador

**approved**. A integração de cotação e os achados acionáveis do pente fino
foram corrigidos, validados e aprovados em revisão independente.
