# Desenvolvimento, banco e validação

## Preparação local

Use os comandos e versões declarados no repositório. O fluxo padrão é:

```bash
uv sync
uv run alembic upgrade head
uv run uvicorn app.main:app
```

Consulte `pyproject.toml`, `alembic.ini`, `.env.example` e a configuração real
antes de assumir nomes de variáveis ou serviços. Não copie segredos do `.env`
para documentação, logs ou relatórios.

## Migrações

Para mudança de schema:

```bash
uv run alembic revision --autogenerate -m "descricao curta"
uv run alembic upgrade head
```

Revise o arquivo gerado. Autogenerate não decide corretamente toda regra de
negócio. Confira:

- tipo, precisão, nulabilidade e default;
- nomes de constraints e índices;
- chaves estrangeiras, cascatas e unicidade;
- transformação/backfill de dados existentes;
- simetria e segurança do downgrade.

Há histórico sensível a nome de constraint em downgrade. Teste o intervalo
afetado antes de afirmar reversibilidade. Não aplique downgrade destrutivo em
banco compartilhado sem autorização explícita.

## Reset e seed

O projeto possui fluxo protegido para limpar/recriar o banco local e seed
determinístico para as entidades. Reset é destrutivo: confirme alvo, ambiente e
autorização antes de executá-lo. Nunca derive o alvo de uma variável vazia ou de
um caminho/banco amplo.

Ao alterar domínio persistido:

1. atualize model e schema;
2. crie/revise migração;
3. ajuste seed e relações;
4. ajuste reset somente se a ordem/infraestrutura exigir;
5. adicione testes independentes da ordem de execução.

Seed dá um estado representativo, não licença para testes dependerem de registros
implícitos. Cada teste deve criar, localizar ou validar explicitamente sua
pré-condição.

## Testes

A suíte oficial fica em `tests/`. Execute toda a suíte com o comando configurado
no projeto, normalmente:

```bash
uv run pytest tests
```

Para iteração, rode primeiro o arquivo/caso afetado e depois amplie:

```bash
uv run pytest tests/caminho/test_arquivo.py -q
uv run pytest tests -q
```

Os testes incluem unidades e cenários black-box que podem exigir servidor e banco
reais. Descubra fixtures e marcadores antes de iniciar serviços duplicados. Uma
falha `502` em frete pode representar indisponibilidade/credencial do Melhor
Envio, não necessariamente regressão local; mantenha a asserção do contrato e
isole a integração quando o objetivo for regra interna.

Regras da suíte:

- nenhum `pytest.skip` para ocultar dados ausentes ou recurso quebrado;
- fixtures determinísticas e isolamento entre usuários;
- restauração/limpeza proporcional do estado criado;
- testes de status HTTP e corpo, não apenas caminho feliz;
- fluxos transacionais verificam efeitos no banco e ausência de estado parcial.

Se gerar JUnit ou relatório, grave em `reports/tests/`. Artefatos gerados devem
continuar fora do versionamento, enquanto relatórios Markdown deliberadamente
curados podem ser versionados quando agregarem contexto durável.

## Qualidade

Use a configuração do `pyproject.toml`:

```bash
uv run ruff check .
uv run ruff format --check .
uv run mypy app
```

Nem toda mudança exige todas as verificações, mas checkout, autenticação, models
e infraestrutura merecem validação ampla. Antes da entrega, execute ao menos:

```bash
git diff --check
git status --short
```

Leia o diff completo e preserve alterações do usuário que não pertencem à tarefa.

## Servidor

Para execução normal use o entrypoint documentado, sem modo de teste ou reload a
menos que necessário. Verifique `/health` e a documentação. Se o processo precisar
ficar ativo, informe PID/sessão e porta; não inicie uma segunda instância sobre a
mesma porta sem checar a primeira.

## Commits

Só faça commit quando o usuário autorizar. Use Conventional Commits, escopo claro
quando útil e unidades atômicas, por exemplo:

- `feat: adiciona ...`
- `fix: preserva ...`
- `test: cobre ...`
- `docs: documenta ...`
- `refactor: separa ...`
- `chore: ajusta ...`

Cada commit deve compilar conceitualmente sozinho: implementação e seu teste
essencial ficam juntos; documentação independente pode ser separada. Não misture
formatação ampla ou arquivos não relacionados. Mostre os hashes e a validação
executada ao entregar.

## Atualização desta skill

Quando a arquitetura, domínio, API ou operação mudar, atualize o arquivo de
referência correspondente na mesma tarefa. Valide o pacote com:

```bash
python3 /home/lucas/.codex/skills/.system/skill-creator/scripts/quick_validate.py skills/ecommerce-atacadao
```

Mantenha `SKILL.md` como roteador conciso e mova detalhes duráveis para
`references/`. Não documente capacidade futura como se estivesse entregue.
