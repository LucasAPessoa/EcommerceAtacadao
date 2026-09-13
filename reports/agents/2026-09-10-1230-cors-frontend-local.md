# CORS para frontend local

## 1. Objetivo e escopo

Permitir que o frontend Vite local consulte a API FastAPI em `127.0.0.1:8000`
sem abrir CORS para origens arbitrárias.

## 2. Critérios de aceite

- Permitir `http://localhost:5173` e `http://127.0.0.1:5173`.
- Manter credenciais sem usar `*`.
- Confirmar preflight para headers e métodos usados pelo cliente.
- Atualizar a configuração local e o exemplo versionável.

## 3. Resumo de cada agente

- `ecommerce_api`: configurou a allowlist por vírgulas, atualizou o exemplo e
  adicionou cobertura de preflight.
- `ecommerce_frontend`: confirmou que o Vite usa a porta `5173` e que ambas as
  formas de host são origens distintas.
- `ecommerce_reviewer`: revisou segurança e contrato CORS; veredito
  `approved`.

## 4. Decisões de contrato

`CORS_ALLOWED_ORIGINS` passou a conter exclusivamente:

```text
http://127.0.0.1:5173,http://localhost:5173
```

O middleware preserva `allow_credentials=True` e descarta wildcard.

## 5. Achados do revisor por prioridade

Nenhum achado.

## 6. Correções e ciclos de nova revisão

Não houve ciclo adicional.

## 7. Testes e verificações

- `uv run pytest tests/test_main_unit.py -q`: 3 passed.
- Ruff focado: passou.
- `git diff --check`: passou.

## 8. Riscos ou trabalho restante

A API precisa ser reiniciada após a alteração do `.env`, pois o middleware lê a
configuração no início do processo. Não havia processo escutando na porta 8000
neste ambiente no momento da validação.

## 9. Veredito final do orquestrador

**approved**. O navegador poderá consultar a API local após iniciar ou reiniciar
o processo FastAPI.
