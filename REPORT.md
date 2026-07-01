# Relatório do Projeto EcommerceAtacadao

## Visão Geral do Projeto
Backend de e-commerce robusto e escalável construído com FastAPI, seguindo uma arquitetura em camadas (Layered Architecture) orientada a domínios (Catálogo, Identidade, Operações, Vendas). O objetivo é viabilizar a automatização do controle de inventário, processamento seguro de vendas e logística de despacho regional e nacional, integrado ao ERP Bling e ao gateway de pagamentos Mercado Pago.

**Equipe de Desenvolvimento:** Lucas de Almeida Pessoa & Paulo Renato Peris Rosa  
**Cliente:** Priscilla  
**Prazo Estimado:** 8 semanas (fluxo contínuo até deploy e homologação)

## Escopo Funcional de Engenharia
- Autenticação e Segurança: ambiente restrito para clientes (cadastro/login) com criptografia padrão de mercado.
- Gateway de Pagamentos: integração com Mercado Pago (Pix, Cartão de Crédito, Boleto Bancário).
- Logística de Frete Nacional: integração automatizada com Correios e soluções de cubagem/coleta privada (Melhor Envio / Loggi) para cálculo em tempo real de custos e prazos.
- Logística de Entrega Própria (Regional): estruturação de inteligência de frete customizada por bairros baseada em tabelas rígidas de faixas de CEP.
- Sincronização Bidirecional ERP Bling: importação automatizada do catálogo de produtos e sincronização assíncrona de inventário; webhooks para trâmite automático de dados fiscais essenciais à emissão de Notas Fiscais (NF).
- Módulo de Carrinho: persistência de itens, revisão dinâmica de valores e fluxo de checkout sem fricção.
- Painéis Administrativos (Dashboards): painel de controle integrado para consolidação de anúncios do Bling e gerenciamento logístico (status de pacotes, agendamentos de coletas e geração simplificada de etiquetas de envio).
- Preços de Varejo e Atacado: preços diferentes conforme quantidade comprada (lógica essencial para catálogo e carrinho).

## Stack Tecnológico e Dependências
- **Linguagem:** Python 3.11+
- **Gerenciamento de Dependências:** `uv`
- **Build System:** `hatchling`

### Dependências de Produção
- `fastapi>=0.111.0`
- `uvicorn[standard]>=0.30.0`
- `pydantic[email]>=2.7.0`
- `pydantic-settings>=2.2.0`
- `python-multipart>=0.0.9`
- `sqlalchemy>=2.0.30`
- `alembic>=1.13.1`
- `asyncpg>=0.29.0`
- `pyjwt>=2.8.0`
- `passlib[bcrypt]>=1.7.4`

### Dependências de Desenvolvimento (Testes e Qualidade)
- `pytest>=8.2.0`
- `pytest-asyncio>=0.23.6`
- `ruff>=0.4.4`
- `mypy>=1.10.0`

## Arquitetura e Fluxo de Dados
A separação de responsabilidades é estrita. Uma requisição deve fluir da seguinte maneira:
```
Router (FastAPI) -> Service (Business Logic) -> Repository (Data Access) -> DB
```

### Organização de Pastas e Responsabilidades
- `src/models/`: Modelos SQLAlchemy 2.0 (definição de tabelas). **Não** adicione lógica de validação aqui.
- `src/schemas/`: Modelos Pydantic (contratos de entrada e saída).
- `src/repositories/`: Centraliza todas as queries de banco de dados. Nunca acesse a sessão do DB diretamente no Controller.
- `src/services/`: Lógica de negócio. Não deve conhecer o framework web (não importe `Request` ou lance `HTTPException` do FastAPI aqui).
- `src/api/v1/endpoints/`: Controladores (Routers). Sua única função é receber a requisição, chamar o Service injetado via `Depends()`, e retornar a resposta.

## Padrões de Código e Regras Estritas
1. **Respostas Padronizadas (BaseResponse)**  
   TODOS os endpoints devem retornar respostas envelopadas no modelo genérico `BaseResponse` (localizado em `src/schemas/response_schema.py`).  
   Schema esperado:  
   ```json
   {
     "status": "success" | "error",
     "message": "string",
     "data": <payload>,
     "errors": [...]
   }
   ```
   Nunca retorne objetos puros ou listas soltas. Enclausure-os no campo `data` do `BaseResponse`.

2. **Tratamento Global de Erros**  
   Respeite o sistema de Exception Handlers globais implementado em `src/main.py`.  
   Erros de validação de payload (`RequestValidationError`), erros HTTP (`HTTPException`) e exceções não tratadas são formatados automaticamente para o padrão `BaseResponse`.  
   Na camada de serviço, prefira levantar exceções de domínio claras ou usar blocos `try/except` que repassem mensagens legíveis para a camada de controle.

3. **Idioma e Nomenclatura**  
   - **Código:** Nomes de variáveis, classes, funções, arquivos e tabelas do banco devem ser **100% em Inglês** (ex: `category_service.py`, `is_active`, `create_order`).  
   - **Comentários, Docstrings e Commits:** Devem ser em **Português**, garantindo a clareza para a equipe local.  
   - Padrões:  
     - Classes: `PascalCase` (ex: `CategoryRepository`)  
     - Funções/Variáveis/Arquivos: `snake_case` (ex: `get_category_by_id`)

4. **Boas Práticas Pythonicas**  
   - **Type Hints:** Obrigatório tipar parâmetros e retornos de todas as funções/métodos.  
   - **Injeção de Dependências:** Use extensivamente o sistema do FastAPI (`Depends()`) para instanciar repositórios e serviços, garantindo a facilidade de testes unitários.

