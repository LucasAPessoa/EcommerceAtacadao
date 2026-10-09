# Auditoria de deploy gratuito no Vercel

## Objetivo e escopo

Organizar com segurança o caminho de deploy do backend e do storefront no
Vercel, respeitando a exigência de não usar recursos pagos nem gerar cobranças.
A auditoria foi somente leitura, com a exceção da documentação deste limite.

## Critérios de aceite

- Não criar deploy, projeto, migração remota, variável remota ou cobrança.
- Não acessar, registrar ou expor segredos.
- Verificar preparação local de backend e frontend.
- Confirmar se o plano gratuito é compatível com uma loja comercial.
- Registrar qualquer impeditivo e os pré-requisitos técnicos restantes.

## Resumo dos agentes

### ecommerce_api

Inspecionou o backend. `pyproject.toml` declara `src.main:app`, o entrypoint
FastAPI existe e não requer `vercel.json`. A API exige variáveis de banco,
identidade, Melhor Envio e Mercado Pago; migrações devem continuar fora da
Function. O CORS usa allowlist explícita e o pool atual merece revisão antes de
escala serverless com PostgreSQL gratuito. Executou
`uv run pytest tests/test_main_unit.py tests/test_config_unit.py -q`: 5 testes
passaram.

### ecommerce_frontend

Inspecionou `/home/lucas/Projetos/front_atacadao`. O build é Vite com output
`dist` e o rewrite da SPA cobre os links diretos. `VITE_API_BASE_URL` precisa
ser a URL HTTPS pública da API incluindo `/api/v1`; é valor público de build e
nunca deve conter segredo. Os callbacks do Mercado Pago exigem backend HTTPS e
origem HTTPS exata no CORS.

### ecommerce_reviewer

Revisou a decisão e a correção documental. Veredito final: `approved`.

## Decisões de contrato e infraestrutura

- Backend e frontend permanecem projetos e repositórios independentes.
- Não foram configurados projetos, domínios, variáveis ou deploys no Vercel.
- Um eventual ambiente compatível exige API HTTPS, `CORS_ALLOWED_ORIGINS` com
origens exatas e as URLs públicas de retorno/notificação do Mercado Pago.
- Migrações Alembic não devem executar em build ou requisição; são mutação de
banco e devem ocorrer em ambiente controlado.

## Achados do revisor

- P1: Vercel Hobby é gratuito para uso pessoal e não comercial. Uma loja em
operação comercial não pode ser publicada nesse plano sem contrariar os termos.
- P1: Neon, Mercado Pago e Melhor Envio são serviços externos com condições e
possíveis custos próprios; a gratuidade da Vercel não os cobre.
- P2 corrigido: o README agora explicita essa limitação para evitar deploy futuro
incompatível.

## Correções e nova revisão

Foi atualizada somente a seção de deploy de `README.md`, sem código, segredos ou
configuração remota. A revisão final confirmou que a redação não expõe dados
sensíveis e representa corretamente o limite do plano.

## Testes e verificações

- `uv run pytest tests/test_main_unit.py tests/test_config_unit.py -q` — 5
  aprovados.
- `git diff --check` — aprovado.
- Árvores de trabalho auditadas sem `.vercel` vinculada.

## Riscos e trabalho restante

Não existe um caminho de deploy em produção no Vercel Hobby que cumpra ao mesmo
tempo os termos da plataforma e a exigência de custo zero para esta loja. A
execução local e testes de sandbox podem continuar sem publicar a operação.

## Veredito final do orquestrador

`approved` para a auditoria, o bloqueio preventivo de publicação comercial no
Hobby e a documentação. `blocked` para deploy de produção comercial no Vercel
Hobby sob a exigência de custo zero.
