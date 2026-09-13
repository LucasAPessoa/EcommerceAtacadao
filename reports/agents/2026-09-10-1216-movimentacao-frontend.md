# Movimentação do frontend

## 1. Objetivo e escopo

Mover integralmente o frontend inicial de
`/home/lucas/Projetos/EcommerceAtacadao/frontend` para o projeto separado
`/home/lucas/Projetos/front_atacadao`.

## 2. Critérios de aceite

- O destino não preexistia e contém a estrutura completa do cliente.
- O caminho antigo não permanece no repositório.
- Não há referências obrigatórias ao caminho antigo no novo projeto.
- O build do cliente passa no novo local.

## 3. Resumo de cada agente

- `ecommerce_frontend`: validou a estrutura, dependências e referências no
  destino, sem editar arquivos.
- `ecommerce_api`: não foi necessário: a mudança é confinada ao cliente e não
  altera contrato HTTP ou backend.
- `ecommerce_reviewer`: revisou a movimentação em modo somente leitura e emitiu
  `approved`.

## 4. Decisões de contrato

Nenhuma. A URL da API continua configurável por `VITE_API_BASE_URL` no novo
projeto.

## 5. Achados do revisor por prioridade

Nenhum achado.

## 6. Correções e ciclos de nova revisão

O servidor de desenvolvimento anterior deixou somente o cache transitório
`frontend/.vite` no caminho original. Ele foi removido para concluir a mudança.
Não houve alteração de código.

## 7. Testes e verificações

- Confirmação de ausência de `/home/lucas/Projetos/EcommerceAtacadao/frontend`.
- Confirmação de presença de `/home/lucas/Projetos/front_atacadao`.
- Busca sem referências obrigatórias ao caminho antigo.
- `npm run build` no novo destino: passou.
- `git diff --check`: passou.

## 8. Riscos ou trabalho restante

O frontend está fora do repositório do backend e terá ciclo de versionamento,
commit e deploy independentes.

## 9. Veredito final do orquestrador

**approved**. O frontend foi movido integralmente e está compilando no novo
projeto.
