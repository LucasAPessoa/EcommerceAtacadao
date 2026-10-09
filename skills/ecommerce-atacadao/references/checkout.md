# Checkout transacional

O checkout é o limite de segurança mais importante do projeto. Ele converte um
carrinho mutável em pedido, itens e reservas imutáveis sem confiar em valores
comerciais enviados pelo cliente.

## Autoridade do servidor

O cliente pode informar intenção e confirmar o total que viu, mas não define:

- usuário do pedido;
- itens, quantidades ou SKUs fora do carrinho persistido;
- preço unitário, faixa atacadista, subtotal ou desconto;
- disponibilidade de estoque;
- custo final de frete;
- estado inicial do pedido ou da reserva.

Use `Decimal` em todo cálculo e aplique arredondamento monetário de forma
explícita e consistente com os schemas/models existentes.

## Preview

O preview é informativo e não reserva estoque. O fluxo deve:

1. carregar o carrinho do autenticado e rejeitar carrinho vazio;
2. consolidar linhas por SKU;
3. validar novamente produto e variação ativos e não excluídos;
4. selecionar a faixa de preço aplicável à quantidade consolidada;
5. validar cupom e calcular desconto no servidor;
6. cotar frete com dados logísticos persistidos;
7. devolver itens, subtotais, descontos, frete e total calculados.

O preview pode ficar obsoleto por estoque, catálogo, cupom ou frete. A confirmação
sempre recalcula.

## Confirmação

Mantenha uma única sessão e uma única unidade transacional:

1. autentique o usuário e valide `Idempotency-Key`;
2. procure replay concluído pela chave vinculada ao usuário;
3. bloqueie o carrinho/linhas relevantes;
4. consolide SKUs e adquira locks de estoque em ordem determinística;
5. revalide produto, variação, quantidade e faixas de preço;
6. desconte reservas ativas e não expiradas da disponibilidade;
7. revalide cupom e recalcule o frete;
8. compare o total calculado com `expected_total_amount` e exija nova revisão se
   houver divergência;
9. crie pedido, snapshots dos itens, histórico e reservas temporárias;
10. esvazie/finalize o carrinho conforme o fluxo atual;
11. faça um único commit e devolva o pedido persistido.

Em falha, execute rollback de toda a unidade. Não deixe pedido sem itens, reserva
sem pedido, carrinho parcialmente limpo ou chave idempotente presa em estado
incorreto.

Não mantenha locks de banco durante chamada externa lenta. Faça a cotação antes
da seção crítica quando possível e valide novamente qualquer premissa que possa
mudar antes do commit. Se o desenho exigir chamada externa dentro da unidade,
reavalie a fronteira em vez de simplesmente alongar a transação.

## Idempotência

A chave é escopada por usuário. Repetir a mesma confirmação deve retornar o
resultado original, sem criar outro pedido, debitar estoque novamente ou duplicar
histórico/reservas. A mesma chave de outro usuário não compartilha o resultado.

Defina comportamento explícito para tentativa anterior em processamento ou que
falhou. Constraints de banco complementam, mas não substituem, a coordenação do
service.

## Estoque e reservas

- Locks devem ser adquiridos em ordem estável para reduzir deadlocks.
- Disponível = estoque persistido menos reservas ativas e não expiradas, conforme
  a regra implementada.
- Quantidade precisa permanecer positiva e respeitar limites do schema/domínio.
- Expiração ou cancelamento deve liberar a reserva exatamente uma vez.
- Cancelar pedido aguardando pagamento registra histórico e desfaz efeitos de
  estoque/reserva na mesma unidade transacional.

Pedidos pagos ou em processamento não podem usar o cancelamento simples de
`awaiting_payment`; exigem fluxo de estorno/reembolso ainda não completo.

## Snapshot comercial

O item do pedido conserva os dados necessários para auditoria mesmo que produto,
SKU, imagem ou preço mudem depois. Não reconstrua histórico comercial consultando
o catálogo atual.

O snapshot deve refletir quantidade, preço unitário aplicado, subtotal e os
identificadores/textos já previstos no model. Frete, desconto e total ficam no
pedido com a precisão do banco.

## Pagamento

Valide método e parcelas no servidor. Parcelamento só se aplica aos métodos e
limites permitidos. No estado atual, criar o pedido não significa que o Mercado
Pago cobrou ou confirmou o pagamento. Não marque como pago sem callback ou fluxo
confiável correspondente.

No Checkout Pro hospedado, o navegador envia somente a revisão comercial: o
provedor escolhe e confirma o meio, parcelas e todos os dados de pagamento.
Se fundos forem aprovados mas a reserva não puder ser confirmada, registre uma
reconciliação durável e não apresente o pedido como pronto para fulfillment. A
solicitação de estorno é distinta do estorno confirmado pelo provedor.

## Testes mínimos por alteração

Selecione os casos afetados, incluindo quando relevante:

- carrinho vazio, SKU inativo/excluído e quantidade inválida;
- preço varejo e cada limite de faixa atacadista;
- cupom válido, inválido, expirado e limites de uso/valor;
- mudança de total entre preview e confirmação;
- estoque suficiente, insuficiente e reduzido por reserva ativa;
- replay da mesma chave e mesma chave usada por outro usuário;
- duas confirmações concorrentes para o último estoque;
- rollback causado após criação parcial;
- falha/indisponibilidade da cotação;
- isolamento entre proprietários;
- cancelamento permitido e transições recusadas.

Não ignore cenário por falta de seed. Monte fixtures determinísticas e verifique
estado do banco antes e depois da operação.
