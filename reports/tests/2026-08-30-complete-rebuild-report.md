# Reconstrução completa e suíte sem skips — 30/08/2026

## Resultado

O banco local `ecommerce_atacadao` foi limpo, reconstruído pelas migrações e
populado novamente. Após ampliar a cobertura do checkout, a execução final foi:

| Resultado | Quantidade |
|---|---:|
| Testes coletados | 115 |
| Aprovados | 115 |
| Falhas | 0 |
| Erros | 0 |
| Ignorados | 0 |
| Duração | 28,74 s |

O JUnit final está em `reports/tests/pytest-results-complete.xml`.

## Reconstrução do banco

O downgrade histórico do Alembic não conseguiu remover uma constraint antiga
sem nome. Para tornar a operação segura e reproduzível, foi criado
`scripts/reset_database.py`, que:

- exige confirmação explícita com `--yes`;
- aceita somente banco local por padrão;
- remove e recria apenas o schema `public` do banco configurado;
- não imprime senha ou credenciais.

Fluxo executado:

```bash
uv run python -m scripts.reset_database --yes
uv run alembic upgrade head
uv run python -m scripts.seed
```

As quatro migrações foram aplicadas do zero até `31a9c6e2f4b8` (`head`).

## Cobertura do dataset

O seed passou a criar e validar pelo menos um registro para cada uma das 26
entidades concretas:

- identidade: roles, usuários, refresh tokens e endereços;
- catálogo: categorias, produtos, variações, imagens, faixas de preço,
  avaliações, perguntas, listings, atributos e imagens de listing;
- vendas: cupons, carrinhos, itens, pedidos, itens de pedido, reservas e
  histórico de status;
- operações: transações, reembolsos, faixas locais de CEP, remessas e logs de
  webhook ERP.

Também são validados todos os valores dos oito enums:

- tipos de usuário: `INDIVIDUAL`, `COMPANY`, `ADMIN`;
- status de pedido: `PENDING_PAYMENT`, `PAID`, `PROCESSING`, `SHIPPED`,
  `DELIVERED`, `CANCELED`, `EXPIRED`;
- pagamentos: `PIX`, `CREDIT_CARD`, `BOLETO`;
- status de transação: `PENDING`, `PROCESSING`, `APPROVED`, `REJECTED`,
  `CANCELED`, `REFUNDED`, `PARTIALLY_REFUNDED`, `CHARGEBACK`;
- reservas: `ACTIVE`, `CONFIRMED`, `RELEASED`, `EXPIRED`;
- reembolsos: `REQUESTED`, `APPROVED`, `REJECTED`, `COMPLETED`;
- remessas: `PREPARING`, `SHIPPED`, `DELIVERED`, `RETURNED`;
- descontos: `PERCENTAGE`, `FIXED_AMOUNT`, `FREE_SHIPPING`.

O seed aborta e faz rollback se qualquer entidade ou valor de enum estiver
ausente. Valores monetários são normalizados com `Decimal` e snapshots de
pedido preservam preço, SKU, nome, variação e dimensões logísticas.

## Cobertura do checkout transacional

Foram acrescentados testes para:

- confirmação atômica do pedido e limpeza do carrinho;
- replay seguro pela mesma chave de idempotência;
- bloqueio por estoque já reservado;
- aplicação da maior faixa de preço atacadista;
- Pix e boleto em uma parcela;
- cartão de crédito à vista e parcelado;
- desconto percentual, valor fixo e frete grátis;
- rejeição de parcelamento incompatível;
- autenticação, autorização, isolamento entre usuários e imutabilidade direta
  dos itens de pedido.

## Ajustes descobertos pelo banco limpo

- O cadastro buscava a role inexistente `customer`; agora utiliza a role
  canônica `user`, reconhecida pelas dependências de autorização.
- O seed misturava `float` e `Decimal` antes do primeiro reload do ORM; todo
  cálculo monetário do pedido agora é explicitamente decimal.
- O seed acessava relacionamento lazy em sessão assíncrona; o snapshot do nome
  do produto agora é obtido por consulta assíncrona explícita.
- Todos os `pytest.skip` foram removidos. Pré-condições ausentes agora causam
  falha clara, em vez de reduzir silenciosamente a cobertura.

## Estado final

Após a suíte, o seed idempotente foi executado novamente. O banco ficou
validado e pronto, com todas as entidades e valores de enum representados.
