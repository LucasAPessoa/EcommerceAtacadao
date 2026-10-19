# Research: Integração com o Bling (conexão da conta)

Fontes: documentação oficial da API v3 (`developer.bling.com.br/aplicativos`, `developer.bling.com.br/limites`), consultada em 2026-10-18. O app OAuth ainda não pôde ser criado (o cadastro trava ao salvar), então tudo marcado **[a validar]** depende de uma chamada real e deve ser confirmado antes do merge da implementação.

## R1. Fluxo OAuth e validades

- **Decision**: Authorization Code. Autorização em `https://www.bling.com.br/Api/v3/oauth/authorize?response_type=code&client_id=…&state=…`; troca e renovação em `POST https://www.bling.com.br/Api/v3/oauth/token` com `Authorization: Basic base64(client_id:client_secret)` e corpo form-urlencoded (`grant_type=authorization_code&code=…` ou `grant_type=refresh_token&refresh_token=…`). API em `https://api.bling.com.br/Api/v3`.
- **Fatos confirmados na documentação**: o código de autorização vale **1 minuto**; o refresh token vale **30 dias**; `redirect_uri` e `scope` enviados na requisição são **ignorados**, e valem os cadastrados no app; existe `POST /oauth/revoke` (Basic auth) para invalidar tokens; não há sandbox (tudo é produção, então o desenvolvimento usa uma conta Bling de teste).
- **[a validar]**: duração do access token (`expires_in` vem na resposta; a doc não fixa o número); se o refresh token **rotaciona** a cada renovação; suporte e devolução do parâmetro `state`; formato do token (a doc menciona migração para JWT).
- **Rationale**: o desenho assume o caso mais restritivo (refresh rotativo e de uso único). Isso funciona também se não houver rotação.
- **Alternatives considered**: nenhuma; é o único fluxo suportado pela API v3.

## R2. Redirecionamento OAuth com multitenant por deploy (decisão prioritária)

O app tem **um único** "link de redirecionamento" e o Bling ignora `redirect_uri`. Com um deploy e um domínio por cliente:

