# Launch-readiness audit — Ecommerce Atacadão

**Date:** 2026-10-03  
**Scope:** `EcommerceAtacadao` API and `front_atacadao` storefront, assessed for a production launch targeted in two months.  
**Verdict:** **changes_required** — do not launch until every urgent item has a verified remediation.

## Objective and acceptance criteria

Catalogue launch risks without changing product code. A launch-ready release must allow a new customer to register, create an address, complete and recover a payment flow safely; protect sessions and public endpoints; preserve inventory/payment integrity; and be reproducibly tested, deployed, monitored, and reversible.

## Scope and method

Three read-only specialists reviewed the code in parallel:

| Specialist | Focus | Result |
| --- | --- | --- |
| Backend/security | FastAPI, identity, checkout, payment, data integrity | 12 findings |
| Frontend/quality | storefront flows, API consumer contract, UX, client security | 11 findings |
| Release/operations | test automation, dependencies, deployment, observability | 11 findings |

Static quality analysis was also run. Its backend estimates (17% test coverage) are directionally useful, but its hard-coded-secret and SQL-injection detections include confirmed false positives, so they are not listed as defects. Frontend production build passed. No full backend test run, dependency vulnerability scan, deployment, database migration, or external-service test was performed: the audit was read-only and the environment does not expose a safe test database. Absence of a finding is not proof of absence.

## Urgent — resolve before launch

| ID | Problem and evidence | Launch impact | Suggested solution | Primary owner |
| --- | --- | --- | --- | --- |
| U1 | A newly registered customer cannot add an address. The storefront only lists addresses (`front_atacadao/src/services/client.ts:75`, `src/App.tsx:31`), while checkout requires one (`src/features/cart/CartPage.tsx:13-16`). The API already provides address create/update endpoints (`EcommerceAtacadao/src/api/v1/endpoints/identity/addresses.py:35-81`). | New customers cannot calculate shipping or pay. | Add authenticated address create/edit/default UI and API client calls; cover registration → address → checkout with E2E tests. | Frontend + API contract |
| U2 | Refresh-token rotation is raceable. The service checks then revokes a token (`EcommerceAtacadao/src/services/identity/auth_service.py:103-119`), while the repository uses an unlocked select and independent commit (`src/repositories/identity/refresh_token_repository.py:20-33`). | Concurrent replay can mint more than one valid token pair. | Atomically claim the token with `FOR UPDATE` or conditional update; create its successor in the same transaction; add a concurrent-refresh test. | Backend/security |
| U3 | The client stores access and refresh JWTs in `localStorage`, has no refresh API call, and logs out on every 401 (`front_atacadao/src/App.tsx:12-31`, `src/services/client.ts:68-98`; documented in `README.md:25`). | XSS can steal the long-lived bearer token; normal token expiry interrupts checkout and order recovery. | Move refresh token to Secure, HttpOnly, SameSite cookie; keep access token in memory; add one refresh-and-retry path and CSP/XSS hardening. | Frontend + backend/security |
| U4 | An approved Mercado Pago transaction can remain without committed stock: failures from reservation confirmation are caught after the transaction becomes approved (`src/services/sales/mercado_pago_service.py:192-202`; repository validation at `src/repositories/sales/order_repository.py:284-299`). | A customer can be charged for an unfulfillable order, with no durable automatic compensation/reconciliation path. | Define an explicit approved-but-unfulfillable state with durable reconciliation, alerts, and an agreed refund/fulfillment policy; test delayed webhook and stock-conflict paths. | Backend/security + release/operations |
| U5 | No rate limiting/abuse guard exists for login, registration, shipping, payment initiation, or webhook routes (`src/api/v1/endpoints/identity/auth.py`, `operations/shipping.py`, `sales/checkout.py`). | Credential stuffing, provider-cost abuse, denial of service, and webhook brute-force risk. | Apply edge/API route limits, request-size limits, webhook signature/IP controls, and alerts for threshold breaches. | Backend/security + release/operations |
| U6 | Neither repository has CI/CD workflows (`.github/` absent); the frontend has no test files and only dev/build/preview scripts (`front_atacadao/package.json:6-10`). | Regressions, dependency changes, and migrations can reach production without a quality gate. | Add protected-main CI: locked installs, lint/typecheck, backend unit/integration tests, frontend component/E2E tests, dependency scanning, and an approved migration job. | Release/operations + frontend/backend |
| U7 | Authenticated product-review/question creation trusts author and moderation fields supplied by the client. The generic factory authenticates but forwards the payload unchanged (`src/api/v1/endpoints/catalog/_crud_factory.py:71-79`); review schemas/services expose and persist `user_id`/`is_approved` (`schemas/catalog/product_review_schema.py:6-13`, `services/catalog/product_review_service.py:11-19`) and question paths expose `user_id`/`answer_text` (`schemas/catalog/product_question_schema.py:30-37`, `services/catalog/product_question_service.py:43-53`). | Any logged-in user can impersonate an author, self-approve a review, or publish a fake vendor answer. | Remove author/moderation fields from creator schemas; set author server-side; make approval and answers admin-only; add spoofing and visibility tests. | Backend/security + frontend contract |

