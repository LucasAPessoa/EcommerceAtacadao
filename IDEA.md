# Instruções do Code Agent - E-commerce Atacadão

## Contexto do Projeto
Você é um AI Coding Assistant focado no projeto **EcommerceAtacadao**. 
Este é um backend de e-commerce robusto e escalável construído com **FastAPI**, seguindo uma arquitetura em camadas (Layered Architecture) orientada a domínios (Catálogo, Identidade, Operações, Vendas).

## Escopo de Negócio (Proposta Comercial)
**Equipe de Desenvolvimento:** Lucas de Almeida Pessoa & Paulo Renato Peris Rosa
**Cliente:** Priscilla
**Prazo Estimado:** 8 semanas (Fluxo contínuo até deploy e homologação)

**Objetivo do Projeto:**
Implementação de um sistema de comércio eletrônico completamente integrado ao ERP Bling e ao gateway de pagamentos Mercado Pago. O foco principal é viabilizar a automatização do controle de inventário, o processamento seguro de vendas e a logística de despacho regional e nacional.

**Escopo Funcional de Engenharia:**
- **Autenticação e Segurança:** Criação de ambiente restrito para clientes (Cadastro/Login) com criptografia padrão de mercado.
- **Gateway de Pagamentos:** Integração com o Mercado Pago para habilitar transações via Pix, Cartão de Crédito e Boleto Bancário.
- **Logística de Frete Nacional:** Integração automatizada com Correios e soluções de cubagem/coleta privada (Melhor Envio / Loggi) para cálculo em tempo real de custos e prazos de postagem.
- **Logística de Entrega Própria (Regional):** Estruturação de inteligência de frete customizada por bairros baseada em tabelas rígidas de faixas de CEP para evitar problemas de digitação e garantir tarifas exatas para serviços de motoboy.
- **Sincronização Bidirecional ERP Bling:** Importação automatizada do catálogo de produtos e sincronização assíncrona de inventário. Configuração de Webhooks para trâmite automático de dados fiscais essenciais à emissão posterior de Notas Fiscais (NF).
- **Módulo de Carrinho:** Persistência de itens, revisão dinâmica de valores e fluxo de checkout sem fricção.
- **Painéis Administrativos (Dashboards):** Painel de controle integrado para consolidação de anúncios do Bling e gerenciamento logístico (status de pacotes, agendamentos de coletas e geração simplificada de etiquetas de envio).
- **Preços de Varejo e Atacado:** Os preços praticados serão diferentes a depender da quantidade de produtos comprados (Lógica essencial para o serviço de catálogo e carrinho).

**Garantia e Condições:**
- Após o deploy final, haverá garantia assistida de 90 dias cobrindo correções de bugs e estabilização de fluxos.
- Custos operacionais (infraestrutura em nuvem, taxas Mercado Pago, assinaturas ERP) e fornecimento de chaves de API/tabelas de CEP são obrigações da Contratante.

## Stack Tecnológico e Dependências
**Linguagem Base e Ferramentas:**
- **Linguagem:** Python 3.11+
- **Gerenciamento de Dependências:** `uv`
- **Build System:** `hatchling`

**Dependências de Produção:**
- `fastapi` (>=0.111.0): Framework Web de alta performance.
- `uvicorn[standard]` (>=0.30.0): Servidor ASGI.
- `pydantic[email]` (>=2.7.0): Validação e Serialização de dados (V2).
- `pydantic-settings` (>=2.2.0): Gestão segura de variáveis de ambiente.
- `python-multipart` (>=0.0.9): Processamento de formulários e upload de ficheiros.
- `sqlalchemy` (>=2.0.30): ORM (Sintaxe 2.0).
- `alembic` (>=1.13.1): Controlo de versões da base de dados (Migrations).
- `asyncpg` (>=0.29.0): Driver assíncrono nativo para PostgreSQL.
- `pyjwt` (>=2.8.0): Geração e validação de tokens JWT.
- `passlib[bcrypt]` (>=1.7.4): Hashing seguro de palavras-passe.

**Dependências de Desenvolvimento (Testes e Qualidade):**
- `pytest` (>=8.2.0) e `pytest-asyncio` (>=0.23.6): Framework de testes unitários e assíncronos.
- `ruff` (>=0.4.4): Linter e Formatter super-rápido (regras E, F, I).
- `mypy` (>=1.10.0): Verificação rigorosa de tipagem estática.

## Arquitetura e Fluxo de Dados
A separação de responsabilidades é estrita. Uma requisição deve fluir da seguinte maneira:
`Router (FastAPI) -> Service (Business Logic) -> Repository (Data Access) -> DB`

- **`src/models/`**: Exclusivo para Modelos SQLAlchemy (definição de tabelas do banco). Não adicione lógica de validação aqui.
- **`src/schemas/`**: Exclusivo para Modelos Pydantic. Define os contratos de entrada (requests) e saída (responses).
- **`src/repositories/`**: Centraliza todas as queries de banco de dados. Nunca acesse a sessão do DB diretamente no Controller.
- **`src/services/`**: Lógica de negócio. Não deve conhecer o framework web (não importe `Request` ou lance `HTTPException` do FastAPI aqui).
- **`src/api/v1/endpoints/`**: Controladores (Routers). Sua única função é receber a requisição, chamar o Service injetado via `Depends()`, e retornar a resposta.

## Padrões de Código e Regras Estritas

### 1. Respostas Padronizadas (BaseResponse)
- **TODOS** os endpoints devem retornar respostas envelopadas no modelo genérico `BaseResponse` (localizado em `src/schemas/response_schema.py`).
- O schema esperado é estrito: `{"status": "success" | "error", "message": "string", "data": <payload>, "errors": [...]}`.
- Nunca retorne objetos puros ou listas soltas. Enclausure-os no campo `data` do `BaseResponse`.

### 2. Tratamento Global de Erros
- Respeite o sistema de Exception Handlers globais implementado no `src/main.py`.
- Erros de validação de payload (`RequestValidationError`), erros HTTP (`HTTPException`) e exceções não tratadas são formatados automaticamente para o padrão `BaseResponse`.
- Na camada de serviço, prefira levantar exceções de domínio claras ou usar blocos `try/except` que repassem mensagens legíveis para a camada de controle.

### 3. Idioma e Nomenclatura
- **Código:** Nomes de variáveis, classes, funções, arquivos e tabelas do banco devem ser **100% em Inglês** (ex: `category_service.py`, `is_active`, `create_order`).
- **Comentários, Docstrings e Commits:** Devem ser em **Português**, garantindo a clareza para a equipa local.
- Padrões:
  - Classes: `PascalCase` (ex: `CategoryRepository`).
  - Funções/Variáveis/Arquivos: `snake_case` (ex: `get_category_by_id`).

### 4. Boas Práticas Pythonicas
- **Type Hints:** É estritamente obrigatório tipar parâmetros e retornos de todas as funções/métodos.
- **Injeção de Dependências:** Use extensivamente o sistema do FastAPI (`Depends()`) para instanciar repositórios e serviços, garantindo a facilidade de testes unitários.

### 5. Banco de Dados e Migrações
- Quaisquer alterações nos arquivos em `src/models/` **exigem** a geração de uma nova migration via Alembic.
- Comando padrão esperado: `alembic revision --autogenerate -m "descrição da mudança em inglês"`.