| Opção | Como funciona | Prós | Contras |
|---|---|---|---|
| A. Um app por cliente | Cada cliente tem um app Bling com o redirecionamento apontando para o próprio domínio | Sem serviço novo; isolamento total; credenciais do app também por cliente | ~15 min de cadastro manual por cliente (vira passo do provisionamento #65) |
| **B. App único + redirecionamento central** | O app aponta para um endereço fixo da plataforma, que repassa o `code` ao deploy certo usando o `state` | Um app só para manter | Serviço central novo (ponto único de falha); depende de `state` funcionar [a validar]; o código vale só 1 minuto, então o repasse precisa ser imediato |

- **Decision**: **B — app único com redirecionamento central** (aprovado pelo usuário em 2026-10-18), com estas condições:
  - O redirecionador é **sem estado**: não tem banco, não guarda o `code` e não chama o Bling. Ele só valida o `state` e devolve um 302 para o callback da loja.
  - O `state` é gerado pela loja: `base64url(tenant_id, nonce, exp)` + HMAC-SHA256 com a chave da loja (`BLING_STATE_SIGNING_KEY`). O redirecionador conhece as chaves e os callbacks numa **lista fixa de clientes** (env `PLATFORM_TENANTS`), então só redireciona para domínios cadastrados.
  - Se ele ficar fora do ar, só **novas conexões** param; as conexões existentes seguem, porque cada loja renova direto com o Bling.
  - Cada deploy precisa do `client_secret` do app único. Se ele vazar, o segredo é rotacionado no Bling e atualizado nos deploys; tokens de outras contas continuam inacessíveis.
- **Gate [a validar primeiro]**: o Bling precisa devolver o `state` no redirecionamento. Se não devolver, cai a opção B e volta a A (um app por cliente); o código da loja é o mesmo nos dois casos, só o link cadastrado muda.
- **Rationale**: um app para cadastrar e homologar, controle central de clientes, entrada de cliente novo sem passo manual no Bling e base para o roteamento de webhooks do pós-MVP.
- **Alternatives considered**: A (um app por cliente), mantida como plano B pelo gate acima.

## R3. Limites de requisição

- **Fatos confirmados**: **3 req/s** e **120.000 req/dia por conta Bling** (não por app nem por endpoint); excesso devolve **HTTP 429**. Existe também bloqueio por IP, um mecanismo separado.
- **Decision**: limitador por conta no próprio cliente HTTP, com folga (2,5 req/s) e espera quando o limite é atingido. Como cada deploy fala com uma única conta, o limitador pode ser por processo.
- **[a validar]**: se o 429 traz cabeçalho de espera (`Retry-After` ou similar).
- **Risco**: em serverless, instâncias paralelas do mesmo deploy somam requisições. Mitigação: o Redis do rate limit já existe; se o 429 aparecer na prática, o limitador passa a ser compartilhado via Redis (decisão adiada; registrar no plano da 004).

## R4. Retry e classificação de erros

- **Decision**: retry só para 429, 5xx e falha de rede/timeout; até 4 tentativas com espera exponencial e jitter (1s, 2s, 4s, 8s). 4xx (exceto 429) não são repetidos. Os erros são entregues aos consumidores como: `NotConnected`, `ReconnectRequired`, `RateLimited` (após esgotar), `Unavailable` (após esgotar) e `BlingRejected` (4xx, com o tipo/mensagem do Bling sem dados sensíveis).
- **[a validar]**: formato exato do corpo de erro do Bling (a doc indica `{"error": {"type", "message", "description"}}`).
- **Alternatives considered**: retry ilimitado com fila, rejeitado porque a persistência do trabalho pendente é responsabilidade das features consumidoras (#54, #58, #60).

## R5. Renovação concorrente e "recusa definitiva"

- **Decision**: renovação sob lock de linha no banco (`SELECT … FOR UPDATE` na conexão da loja). Quem obtém o lock relê o token: se outro processo já renovou, usa o novo sem chamar o Bling. Renova quando faltam menos de 5 minutos para expirar ou após um 401 da API.
- **Recusa definitiva** = resposta `invalid_grant` / 400–401 no endpoint de token. Isso vira `RECONNECT_REQUIRED`. Falha de rede ou 5xx no token é passageira: tenta de novo e mantém `CONNECTED`.
- **Rationale**: o banco já é o ponto de serialização do projeto (locks de checkout); evita depender do Redis para corretude.

## R6. Proteção das credenciais

- **Decision**: criptografia simétrica autenticada (Fernet, pacote `cryptography`, nova dependência) com chave por deploy em `BLING_TOKEN_ENCRYPTION_KEY` (env sensitive na Vercel). Tokens nunca entram em logs, respostas ou mensagens de erro; o `client_secret` fica só em env.
- **Rotação da chave**: fora do MVP; o formato guarda a versão da chave para permitir rotação futura.
- **Alternatives considered**: pgcrypto no banco (a chave iria nas queries); KMS externo (custo e complexidade desnecessários no beta).

## R7. Identificação da empresa vinculada

- **Decision**: após a troca do código, consultar os dados da empresa e gravar identificador e nome. Na reconexão, comparar com a empresa vinculada (FR-012: só aceita a mesma).
- **[a validar]**: endpoint exato dos dados da empresa e campo identificador estável.

## R8. Proteção do callback (FR-002)

- **Decision**: o admin inicia a conexão e o servidor gera um `state` aleatório, de uso único, com validade de 10 minutos, gravado em `bling_authorization_attempts`. O callback exige um `state` válido e não usado, marca como usado e só então troca o código. Recarregar o callback não registra a conexão duas vezes.
- **Fallback [a validar]**: se o Bling não devolver `state`, o callback exige um admin autenticado com tentativa pendente recente (menos segura; aceitável só no beta).

## R9. Verificação periódica da conexão

- **Decision**: o job de manutenção existente (a cada 10 min) verifica a conexão: renova se estiver perto de expirar e faz uma chamada leve ao Bling. Isso detecta revogação em até ~10 min (SC-003) mesmo sem o sincronismo de catálogo, e mantém o refresh token (30 dias) sempre renovado.
- **Alternatives considered**: depender só do sincronismo (#54), rejeitado porque ele ainda não existe e o SC-003 deve valer desde já.

## R10. Alertas e eventos

- **Decision**: eventos em tabela própria (`bling_connection_events`) mais log estruturado. O alerta operacional usa o mecanismo da #12 quando existir; até lá, o aviso no painel e o evento bastam (suposição da spec).