## Medium risk — complete in the two-month launch window

| ID | Problem and evidence | Risk | Suggested solution | Primary owner |
| --- | --- | --- | --- | --- |
| M1 | Payment starts by persisting order/reservation before gateway configuration and remote order creation (`mercado_pago_service.py:74-92`). A provider/config failure leaves an unusable pending order and reserved stock. | Inventory is temporarily withheld and recovery is unclear. | Validate payment configuration before checkout; add retryable attempt states, expiry cleanup, customer recovery messaging, and provider-failure tests. | Backend/security |
| M2 | Refresh-token rows retain raw bearer JWTs (`auth_service.py:79-84`, `refresh_token_repository.py:20-24`). | Database/log exposure grants token use for its lifetime. | Store only a keyed hash/digest, look up by digest, and revoke/migrate existing raw-token rows. | Backend/security |
| M3 | Core payment/stock races are not proven by DB-backed tests: concurrent checkout, expired reservation, cancel-vs-webhook, provider failure recovery, and webhook signature HTTP behavior are absent. | Revenue/inventory invariants are unverified. | Add isolated PostgreSQL integration tests using separate sessions and mocked providers for every listed race/failure case. | Backend/security + release/operations |
| M4 | Listing limits are caller-controlled and unbounded in users, orders, and generic catalogue resources (`identity/users.py:45-55`, `sales/order.py:21-30`, `catalog/_crud_factory.py:83-95`). | Public/authenticated callers can amplify database and response load. | Enforce bounded `Query` limits and pagination/cursors; add maximum-limit contract tests. | Backend/security |
| M5 | Retrying a payment already in `MERCADO_PAGO_PREPARING` can hold `FOR UPDATE` through remote I/O (`order_repository.py:68-71`, `mercado_pago_service.py:78-91`). | Lock contention and timeouts during provider slowness. | Release DB locks before network calls; coordinate retries through a persisted attempt lease/state. | Backend/security |
| M6 | The deploy/migration procedure is manual and incomplete (`EcommerceAtacadao/README.md:37,49-50`): no environment matrix, backup, rollback test, smoke check, or owner. | Unsafe migration/deployment and slow incident recovery. | Version a runbook with owners, environment matrix, backup, staging migration rehearsal, smoke checks, and rollback steps. | Release/operations |
| M7 | The health endpoint is liveness-only (`src/main.py:67-71`); there is no structured request logging, metrics, tracing, error tracker, checkout/webhook alerts, or dashboard. | Failures can be invisible until customers report them. | Add protected readiness checks, structured logs/request IDs, error tracking, metrics, dashboards, and alert thresholds. | Release/operations |
| M8 | Vercel/serverless deployment is documented, but DB uses a per-runtime pool of up to 15 connections without pre-ping/serverless strategy (`src/core/db.py:9-15`). | Connection exhaustion or stale connections under scale. | Use provider-compatible pooling or `NullPool`, set an explicit connection budget, enable safe stale-connection handling, and load-test it. | Release/operations + backend |
| M9 | Mercado Pago and Melhor Envio have timeouts but no bounded retry policy, circuit breaker, provider monitoring, or reconciliation job (`integrations/mercado_pago/client.py:50-84`, `integrations/melhor_envio/client.py:57-92`). | Provider incidents become synchronous customer failures with weak recovery. | Add idempotent bounded retries, circuit breaking, safe telemetry, webhook/reconciliation worker, and outage alerts. | Release/operations + backend |
| M10 | Frontend dependencies are declared as `latest` (`front_atacadao/package.json:12-20`). | Fresh installs can select unreviewed breaking majors; CI cannot catch them today. | Pin compatible versions/ranges, require `npm ci`, and use controlled automated dependency updates with audit checks. | Release/operations |
| M11 | Backend integration tests require a running PostgreSQL/API but no reproducible service/fixture configuration is tracked; frontend lacks component/contract/E2E tests. | The release suite cannot validate the launch journey deterministically. | Supply ephemeral PostgreSQL in CI, deterministic fixtures, mocked integrations, Vitest/RTL, and Playwright launch-flow coverage. | Release/operations + frontend/backend |
| M12 | Storefront catalog requests at most 100 items and renders initials instead of product images (`src/services/client.ts:75`, `src/features/catalog/CatalogPage.tsx:16`). | Incomplete catalog and weak merchandising at scale. | Implement paginated catalogue/search and display validated image URLs with accessible image fallbacks. | Frontend + API contract |
| M13 | Cart uses a global busy flag for all mutations (`CartPage.tsx:8,11-16`), with only a global error notice. | One slow item blocks the cart and recovery is poor. | Track pending/error state per item and action; preserve retry affordances and refresh cart state after conflict. | Frontend |

