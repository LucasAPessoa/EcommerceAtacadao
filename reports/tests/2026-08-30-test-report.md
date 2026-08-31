# Relatório de testes — 30/08/2026

## Escopo

Execução completa da suíte localizada em `tests/` após a remoção dos
scripts de teste que estavam na raiz do repositório.

Comando executado:

```bash
UV_CACHE_DIR=/tmp/ecommerce-uv-cache uv run pytest -q \
  --junitxml=reports/tests/pytest-results.xml
```

## Resultado

| Resultado | Quantidade |
|---|---:|
| Testes coletados | 106 |
| Aprovados | 2 |
| Falhas | 42 |
| Erros de preparação | 62 |
| Ignorados | 0 |
| Duração | 31,34 s |

Os dois testes unitários de checkout foram aprovados:

- aplicação da maior faixa de preço de atacado elegível;
- rejeição da compra quando reservas existentes tornam o estoque insuficiente.

## Causa predominante

Os outros 104 testes são testes black-box configurados em `tests/conftest.py`
para acessar uma API previamente iniciada em `http://127.0.0.1:8000`.
A API não estava disponível durante esta execução. Por isso, as falhas e os
erros apresentam predominantemente:

```text
httpx.ConnectError: All connection attempts failed
```

O resultado não permite concluir que os 104 comportamentos da aplicação
estão incorretos: as requisições não chegaram ao FastAPI. Para validar esses
cenários é necessário iniciar PostgreSQL, aplicar as migrations, executar o
seed e iniciar a API antes do pytest.

## Aviso de segurança

A execução também produziu `InsecureKeyLengthWarning`: a chave HMAC usada no
ambiente de teste possui 12 bytes, abaixo dos 32 bytes recomendados para
HS256. A configuração de testes deve usar uma chave com pelo menos 32 bytes.

## Arquivos removidos da raiz

- `comprehensive_test.py`
- `comprehensive_test_admin_only.py`
- `comprehensive_test_both.py`
- `comprehensive_test_final.py`
- `route_validation_test.py`
- `test_user_flow.py`

Os testes mantidos ficam exclusivamente em `tests/`.

## Artefato detalhado

O resultado estruturado completo, incluindo cada caso e traceback, está em:

```text
reports/tests/pytest-results.xml
```

## Próxima execução recomendada

```bash
uv run alembic upgrade head
uv run python -m scripts.seed
uv run uvicorn src.main:app
UV_CACHE_DIR=/tmp/ecommerce-uv-cache uv run pytest -q
```

Em uma evolução posterior, os testes HTTP deveriam usar `ASGITransport` e um
banco isolado de testes para não depender de um servidor iniciado manualmente.
