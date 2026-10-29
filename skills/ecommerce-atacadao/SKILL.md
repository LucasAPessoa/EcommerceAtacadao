---
name: ecommerce-atacadao
description: Desenvolver, revisar, testar e operar o backend EcommerceAtacadao em tarefas de identidade, catálogo, frete, carrinho, checkout, pedidos, banco ou integrações. Use apenas neste repositório; não trate funcionalidades planejadas como implementadas.
metadata:
  short-description: Engenharia segura do backend EcommerceAtacadao
---

# EcommerceAtacadao

Preserve as regras comerciais e transacionais deste backend atacadista enquanto
implementa, diagnostica, revisa ou valida mudanças.

## Roteamento de contexto

Leia somente as referências necessárias, sempre por completo:

- Mudanças de camadas, contratos, configuração, erros ou persistência: leia
  [architecture.md](references/architecture.md).
- Regras de identidade, catálogo, operações, vendas, entidades ou estados: leia
  [domains.md](references/domains.md).
- Endpoints, paths, autenticação ou autorização: leia
  [api-surface.md](references/api-surface.md).
- Carrinho, preço atacadista, frete no pedido, estoque, pagamento ou pedido: leia
  [checkout.md](references/checkout.md) além da referência do domínio afetado.
- Setup, migrações, seed, reset, testes, relatórios ou commits: leia
  [development.md](references/development.md).

Para tarefas transversais, combine as referências relevantes. Não leia todas por
padrão.

## Forma de trabalhar

1. Confirme o estado real no código e no Git. Use a skill como mapa, não como
   substituto da inspeção dos arquivos afetados.
2. Classifique a capacidade como implementada, parcialmente modelada ou futura.
   Não invente endpoints ou integrações porque existe uma tabela correspondente.
3. Mantenha o fluxo `router -> service -> repository -> banco/integração`:
   routers traduzem HTTP, services aplicam negócio, repositories concentram I/O.
4. Modele a alteração no contrato Pydantic e nas regras de domínio antes de
   persistir. Para mudanças em models, crie e revise uma migração Alembic.
5. Teste primeiro a unidade de negócio frágil e depois o contrato HTTP. Em fluxos
   de compra, valide também concorrência, replay, rollback e isolamento de dono.
6. Entregue o resultado com limites conhecidos.

## Estado do produto

Implementado: API em `/api/v1` (docs em `/api/docs`, `/health`); JWT com access e
refresh separados; catálogo público (mutações só de admin, exceto perguntas e
avaliações autenticadas); carrinho por usuário; frete pelo Melhor Envio; checkout
`preview`/`confirm` com Mercado Pago; pedidos por proprietário; conexão e
importação do catálogo Bling; portal admin em `/api/v1/admin/*` (spec 007:
dashboard, produtos, pedidos, moderação, Bling); camada de apresentação por
produto que a sync do Bling não sobrescreve; tema da loja em `/api/v1/store/theme`.

Em implementação (spec 008, back #128): o site é a loja do tipo "API" no Bling;
só produtos vinculados a ela aparecem; cada variação tem tabela de preços no
site (linha de 1 unidade = preço do vínculo, gravada; faixas criadas no admin);
editar a linha de 1 unidade grava o preço no vínculo do Bling; confirmação de
preços automática ou manual. Até o PR 2 da 008 entrar, vale o fluxo antigo.

Ainda não ponta a ponta: sync bidirecional e webhooks do Bling, entrega regional
por CEP, etiquetas e coleta, remessa/chargeback/nota fiscal, seções "em breve" do
portal (clientes, entrega própria, despacho, configurações), workers e
observabilidade. Tabela ou seed não prova fluxo: confirme router, service,
repository, integração e testes antes de prometer uma capacidade.

## Convenções

Identificadores e código em inglês; comentários, docstrings, mensagens de erro e
comunicação em português. Sucesso responde com `BaseResponse`
(`src/schemas/response_schema.py`), sem esconder o status HTTP real. Commits em
Conventional Commits, atômicos, só quando o usuário pedir.

## Invariantes obrigatórias

- Use `Decimal` para dinheiro. Nunca derive o pedido de preço ou subtotal enviado
  pelo cliente.
- O checkout usa o carrinho persistido, recalcula preços/descontos/frete e exige
  revisão quando `expected_total_amount` divergir.
- Preserve idempotência por usuário, locks ordenados de SKU, reservas de estoque,
  snapshots imutáveis e uma única unidade transacional na confirmação.
- Valide produto e variação ativos e não excluídos novamente no checkout, mesmo
  que o catálogo já os filtre.
- Restrinja dados pessoais e pedidos pelo proprietário; `admin` é a única role
  administrativa e `user` é a role de cliente.
- Faça autorização antes de validações que alcancem persistência. Perguntas e
  avaliações são as exceções atuais de criação autenticada no catálogo.
- Access token não substitui refresh token e refresh token não autentica rotas.
  Preserve rotação, revogação e vínculo do token com o usuário.
- Enquanto as colunas forem timezone-naive, normalize datas persistidas para UTC
  naive de modo consistente.
- Nunca devolva erro cru de banco, token, credencial ou payload sensível.
- Não use `pytest.skip` para ausência de seed. Testes devem montar ou exigir uma
  pré-condição determinística.

## Limites de autorização

Não limpe banco, rode reset, aplique migração destrutiva, altere serviços externos
ou publique mudanças sem autorização correspondente. O script de reset local ter
proteções não transforma seu uso em uma ação implícita.

## Critério de conclusão

Uma mudança está pronta quando o contrato e as invariantes relevantes foram
verificados, os testes proporcionais ao risco passaram, `git diff --check` não
aponta problemas e a documentação da skill continua coerente caso o escopo ou a
arquitetura tenham mudado.
