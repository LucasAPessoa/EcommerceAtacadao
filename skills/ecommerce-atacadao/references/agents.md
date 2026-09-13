# Equipe de coding agents

O projeto usa o agente principal como `ecommerce_orchestrator` e três perfis em
`agents/`: frontend, API e revisão. As regras executáveis de coordenação estão no
`AGENTS.md` da raiz; leia esse arquivo por completo antes de iniciar um fluxo
multiagente.

## Fluxo

```text
usuário
  -> orquestrador: escopo, critérios e delegação
       -> frontend: jornada e contrato consumidor
       -> API: domínio, persistência e contrato servidor
       -> revisor: diff integrado e veredito independente
  <- orquestrador: julgamento final e report consolidado
```

Frontend e API podem trabalhar simultaneamente quando não editarem os mesmos
arquivos. Eles comunicam mudanças de contrato entre si; o orquestrador encaminha
quando mensagem direta não estiver disponível. O revisor entra depois do handoff
dos executores e permanece somente leitura.

Reports ficam em `reports/agents/`. Logs e detalhes intermediários permanecem nas
threads dos agentes; o usuário recebe um resumo com o veredito e o link do report.

## Instalação nativa

Codex reconhece agentes de projeto em `.codex/agents/*.toml` e configurações
globais em `.codex/config.toml`. Neste workspace, `.codex` é montado como somente
leitura. Por isso, os perfis versionáveis ficam em `agents/` e o `AGENTS.md`
instrui o agente principal a usá-los ao criar os subagentes.

Quando `.codex` aceitar escrita, copie os quatro perfis para `.codex/agents/` e o
conteúdo de `agents/config.toml` para `.codex/config.toml`. O limite de três
threads exclui o agente principal e corresponde aos três especialistas.
