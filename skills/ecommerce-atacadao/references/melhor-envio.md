# Melhor Envio — fatos da API de cotação

Levantamento da #62 (parte de cotação da #50). Etiqueta, NF-e e rastreio ainda
estão pendentes na #50 e serão tratados na #63. Cada fato traz a origem: doc
oficial, blog do Melhor Envio ou spike no sandbox (2026-11-05).

## Cotação: `POST /api/v2/me/shipment/calculate`

- Fonte: https://docs.melhorenvio.com.br/reference/calculo-de-fretes-por-produtos
- Corpo: `from.postal_code`, `to.postal_code` e `products[]` com `id`, `width`,
  `height`, `length` (cm), `weight` (kg), `quantity` e `insurance_value`. A API
  multiplica `insurance_value` por `quantity`. Alternativa: `volumes[]`.
- Resposta: lista de serviços. Cada um traz `id`, `name`, `price`, `custom_price`,
  `discount`, `delivery_time`, `custom_delivery_time`, `delivery_range`
  `{min,max}`, `company{id,name,picture}`, `additional_services` e `packages[]`.
- Valores monetários e pesos vêm como **string** (`"360.02"`, `"30.00"`), e
  prazos vêm como inteiro (spike).
- Cada item de `packages[]` traz `price`, `discount`, `format`, `dimensions`
  `{height,width,length}`, `weight`, `insurance_value` e `products[{id,quantity}]`.
  O `id` é o mesmo enviado em `products[].id`, então mande o id da variação
  (spike).
- Serviço recusado volta na mesma lista com `error` (texto) e `price` nulo, com
  HTTP 200. Exemplos do spike: "Peso ultrapassa o limite máximo de 30,00kg." e
  "Dimensões do objeto ultrapassam o limite da transportadora."
- O limite de peso vale **por pacote**, não por pedido: 4 × 10 kg no PAC virou 2
  pacotes (30 kg + 10 kg) e foi cotado; 1 volume de 40 kg foi recusado no PAC e
  aceito na Jadlog (spike).
- `custom_price` e `custom_delivery_time` incluem acréscimos e prazo extra do
  painel do ME. O projeto usa `price` + a margem do deploy
  (`STORE_SHIPPING_MARGIN_PERCENT`), para não somar duas margens (decisão de
  2026-11-05).

## Etiqueta (para a #63)

- Fonte: https://docs.melhorenvio.com.br/reference/inserir-fretes-no-carrinho
- Os `volumes` do `POST /me/cart` são os `packages` da cotação. Correios, J&T e
  Loggi aceitam um volume por envio, então n pacotes viram n inserções. Por isso
  o pedido guarda `orders.shipping_quote_snapshot` com os `packages`.
- `options.insurance_value` "geralmente corresponde à somatória dos valores dos
  produtos". Envio comercial exige `options.invoice.key` (NF-e).

## Limites por transportadora (blog do ME, não é doc da API)

- Correios PAC/SEDEX e Loggi: 30 kg. Jadlog: até 120 kg. LATAM Cargo: 200 kg
  (100 kg por volume). Buslog: 50 kg. Azul Cargo: as fontes divergem.

## Sandbox

- `https://sandbox.melhorenvio.com.br`, contas separadas da produção, só Correios
  e Jadlog (Mini Envios aparece, mas recusa caixas grandes). O `User-Agent` com
  nome da app e email é obrigatório.
- Latência observada no spike: de 0,9 s a 1,4 s por cotação.
