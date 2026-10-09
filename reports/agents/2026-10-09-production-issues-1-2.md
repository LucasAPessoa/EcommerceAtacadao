# Validação de produção — issues #1 e #2

## Objetivo

Publicar as correções e validar em produção a rotação concorrente de refresh token e o Checkout Pro do Mercado Pago.

## Implementação

- A rotação de refresh token passou a usar atualização condicional e transação única.
- Pagamentos aprovados que não conseguem confirmar estoque são registrados para reconciliação operacional.
- O runtime da Vercel recebeu as URLs HTTPS públicas e o segredo do webhook do Mercado Pago.

## Evidências

- Testes locais: 12 testes de refresh token e 29 testes focados de checkout/pagamentos aprovados passaram.
- Produção: duas requisições simultâneas de refresh retornaram exatamente um `200` e um `401`.
- Produção: login, carrinho, endereço, quatro cotações de frete e criação de checkout foram validados; o checkout retornou `201` com `order_id` e URL hospedada do Mercado Pago.

## Resultado

As issues #1 e #2 foram fechadas com comentários concisos de resolução e evidência de validação.
