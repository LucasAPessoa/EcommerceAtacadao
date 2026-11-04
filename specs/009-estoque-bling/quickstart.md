# Quickstart: validar a spec 009

## Pré-requisitos
- Testes: env fictícias e Docker descartável (`skills/ecommerce-atacadao/references/development.md`). Bling e MP simulados por fakes.
- Conta real (só com aprovação do usuário): no Bling, a reserva ligada para "Em aberto" ("Considerar situações de vendas") e o app com escopos de **pedidos de venda** e **contatos** (escrita). Depois de mudar os escopos, reconectar o Bling no admin.
- Config: `BLING_ORDER_SITUATION_PAID_ID` e `BLING_ORDER_SITUATION_CANCELED_ID`. Os padrões são 9 e 12; confira os ids da conta com `GET /situacoes/modulos`.

## Cenários automatizados (CI)
| Cenário | Esperado | Spec |
|---|---|---|
| Saldo virtual 10, compra de 3, pagamento aprovado | 1 pedido no Bling; `CREATE`, `MARK_PAID` e `POST_STOCK` `DONE` uma vez cada; disponível 7 em todas as etapas | US1, SC-001 |
| `POST /pedidos/vendas` responde 400 mas cria | O próximo passo é `GET` por `numeroLoja`, que acha o pedido; nunca dois | SC-002 |
| N checkouts disputando K unidades | ≤ K reservas | SC-003 |
| Bling fora do ar (fake 503) por 1 h simulada | O checkout passa; as ações ficam `PENDING` e concluem quando o Bling volta | SC-004 |
| Reserva vencida, Order remota ainda `created` | A reserva **não** é liberada, nem há `CANCEL` no Bling, até o `cancel_order` confirmar | R1 |
| Aprovação depois da expiração, ou sem saldo | Pedido `CANCELED` (`insufficient_stock`), estorno MP e `CANCEL` no Bling, sem `POST_STOCK` | FR-008 |
| Prazo da Order ≠ prazo da reserva | O teste de amarração falha | FR-007 |
| Virtual = físico com pedido Em aberto | A reserva local continua contando; aviso `bling_reserve_not_applied` | FR-013 |

Comandos: os do `.github/workflows/ci.yml` (ruff, mypy, pytest unitário e integração).

## Validação manual (opcional, conta de teste)
1. **Pix x expiração (R1)**: crie uma Order com `expiration_time=PT2M` e abra o `checkout_url` no seu navegador. Gere o Pix e espere 3 min. Rode `POST /v1/orders/{id}/cancel` e depois `GET /v1/orders/{id}`: o pagamento pendente deve vir `canceled`.
2. **Bling (T001)**: crie um pedido Em aberto de 1 unidade, mude para Atendido e lance o estoque. Confira o físico −1 e o virtual −1 (não −2). Depois estorne, cancele e confira que voltou.
