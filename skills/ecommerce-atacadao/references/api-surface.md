# Superfície HTTP e autorização

Confirme paths e schemas no router antes de mudar clientes. Este arquivo descreve
as famílias de endpoints e suas políticas, não substitui o OpenAPI gerado.

## Base da aplicação

- API de negócio: `/api/v1`.
- Health check: `/health`.
- Swagger UI: `/api/docs`.
- OpenAPI: path configurado pela aplicação.

## Autenticação

Família `/api/v1/auth`:

- registro;
- login;
- refresh com rotação do token persistido;
- logout com revogação.

Registro e login são públicos. Refresh exige o refresh token correto; endpoints
de negócio autenticados exigem access token. Não aceite role administrativa no
cadastro comum e não retorne tokens ou credenciais em logs/erros.

## Usuário e endereços

As rotas de usuário expõem o perfil do autenticado e as rotas de endereço
permitem listar, criar, atualizar e excluir logicamente endereços pertencentes a
ele.

Sempre aplique a consulta pelo recurso e pelo `user_id`. Para outro proprietário,
prefira a semântica atual que não revele a existência do objeto. Não faça uma
consulta global seguida apenas de uma checagem tardia se isso puder vazar dados.

## Catálogo

Há rotas para as entidades de categoria, produto, variação, imagem, faixa de
preço, avaliação, pergunta e estruturas de listing. Alguns recursos usam o
factory CRUD genérico; produtos também possuem busca especializada por código.

Política:

- leituras de catálogo são públicas;
- criação, alteração e exclusão são administrativas;
- criação de avaliação/pergunta é autenticada conforme a exceção implementada;
- filtros de ativo e soft delete devem permanecer consistentes entre lista,
  detalhe, carrinho e checkout.

No factory genérico, aplique a dependência de autorização antes de executar
validações que consultem ou persistam dados. Um payload inválido não deve permitir
que usuário não autorizado alcance a camada de banco.

## Carrinho e checkout

Família de carrinho sob `/api/v1/cart`:

- obter carrinho atual;
- adicionar item;
- atualizar quantidade;
- remover item;
- limpar carrinho;
- gerar preview do checkout;
- confirmar checkout.

Todas as rotas pertencem ao usuário autenticado. O ID do usuário vem do token,
nunca do corpo. Mutações retornam o estado recarregado do carrinho para evitar
respostas obsoletas após `flush`, agregação ou remoção.

A confirmação exige `Idempotency-Key` e os campos de revisão previstos no schema,
incluindo o total esperado pelo cliente. Consulte [checkout.md](checkout.md) para
o protocolo transacional.

## Pedidos

Família `/api/v1/orders`:

- cliente lista e consulta apenas seus pedidos;
- administrador pode consultar o conjunto administrativo;
- cancelamento direto é restrito ao proprietário/administrador conforme a regra
  implementada e ao estado `awaiting_payment`.

Não exponha criação ou edição genérica de pedido. Pedido nasce do checkout e suas
mudanças passam por transições de domínio, histórico e efeitos de estoque.

## Frete

Há endpoint público para simulação de frete usando dados de destino e itens. O
servidor resolve peso e dimensões a partir do catálogo; não aceite medidas ou
preço de frete fornecidos pelo cliente como verdade.

O checkout recalcula a cotação. A simulação anterior serve à experiência do
usuário, não como autorização de preço. Falha do provedor externo deve manter o
status de indisponibilidade apropriado e uma mensagem sem credenciais ou corpo
sensível do provedor.

## Matriz resumida

| Área | Público | Usuário autenticado | Admin |
| --- | --- | --- | --- |
| Health e documentação | Sim | Sim | Sim |
| Registro/login/refresh | Conforme operação | Conforme token | Conforme token |
| Leitura do catálogo | Sim | Sim | Sim |
| Escrita do catálogo | Não | Pergunta/avaliação | Sim |
| Cotação de frete | Sim | Sim | Sim |
| Carrinho/checkout | Não | Apenas próprio | Como usuário, salvo rota explícita |
| Pedidos | Não | Apenas próprios | Visão administrativa |
| Perfil/endereços | Não | Apenas próprios | Sem acesso implícito |

Administração não elimina ownership automaticamente. Só amplie acesso quando a
rota e a regra de negócio declararem isso explicitamente.
