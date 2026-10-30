# Quickstart: produtos do site como anúncios do Bling

## 1. Criar a loja do site no Bling (uma vez por cliente)
1. No Bling, Central de Extensões → **API** → instalar. Dê um nome (ex.: "Loja do site").
2. Anote o **ID da loja** (aparece em `GET /canais-venda` com `"tipo": "Api"`; na demo de teste: 206347377).
3. Configure `BLING_STORE_ID=<id>` no deploy do cliente (Vercel, environment production) e redeploy.

## 2. Permissões do app OAuth do Bling
O app do cliente precisa de: leitura de produtos, categorias, estoques, canais de venda e vínculos produto–loja, e **escrita de vínculos produto–loja** (para o preço). Depois de mudar os escopos no Bling, reconecte o Bling no admin do site (Bling → Reconectar).

## 3. Publicar um produto no site
1. No Bling, abra o produto → aba de lojas/multiloja → vincule à loja do site e preencha o **preço da loja**.
   - Vínculo no produto pai: todas as variações entram com esse preço.
   - Vínculo numa variação: só ela entra, com preço próprio (prevalece sobre o do pai).
2. Aguarde a sincronização (até 10 min) ou use "Sincronizar agora" no admin.
3. No admin do site, Produtos:
   - confirmação automática ligada: o produto já está na loja com a linha de 1 unidade;
   - desligada: o produto aparece como "aguardando preços" → abra, acrescente faixas se quiser e **Confirmar**.

## 4. Mudar preço
- Pelo site: edite a linha de 1 unidade da variação → o site grava no vínculo do Bling antes de salvar (se a variação herdava o preço do pai, ganha vínculo próprio).
- Pelo Bling: mude o preço do vínculo → a próxima sincronização atualiza a linha de 1 unidade; as faixas não mudam (aviso se alguma ficar igual ou acima).

## 5. Tirar do site
Remova o vínculo com a loja do site no Bling (ou inative o produto). As faixas ficam guardadas no site e voltam se o vínculo for recriado.

## Validação local
- Back: `uv run pytest` com Bling simulado (`tests/integrations/`), env fictícias e Docker descartável (`skills/ecommerce-atacadao/references/development.md`).
- Front: `npm test`, `npm run build`.