5. **Banco de Dados e Migrações**  
   - Quaisquer alterações nos arquivos em `src/models/` **exigem** a geração de uma nova migration via Alembic.  
   - Comando padrão esperado:  
     ```bash
     alembic revision --autogenerate -m "descrição da mudança em inglês"
     ```

## Estrutura de Diretórios (arquivos relevantes)
```
.
├── src/
│   ├── api/
│   │   └── v1/
│   │       ├── endpoints/
│   │       │   ├── catalog/
                │   │       ├── category.py
                │   │       └── router.py
                │   │   └── router.py
                │   └── ...
│   ├── core/
│   │   ├── config.py
│   │   ├── db.py
│   │   └── __init__.py
│   ├── models/
│   │   ├── base.py
│   │   ├── catalog.py
│   │   ├── identity.py
│   │   ├── operations.py
│   │   ├── sales.py
│   │   └── __init__.py
│   ├── repositories/
│   │   └── catalog/
│   │       └── category_repository.py
│   ├── schemas/
│   │   ├── catalog/
                │   │   └── category_schema.py
                │   └── response_schema.py
│   ├── services/
│   │   └── catalog/
                │   │   └── category_service.py
│   ├── __init__.py
│   └── main.py
├── migrations/
├── .env (secret, não versionado)
├── .env.example (não versionado, mas usado como referência)
├── alembic.ini
├── pyproject.toml
├── uv.lock
├── IDEA.md
└── README.md (vazio atualmente)
```

## Modelos Principais (src/models/)
- **Base:** Classe base declarativa do SQLAlchemy 2.0.
- **TimestampMixin:** Campos `created_at` e `updated_at` para auditoria.
- **SoftDeleteMixin:** Campo `deleted_at` para soft delete.
- **Catalog Models:**
  - `Category`: id, name (único), description, is_active, relação muitos-para-muitos com Product.
  - `Product`: id, name (único), description, is_active, relações com Variant, PricingTier, Review, Question.
  - `ProductVariant`: id, product_id (FK), sku_bling (único), name_variation, base_price, stock_quantity, last_sync_bling, is_active, dimensões logísticas (weight_kg, height_cm, width_cm, length_cm), relação com ProductImage.
  - `ProductImage`: id, variant_id (FK), image_url, is_main.
  - `PricingTier`: id, product_id (FK), min_quantity, unit_price.
  - `ProductReview`, `ProductQuestion`: modelos simples com timestamps.

## Serviços Principais (src/services/)
- `src/services/catalog/category_service.py`: contém a lógica de negócio para categorias (criação, listagem, atualização, exclusão, etc.). Segue o padrão de não conhecer o framework web.

## Repositórios Principais (src/repositories/)
- `src/repositories/catalog/category_repository.py`: centraliza as queries de banco para a entidade Category.

## Endpoints Principais (src/api/v1/endpoints/)
- `src/api/v1/endpoints/catalog/category.py`: router para operações de categoria (CRUD).
- `src/api/v1/endpoints/catalog/router.py`: agrega routers do catálogo.
- `src/api/v1/endpoints/router.py`: router principal da API v1.

## Configurações Principais
- `src/core/config.py`: carrega variáveis de ambiente via `pydantic-settings` (arquivo `.env`).
- `src/core/db.py`: configuração assíncrona do SQLAlchemy com `asyncpg` e engine assíncrona.
- `src/main.py`: instancia o FastAPI, configura CORS, trata exceções globais, inclui rotas e fornece endpoint `/health`.

## Histórico Recente de Commits (últimos 10)
```
04f6a7b feat: add global error handler to clarify and return errors with friendly messages
efa49da feat: add name and is _active fields to category and turn name unique and apply migration
7359b0a feat: add create category feature
8a33abd fix: move main.py to src folder
ffbc2de fix: fix wrong imports breaking the code and generate initial migration
39e5988 feat: initial database modeling
3c08159 initial commit
```

## Arquivos Modificados (não commitados atualmente)
- `src/api/v1/endpoints/catalog/category.py`
- `src/repositories/catalog/category_repository.py`
- `src/services/catalog/category_service.py`

## Arquivos Não Rastreados
- `IDEA.md` (documentação detalhada do projeto e instruções para o agente de código)

## Observações
- O projeto utiliza um padrão de camadas bem definido, facilitando a manutenção e testes.
- As mensagens de commit e comentários estão em português, conforme convenção da equipe.
- O uso de `uv` como gerenciador de dependências garante instalações rápidas e reproduzíveis.
- O banco de dados presumido é PostgreSQL (via `asyncpg` e `asyncpg` driver no SQLAlchemy).
- Ainda não há testes automatizados visíveis (pastas de teste não encontradas); isso pode ser um ponto de melhoria.
- O arquivo `.env` contém variáveis de ambiente sensíveis e não deve ser versionado.

## Próximos Passos Sugeridos
1. Implementar testes unitários e de integração usando `pytest` e `pytest-asyncio`.
2. Criar migrations para as novas funcionalidades de categoria, produto, variante, etc.
3. Implementar os demais domínios: identidade (auth), operações, vendas, pagamentos, logística.
4. Definir variáveis de ambiente necessárias (Bling, Mercado Pago, Correios, etc.) em `.env.example`.
5. Preencher o `README.md` com instruções de setup e uso.
6. Considerar adicionar endpoints de saúde mais detalhados (ex: checagem de banco de dados).
7. Revisar permissões CORS em produção (atualmente `allow_origins=["*"]`).

---
*Relatório gerado automaticamente pelo agente de código Hermes em 29/06/2026.*