# Front #1 — gestão de endereços antes do checkout

- Repo: `front_atacadao`, branch `fix/1-address-management` (sem commit/push)
- Fluxo: locator → atacadao-front (2 ciclos) → atacadao-reviewer (2 ciclos) → **approved**
- Contrato HTTP: sem mudança; a API já tinha o CRUD `/addresses/` (create, PATCH, `/{id}/default`, DELETE)

## Antes da tarefa (mesma sessão)
- front #3 fechada (resolvida pelo PR #14, `99c8de6`)
- back PR #33 (pydantic-settings 2.15.0) mergeado → `6ba65aa`

## Mudanças
- `services/client.ts`: create/update/setDefault/delete de endereço tipados; `types/domain.ts` com complement/neighborhood
- `lib/address.ts`: validação (CEP 8 dígitos, UF 2 letras, rua, cidade) e `toAddressPayload(values, mode)`
  — PATCH envia `null` em opcionais vazios (backend usa `exclude_unset`); POST omite
- `features/account/AddressForm.tsx` + `AddressManager.tsx`: listar, criar, editar, definir padrão, excluir (com confirm)
- `features/cart/CartPage.tsx`: sem endereço, formulário inline; o criado fica selecionado;
  trocar/atualizar endereço zera preview e frete
- `App.tsx`: `refreshAddresses` atualiza a lista sem reload
- Primeiro endereço é criado com `is_default=true`

## Achados da revisão (todos corrigidos no 2º ciclo)
- P2 opcionais não podiam ser apagados na edição
- P2 preview/frete do endereço anterior sobrevivia à troca de lista
- P3 falha ao atualizar a lista após salvar: rejeição não tratada e risco de endereço duplicado
  (agora o retry só repete o refresh, sem novo POST/PATCH)

## Verificação
- `npm run build` ok; `npm test` 13/13; `git diff --check` ok
- Não testado no navegador; sem teste de componente para o retry do formulário

## Pendente
- Commit/push/PR quando o usuário pedir; E2E cadastro → endereço → checkout fica para a issue de testes
- Front #2 (refresh/cookie HttpOnly) aguarda decisão de arquitetura; exige issue e PR próprios no backend
