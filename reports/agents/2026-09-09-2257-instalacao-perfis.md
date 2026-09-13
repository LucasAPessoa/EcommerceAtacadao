# Instalação de perfis

1. **Objetivo e escopo:** copiar os quatro perfis de `agents/ecommerce-*.toml` para `.codex/agents/`, sem alterar seu conteúdo. `agents/config.toml` ficou fora do escopo solicitado.
2. **Critérios de aceite:** quatro arquivos presentes, idênticos às origens e TOML válido.
3. **Resumo por agente:** orquestrador realizou a cópia de configuração. Frontend, API e revisor não foram acionados por se tratar de cópia mecânica, sem implementação ou alteração de produto; integridade verificada diretamente.
4. **Contrato:** nenhum contrato HTTP alterado.
5. **Achados:** nenhuma divergência de conteúdo ou erro de sintaxe TOML.
6. **Correções e nova revisão:** não necessárias.
7. **Validações:** comparação byte a byte dos quatro arquivos e parsing com tomllib passaram. Sem testes de aplicação, pois não houve alteração de código. Carregamento pelo aplicativo não foi testado nesta sessão.
8. **Riscos ou trabalho restante:** nenhum para a cópia solicitada.
9. **Veredito final:** approved para a instalação dos arquivos.
