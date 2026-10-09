# Domínios e escopo funcional

## Identidade

Entidades principais: `Role`, `User`, `RefreshToken` e `Address`.

Capacidades implementadas:

- cadastro e autenticação por e-mail/senha;
- access token curto e refresh token persistido;
- rotação e revogação de refresh token no refresh/logout;
- roles canônicas `admin` e `user`;
- perfil e endereços vinculados ao proprietário;
- soft delete de endereço conforme o modelo atual.

Invariantes:

- hash de senha nunca sai em schema de resposta;
- refresh token não autentica endpoints protegidos por access token;
- token revogado, expirado ou de outro usuário não pode ser reutilizado;
- cadastro comum recebe role `user`; elevação para `admin` não vem do payload;
- operações de perfil/endereço verificam ownership antes de revelar o recurso.

## Catálogo

Entidades: `Category`, `Product`, `ProductVariant`, `ProductImage`,
`PricingTier`, `ProductReview`, `ProductQuestion`, `ProductListing`,
`ListingAttribute` e `ListingImage`.

Capacidades implementadas:

- leitura pública de categorias, produtos, variações, imagens e preços;
- busca de produto por código conforme a rota especial existente;
- faixas de preço atacadista por quantidade;
- estruturas para avaliações e perguntas de produto;
- estruturas de anúncio e atributos/imagens de marketplace.

Política de escrita:

- mutações de catálogo são administrativas;
- criação de pergunta e avaliação é autenticada e representa a exceção atual;
- produto, variação e categoria inativos ou excluídos não podem entrar no fluxo
  de compra, mesmo que um ID válido seja informado.

Preço por faixa deve selecionar deterministicamente a melhor faixa aplicável à
quantidade consolidada do SKU. A quantidade consolidada importa: duas inclusões
do mesmo SKU no carrinho são uma linha comercial, não dois preços independentes.

## Vendas

Entidades: `Cart`, `CartItem`, `Coupon`, `Order`, `OrderItem`,
`StockReservation` e `OrderStatusHistory`.

Capacidades implementadas:

- um carrinho persistente isolado por usuário;
- inclusão que agrega quantidade de SKU repetido;
- atualização, remoção e limpeza com estado fresco na resposta;
- cupom validado pelo servidor;
- checkout em preview e confirmação;
- pedido e itens como snapshot do momento da compra;
- reserva temporária de estoque;
- histórico de transições de status;
- listagem/leitura por proprietário e visão administrativa;
- cancelamento direto somente enquanto aguarda pagamento.

Estados, transições e valores válidos devem vir dos enums e services existentes,
não de strings inventadas. O fato de um status existir no enum não autoriza toda
transição entre pares.

As opções de pagamento modelam Pix, cartão e boleto, incluindo parcelas quando
aplicável. O Mercado Pago usa Checkout Pro hospedado: o cliente envia somente a
revisão comercial, a API cria uma Order no provedor e o webhook assinado consulta
o estado autoritativo antes de alterar a transação local. Aprovação sem reserva
confirmável, aprovação tardia de pedido cancelado e estornos entram na
reconciliação durável; não devem promover o pedido diretamente para pago.

## Operações e integrações

### Implementado

- cotação pública de frete pelo Melhor Envio;
- montagem do pacote a partir de peso e dimensões das variações;
- nova cotação no checkout, sem confiar no valor exibido anteriormente ao
  cliente.

### Modelado, mas sem fluxo completo

- `Refund`;
- `Shipment`;
- `LocalCEPRange`;
- `ERPWebhookLog`.

A presença desses models, migrações ou seeds não equivale a uma capacidade
operacional completa. Exija router, service, repository/integração e testes antes
de considerar o recurso entregue.

## Escopo futuro declarado

- sincronização bidirecional e webhooks reais do Bling;
- cobrança, callback, reconciliação, estorno e chargeback do Mercado Pago;
- logística regional por CEP, Loggi/Correios diretos, etiqueta e coleta;
- administração de remessas, reembolsos e nota fiscal;
- frontend de cliente e painel administrativo;
- workers, filas, tarefas agendadas e observabilidade de produção.

## Cobertura de dados

O seed determinístico atual recria o conjunto de entidades do projeto e seus
enums para testes e exploração local. Ele demonstra relacionamentos e cenários,
mas não substitui testes de todas as transições, concorrência, expiração,
autorização e falhas externas. Ao adicionar uma entidade ou enum, atualize seed,
reset, migrações e testes coerentemente.
