# Validação ao vivo — Mercado Pago sandbox

## Objetivo e escopo

Validar os caminhos mais prováveis da integração Mercado Pago com as credenciais
de teste e túneis HTTPS fornecidos pelo operador, sem submeter pagamento real e
sem registrar segredos.

## Critérios

- credenciais e URLs de ambiente presentes;
- API e webhook publicamente alcançáveis;
- Access Token aceito pelo Mercado Pago;
- criação e consulta de Order real de sandbox;
- validação de assinatura HMAC na rota pública de webhook;
- revisão de regressão do payload alterado.

## Resultados

| Cenário | Resultado |
| --- | --- |
| Configuração local do Mercado Pago | Passou: token e secret presentes; URLs de callback configuradas. |
| `GET /users/me` do Mercado Pago | Passou (HTTP 200); o token de teste é válido. |
| API local `/health` | Passou (HTTP 200). |
| Webhook por túnel ngrok | Passou: payload propositalmente inválido chegou e foi rejeitado por schema (HTTP 422). |
| Criação real de Order sandbox | Passou após correção do payload; status remoto `created`. |
| Consulta da Order criada | Passou; o ID retornado coincidiu com o ID consultado. |
| Allowlist de `checkout_url` | Passou; a URL retornada pertence ao domínio HTTPS oficial. |
| Assinatura HMAC pública | Passou: um evento assinado corretamente foi aceito antes de ser recusado por não possuir transação local correspondente. |
| Preview da loja | Bloqueado por HTTP 502 na cotação do Melhor Envio. Nenhum pedido local ou reserva foi criado. |

## Correções encontradas pela validação real

A primeira chamada real a `POST /v1/orders` retornou 400. A resposta do
Mercado Pago identificou propriedades não suportadas pela Orders API ativa:

1. `config.notification_url`;
2. `items[].total_amount` e `items[].unit_measure`.

Foi removido `notification_url` do payload. A URL de notificação continua
configurada no painel de Webhooks do Mercado Pago, que é o canal suportado para
Checkout Pro/Orders. Os itens agora enviam somente `title`, `quantity` e
`unit_price`; o valor total da Order permanece conferido pela soma dos itens.

Arquivos alterados:

- `src/services/sales/mercado_pago_service.py`;
- `tests/sales/test_mercado_pago_unit.py`.

## Verificações

- `uv run pytest -q tests/sales/test_mercado_pago_unit.py` — 12 passaram.
- `uv run pytest -q tests/sales/test_mercado_pago_unit.py tests/sales/test_checkout_unit.py` — 25 passaram.
- `uv run ruff check src/services/sales/mercado_pago_service.py tests/sales/test_mercado_pago_unit.py` — passou.
- `git diff --check` — passou.

## Ambiente temporário de teste

- API local: porta 8000, exposta pelo túnel HTTPS de ngrok usado no `.env`.
- Frontend local: porta 5173, exposto por um túnel HTTPS temporário separado.
- O processo da API foi iniciado com uma substituição de ambiente para a URL
  HTTPS temporária do frontend e a origem CORS do túnel; o `.env` não foi
  regravado.
- O processo do frontend usa temporariamente `VITE_API_BASE_URL` apontando para
  a URL HTTPS do ngrok. A resposta da API confirmou o CORS para essa origem.

## Riscos e próximos passos

- A criação completa de pedido pela UI segue bloqueada até corrigir/configurar a
  cotação do Melhor Envio que respondeu 502.
- Não foi feito pagamento aprovado, recusado ou pendente no formulário hospedado
  porque o teste end-to-end requer uma conta compradora de teste cujo e-mail
  também esteja cadastrado como usuário local.
- Os túneis são temporários; suas URLs deixam de valer quando os processos
  forem encerrados. Para o teste corrente, a URL HTTPS do frontend precisa ser
  a do túnel ativo, e não `http://localhost:5173`.
- O fluxo foi revisado diretamente pelo orquestrador porque os subagentes deste
  runtime não estavam disponíveis para reativação; não houve alteração de
  frontend nem migration.

## Veredito

`changes_required` para o E2E completo da loja devido ao 502 de frete. A
integração Mercado Pago isolada está validada no sandbox para credencial,
criação/consulta de Order e assinatura de webhook.

## Segunda rodada de validação

Após a configuração do Melhor Envio e a disponibilização da conta compradora de
teste, a cotação direta retornou cinco opções e o preview da loja retornou quatro
opções. A tentativa de criar o checkout HTTP da loja revelou que o banco ainda
estava na revisão `a12f4ce980bd`: o enum `paymentmethodenum` não continha
`MERCADO_PAGO`.

A aplicação da migration revelou outro defeito: em bancos em que o schema havia
sido criado por metadata/seed, os tipos de reconciliação já existiam e a criação
da tabela tentava criá-los outra vez. A migration foi corrigida com
`create_type=False`, aplicada com sucesso e o banco ficou em
`6c2d9f8a7b11 (head)`.

Com a migration aplicada, o fluxo HTTP completo até a tela hospedada passou:

- preview do carrinho: HTTP 200;
- criação local + Order Mercado Pago: HTTP 201;
- URL hospedada oficial retornada;
- pedido de teste cancelado localmente após a verificação, liberando a reserva
  de estoque (HTTP 200, estado `CANCELED`).

Não houve pagamento ou dado de cartão. O ambiente de automação não tinha uma
superfície de navegador disponível para autenticar a conta compradora no checkout
hospedado. Assim, aprovação, recusa, pendência e webhook emitido pelo próprio
Mercado Pago continuam como validação manual pendente.

Verificações adicionais: 25 testes unitários/focados passaram, Ruff nos arquivos
alterados passou e `git diff --check` passou.
