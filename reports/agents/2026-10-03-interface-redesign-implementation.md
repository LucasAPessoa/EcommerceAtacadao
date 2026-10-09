# Interface redesign implementation

## Objective and scope

Apply a modern, simple and customizable visual system to the complete `front_atacadao` application: home/catalog, cart, authentication, account, payment return and admin. Preserve the existing API contract and commercial authority of the backend.

## Acceptance criteria

- Orange logo identity is supported by an ink-and-parchment palette.
- A centralized store theme feeds all customer and authentication surfaces.
- Every current route remains usable at desktop and mobile widths.
- The UI does not claim unavailable features such as product reviews, real imagery, stock alerts, discounts or catalog filter endpoints.
- Build and whitespace validation pass.

## Design decisions

The design takes cues from a wholesale shelf, an order slip, a warehouse label, a replenishment list and a delivery handoff. It rejects generic gradient hero art, unsupported promotional navigation and uniform rounded SaaS cards.

The signature is the product quantity rail: a concise orange rule with factual unit pricing. It appears where purchasing choices are made, without fabricating wholesale tiers the API does not expose.

`src/config/store.ts` is now the theme contract. Its semantic values flow into CSS custom properties in the shared layout, including the auth route. `front_atacadao/.interface-design/system.md` records the durable design rules.

## Implementation summary

- Rebuilt the global stylesheet around semantic tokens, responsive layouts, visual hierarchy, native-control focus styles, motion reduction and shared component states.
- Updated the app shell to use the centralized theme and reduced navigation to supported journeys: home, catalog, the existing explanation section and admin for authorized users.
- Reworked catalog product cards and the home hero to use factual wholesale-oriented structure and intentional image fallbacks.
- Styled cart, account, payment return, authentication and admin as part of the same system, with the admin retaining a denser operational layout.

## Verification

`npm run build` and `git diff --check` passed in `front_atacadao`. The Vite production build compiled 26 modules successfully.

A browser pass was attempted at desktop and mobile widths, but the environment denied the local listener with `EPERM` for `127.0.0.1:5173`, including an approved outside-sandbox retry. The next verification should cover header search/navigation, catalog filtering, cart quantity and shipping selection, auth forms, account state, payment outcomes and admin editor/record lists in an environment that permits a local port.

## Risks and remaining work

The product endpoint still has no normalized storefront image field. Product cards intentionally use configurable typographic fallback tiles until image data is available. No backend or external-service mutation was required.
