# Auditoria UX da loja e nova direção visual (2026-10-27)

**Pedido:** revisar a loja com o novo revisor `atacadao-ux`, transformar os achados em issues e propor um design clean, legível e com personalidade.

## Execução
- Duas auditorias do `atacadao-ux` em paralelo: vitrine/produto (12 achados) e carrinho/checkout/conta (13 achados). Veredito nas duas: `changes_required`.
- Correção do orquestrador: o "P0" de contraste no botão principal (branco sobre `#ff3b00`, 3,57:1) é falso positivo em runtime. `Layout.tsx` aplica `brandTokens()` (`src/shared/theme.ts:41`), que escolhe tinta (5,54:1). Só o fallback do CSS está errado; ficou como item da front #63.

## Issues no front (label nova `ux`)
- Novas: #62 grade do catálogo remonta (bug), #63 fundação visual por tokens (urgente), #64 aplicar a nova direção, #65 quantidade e remoção, #66 endereço com CEP (decisão de API pendente), #67 navegação e busca única.
- Escopo adicional por comentário: #4, #6, #7, #9, #25, #29, #36, #38, #39.

## Design
- Canvas "Loja Clean — Nova Direção": https://claude.ai/artifact/M4P93CFnmQcLd4gqxjhFkz
- Direção "Gôndola": neutros frios, cards separados pelo fundo, cor da marca por deploy com texto calculado por contraste e amarelo de etiqueta de prateleira só no preço ativo. Gabarito em títulos e Atkinson Hyperlegible Next no resto.
- Telas: home, produto (interativo, com escada de preço por embalagem), carrinho (interativo, com desfazer e CTA que explica o que falta), produto no celular e tokens com os contrastes calculados.
- O design system da Embeddo, disponível na conta, não foi usado: a loja é white-label.

## Roadmap
- Etapa 2 do roadmap (https://claude.ai/artifact/Qvb4kk7QEeWLADKpstdCu9) atualizada com as issues #62–#67.

## Próximo passo sugerido
1. Usuário aprova ou ajusta o canvas.
2. #62 (correção pequena) e #63 com o `atacadao-front`.
3. Revisão do `atacadao-ux` em modo diff em cada PR.