## Low risk — schedule after launch blockers are stable

| ID | Problem and evidence | Risk | Suggested solution | Primary owner |
| --- | --- | --- | --- | --- |
| L1 | `/users/me` writes user email and role with `print` (`src/api/v1/endpoints/identity/users.py:30`). | Unnecessary PII in production logs. | Remove the print; use redacted structured logging only where operationally necessary. | Backend/security |
| L2 | Product image validation accepts HTTP URLs (`src/services/catalog/product_image_service.py:14-15,29-30`). | Mixed content and third-party content/privacy risk. | Require HTTPS and preferably allowlisted/object-storage hosts; add URL validation tests. | Backend/security + frontend |
| L3 | Seed code embeds and prints predictable administrator/customer credentials (`scripts/seed.py:78-79,904-914`). | Accidental use outside an explicitly protected local environment creates exposed accounts. | Require explicit local-only confirmation; generate credentials securely and never print passwords. | Backend/security + release/operations |
| L4 | Fetch has no timeout/cancellation (`front_atacadao/src/services/client.ts:47-67`), and catalogue failure tells the user only to reload (`CatalogPage.tsx:11,16`). | Requests may appear to hang and recovery is weak. | Use `AbortController` timeouts/cancellation and actionable retry/offline UI. | Frontend |
| L5 | Account error handling can present an empty-order state after an order-fetch failure (`src/features/account/AccountPage.tsx:12,15`). | Outage can be mistaken for no purchase history. | Keep error state distinct from empty state and provide retry without hiding existing data. | Frontend |
| L6 | The admin catalogue editor accepts opaque raw JSON and deletion uses only browser confirmation (`src/features/admin/AdminPage.tsx`). | Operator mistakes are more likely. | Replace raw JSON with schema-aware forms, validation preview, and stronger destructive-action confirmation/audit trail. | Frontend + backend |
| L7 | Store configuration contains placeholder/support copy and identifies itself as a portfolio (`front_atacadao/src/config/store.ts`, `src/components/Layout.tsx`). | Public-facing credibility and support-routing issue. | Replace placeholders with approved brand, legal, and support contact content before staging. | Frontend |
| L8 | Development documentation drifts from reality: project architecture references Python 3.12 and `app.*`, while code is `src` and `pyproject.toml` supports Python 3.11+. | Incorrect setup and maintenance commands. | Align documentation with tested runtime, package paths, and exact quality commands; review it in CI. | Release/operations |
| L9 | Frontend has no dedicated lint/format/typecheck scripts; backend Ruff rules cover only E/F/I (`front_atacadao/package.json:6-10`, `EcommerceAtacadao/pyproject.toml:54-55`). | Fewer automated code-quality protections. | Add lint/format/typecheck scripts and expand backend rules gradually with a documented baseline. | Release/operations |

## Three-agent delivery plan: parallel pipeline with minimal coordination

