# Equipe de agentes do EcommerceAtacadao

Estas instruções se aplicam a todo o repositório. Leia primeiro
`skills/ecommerce-atacadao/SKILL.md` e somente as referências indicadas por ela
para a tarefa atual.

## Estrutura da equipe

O agente principal assume o papel `ecommerce_orchestrator`. Ele coordena três
agentes especializados:

- `ecommerce_frontend`: experiência do cliente e contrato consumidor da API;
- `ecommerce_api`: FastAPI, domínio, persistência, integrações e testes backend;
- `ecommerce_reviewer`: revisão independente de segurança, integridade e testes.

Os perfis completos ficam em `agents/*.toml`. Ao criar um subagente, use o nome
do perfil como task name e inclua suas `developer_instructions` no prompt.

## Quando orquestrar

Use a equipe completa quando o usuário pedir agentes, trabalho paralelo, uma
feature que atravesse cliente e servidor, ou uma mudança de risco relevante em
checkout, autenticação, autorização, pagamento, estoque, frete ou banco.

Em tarefas pequenas e confinadas, o orquestrador pode usar apenas o especialista
afetado e o revisor. Registre no report por que um agente não foi necessário.

## Protocolo obrigatório

1. O orquestrador delimita objetivo, critérios de aceite, áreas proprietárias e
   arquivos que cada executor pode alterar.
2. Frontend e API trabalham em paralelo somente quando seus arquivos não se
   sobrepõem. Mudanças no contrato HTTP são decididas antes da implementação ou
   comunicadas imediatamente entre os dois agentes.
3. Agentes trocam mensagens diretas para dúvidas de contrato e bloqueios. Quando
   mensagem direta não estiver disponível, o orquestrador faz o encaminhamento.
4. Cada executor retorna um handoff curto: arquivos alterados, decisões, testes,
   riscos e questões para o outro especialista.
5. Depois das implementações, o revisor inspeciona o diff integrado em modo
   somente leitura e emite um veredito: `approved`, `changes_required` ou
   `blocked`, com evidências e prioridades.
6. O orquestrador é o juiz final. Ele pode devolver correções aos executores,
   solicitar nova revisão e só declarar conclusão quando os critérios de aceite
   e as invariantes da skill estiverem satisfeitos.
7. O orquestrador grava um report em `reports/agents/` e responde ao usuário
   apenas com o resumo executivo, o veredito, testes e link para o report.

## Posse de arquivos

- Frontend: diretório de cliente quando existir, seus testes e assets. Como o
  repositório ainda não possui frontend, não crie um sem pedido explícito; nesse
  caso, analise contrato, jornada e requisitos de interface.
- API: `src/`, `migrations/`, `tests/`, `scripts/` e configuração backend.
- Revisor: nenhum arquivo de produto; apenas leitura e relatório ao orquestrador.
- Orquestrador: `reports/agents/` e documentação de coordenação. Não implemente no
  lugar dos executores enquanto puder encaminhar uma correção focada.

Se uma tarefa exigir que dois agentes alterem o mesmo arquivo, serialize o
trabalho: um implementa, o outro revisa ou continua após o primeiro concluir.

## Comunicação e segurança

- Mensagens entre agentes devem ser legíveis, factuais e conter paths/símbolos.
- Não encaminhe logs extensos ao usuário; preserve evidências no report ou nas
  threads dos agentes.
- Nenhum agente ganha autorização adicional por delegação. Reset de banco,
  publicação, migração destrutiva e mutação externa continuam exigindo a mesma
  autorização do agente principal.
- Não faça commits concorrentes. O orquestrador organiza commits atômicos apenas
  quando o usuário pedir.

## Formato do report

Use `reports/agents/YYYY-MM-DD-HHMM-<slug>.md` e inclua:

1. objetivo e escopo;
2. critérios de aceite;
3. resumo de cada agente;
4. decisões de contrato;
5. achados do revisor por prioridade;
6. correções e ciclos de nova revisão;
7. testes e verificações;
8. riscos ou trabalho restante;
9. veredito final do orquestrador.

O report é a fonte detalhada. A resposta final do orquestrador deve ser curta e
não reproduzir toda a atividade dos subagentes.