Each agent owns one specialty and creates focused, independently reviewable changes. Work is grouped by contract dependency, not by directory, to prevent duplicate investigation and token-heavy handoffs. A shared issue is assigned to both agents only at an explicit API contract gate.

| Pipeline stage | Agent and specialization | Work items | Dependency / handoff |
| --- | --- | --- | --- |
| 0 — contract gate (half day) | **Agent A: backend & transactional security** | Define versioned refresh-cookie/rotation behavior; address CRUD contract; payment/reconciliation state transitions; rate-limit response semantics. | Publish a one-page API contract and fixtures. No implementation until Agent B confirms consumer needs. |
| 1 — parallel foundations (weeks 1-2) | **Agent A: backend & transactional security** | U2, U4, U5, U7; M1-M5; L1-L3. Add PostgreSQL concurrency/integration tests with each invariant. | Delivers stable auth, address, checkout/payment, and review/question contracts plus test fixtures. |
| 1 — parallel customer journey (weeks 1-2) | **Agent B: frontend experience & client security** | U1, U3; M12-M13; L4-L7. Build address management, refresh/retry behavior matching Agent A’s contract, per-item cart states, robust errors, and storefront tests. | Uses Agent A’s contract/fixtures only; reports any contract gap once, in structured form. |
| 1 — parallel release foundation (weeks 1-2) | **Agent C: release engineering & reliability** | U6; M6-M11; L8-L9. Establish CI, deterministic test database, locked installations, dependency scanning, staging/prod release and rollback runbook, readiness/telemetry baseline. | Supplies CI matrix and a production-like test target to A/B. |
| 2 — integration gate (week 3) | **A + B, reviewed by C** | Run register → address → cart → shipping → Mercado Pago redirect/return → refresh → order-history journey and adversarial/race cases. | C blocks promotion until the CI evidence is retained; defects return to the owning agent only. |
| 3 — hardening/rehearsal (weeks 4-6) | **A/B in parallel; C coordinates** | Complete medium-risk backlog; load-test pool/rate limits; payment provider outage and delayed-webhook drills; migration backup/rollback rehearsal. | Freeze HTTP contracts after this point except for P0 security fixes. |
| 4 — launch gate (weeks 7-8) | **C as release owner; A/B on call** | Staging smoke test, migration verification, alert test, dependency review, accessibility/mobile pass, production go/no-go checklist. | Launch only if U1-U7 are closed, medium items have accepted mitigations, and rollback is rehearsed. |

### Issue allocation

| Agent | Primary issues | Shared gates |
| --- | --- | --- |
| A — backend & transactional security | U2, U4, U5, U7, M1-M5, L1-L3 | U1/U3/U7 contract with B; U6/M3/M8/M9/M11 with C |
| B — frontend experience & client security | U1, U3, M12-M13, L4-L7 | U1/U3 with A; U6/M11 with C |
| C — release engineering & reliability | U6, M6-M11, L8-L9 | U4/U5/M3/M8/M9 with A; U6/M11 with B |

### Definition of done for every pipeline item

1. A short acceptance test is added at the layer that can fail (unit, API contract, database integration, or E2E).
2. CI runs it against locked dependencies and, where needed, ephemeral PostgreSQL plus mocked external providers.
3. Agent C records test evidence, release impact, monitoring/alert behavior, and rollback path.
4. A reviewer validates the integrated diff with special attention to ownership, token lifecycle, payment idempotency, stock reservation, and no secrets/PII in logs.

## Verification record

- `front_atacadao`: production build passed (`npm run build`; Vite 8.3.0, 26 modules).
- Both Git worktrees were clean before the audit; this Markdown report is the only audit artifact added. No product code or configuration was changed.
- Backend analyzer reviewed 132 Python files and estimated 17% coverage. Its automated secret/SQL findings were manually triaged and not treated as confirmed vulnerabilities.
- Dependency CVE scans and full backend tests remain unverified; they must be run in CI with network access and an isolated test database before a launch decision.

## Remaining risk

The urgent list is intentionally strict because this product handles identities, inventory, shipping, and payment. The payment/reconciliation path deserves an explicit business owner decision: automatic refund, fulfillment exception, or a manual operations queue are materially different policies. That decision is required before U4 can be closed.
