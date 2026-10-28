# Menagerist - Frontend

Static SPA served by the backend process itself (`entrypoints/api/spa.py` in `backend/`). API calls go through `/api/*` on the same origin.

Coding conventions (British English, comment style, dependency policy) are in [AGENTS.md](../AGENTS.md#general-rules) - nothing frontend-specific to add here.

## Stack

- [SvelteKit](https://svelte.dev/docs/kit) (static adapter) + Svelte 5
- [Tailwind CSS v4](https://tailwindcss.com) + [shadcn-svelte](https://shadcn-svelte.com) + [bits-ui](https://bits-ui.com)
- TypeScript
- Typed API client auto-generated from the backend's OpenAPI schema via [`@hey-api/openapi-ts`](https://heyapi.dev)

For UX and UI rules, see [DESIGN_GUIDELINES.md](DESIGN_GUIDELINES.md).

## Key patterns

**Reactivity** - Svelte 5 runes throughout (`$state`, `$derived`, `$effect`). No global stores except singleton controllers (`src/lib/theme.svelte.ts`, `src/lib/capture.svelte.ts`, `src/lib/search-palette.svelte.ts`).

**API client** - generated types and functions live in `src/lib/api/generated/`. Never edit those files by hand. Import everything through `src/lib/api/client.ts`.

**Routing** - file-based SvelteKit routing, client-rendered only (no `+page.server.ts`). Data is fetched inside components via the API client.

**Paths** - always use `resolve()` from `$app/paths` when building internal hrefs so the app works under a non-root base path.

**Component choice** - prefer an existing shadcn-svelte/bits-ui component over a hand-rolled native HTML element when one exists and fits (`npx shadcn-svelte@latest add <component>` from `frontend/`, then `npx prettier --write` the new files to match house style - the registry ships double-quoted, unformatted source). Check `src/lib/components/ui/` first; most primitives (`Button`, `Input`, `Select`, `DropdownMenu`, `Popover`, ...) are already there. Native elements are still the right call where they're genuinely better: `<input type="file">` (no shadcn equivalent, and none is needed), a `<table>` for genuinely tabular data, or a custom control (the rating field's `role="radiogroup"` star row, image-overlay buttons in `media-gallery.svelte`) that would need heavy style overrides to force into a generic component anyway. When in doubt, match whatever the surrounding file already does.

**Keyboard shortcuts** - register every shortcut through `src/lib/shortcuts.svelte.ts` (`registerShortcut` inside a component `$effect`, returning its cleanup); never add a bare `window` `keydown` listener. One listener, attached once by the root layout (`attachShortcuts`), reads the registry at key-press time, and the `?` overlay lists whatever is registered. Shortcuts are skipped while typing in a field or inside a dialog, listbox or menu unless they set `allowInInputs`. See `docs/DECISIONS.md` for why the registry is built this way.

**Schema-driven attributes** - node and edge types carry an `attributes_schema` (JSON Schema 2020-12). The backend validates attribute payloads against this schema on every write. The frontend renders schema fields using a pluggable field-type registry (`src/lib/field-types/`): each field type owns its schema serialisation (`toSchema`/`fromSchema`), its edit widget (`InputWidget`), and an optional read-mode widget (`ViewWidget`). Adding a new field type requires only a descriptor file and one import line - no changes to the editor components. See [docs/field-types.md](../docs/field-types.md) for the full guide.

**Authentication** - `src/lib/auth.svelte.ts` is a runes singleton (`auth`) holding the signed-in account, its permissions and `passwordExpired`. The root layout calls `auth.init()` (status, then `/auth/me`, then `/auth/me/permissions` unless the password has expired), renders pages only once the route guard allows them, and redirects with the pure `guardDecision()` in `src/lib/auth.ts` (setup required -> `/setup`; no session -> `/login?next=`; expired password -> `/settings/account`; `/login` and `/setup` are the only public routes). `safeNext()` keeps `?next=` to same-origin paths. Use `auth.can('graph:node_type:delete')` (typed with the generated permission union) to hide admin-only controls; the server still enforces them. `src/lib/api/auth-interceptor.ts` reports a 401 (once) or a `password_expired` 403 to the controller, which the guard turns into a redirect. Signing in or out clears the ETag/body cache so nobody sees the previous person's cached responses. Signing out clears local state first, so the guard shows `/login` at once, and finishes the logout request in the background (`keepalive`); if the server did not end the session the true state is reloaded and the menu shows an error. No password is stored client-side; the session is an HttpOnly cookie.

**Examples** - Settings > Examples (`src/routes/settings/examples/`) adds and removes the shipped example packs. Home links to it from the empty state and shows a dismissible line while examples are installed. The wording helpers (counts, removal messages, dismissal in `localStorage`) live in `src/lib/examples.ts` so they can be unit tested.

**Collections** - `/collections` lists collections (with a search box that also takes `?q=`) and creates them, and `/collections/[id]` shows one: its items (the shared item cards, with search, list and grid views, and the Examples filter), rename and delete, an Add items dialog (`lib/components/add-items-dialog.svelte`) and Remove with Undo. The item page has a Collections card (`lib/components/item-collections.svelte`). Wording and error messages live in `src/lib/collections.ts`. Smart collections (a saved search; `kind === 'dynamic'`) are saved from the items page (`lib/components/save-smart-collection-dialog.svelte`) and show a Smart badge. Their page lists the saved conditions as locked chips (`smart-conditions.svelte`), runs `POST /node/search` with the saved sort (`lib/smart-collections.ts`) and offers **Edit conditions** (explicit Save and Cancel), no add or remove controls, and a narrowing layer: the search box, type select and **Filter** button AND ad-hoc conditions onto the saved ones (`lib/query/narrow.ts`, URL `?f=`/`?q=`/`?type=`), with a bar (`narrowed-bar.svelte`) to save as new, save as new and linked (`in collection <this>` plus the filters, `linkedNarrow`; also the only save on a manual collection narrowed by search text or type), update the collection after a confirmation, or clear. The builder also has Description, Name, Media and In collection rows (the collection picker is chips plus a combobox fed by `fetchAllCollections`, with a Retry when the read fails) and a Connection row (`query-connection-input.svelte`: relationship and direction selects, a server-searching item picker for "Is connected to", and a nested "Where the linked item…" group that cannot hold another connection; lookups come from `ConnectionLookups`). A capped count shows "1,000+" and `collection-count.svelte` (`lib/exact-count.svelte.ts`) fetches the exact figure in the background, with **Count exactly** as the retry. Collections are linked by slug (`collectionRouteParams`, which falls back to the id for an old slug that reads as one; `collectionAddress`; an id address is replaced by the slug), but once the page has loaded every API call goes by `collection.id`, after one reload by id, so the path-keyed ETag cache has a single entry per collection and definition saves carry `If-Match`, and the edit dialog has a Slug field (`collection-slug-field.svelte`). The item page's collection lists ask the server for `kind=manual` (`manualCollections` stays as a guard). A stored definition the server could not return arrives as `definition: null` and shows the unreadable-conditions message with its warning. The items page's **Save as smart collection** saves the filter, search box and type select together (`combineWithSaved`). The e2e specs are `tests/e2e/smart-collections.spec.ts` and `tests/e2e/smart-collection-conditions.spec.ts`, `tests/e2e/smart-collections-connections.spec.ts` (`E2E_BULK=1` adds a 1,003-item exact-count run). The collection page deliberately does not share its list code with the items page; keep the search debounce and the paging in step if you change either.

**Search popup** - `/` opens `lib/components/search-palette.svelte`, a grouped search over Items, Collections, Item types and Pages (in that order, capped per group). `lib/palette-sources.ts` (`searchEverything`) fans out to the API and filters item types and pages locally; `lib/palette-search.ts` ranks each group and `lib/search-palette.ts` holds the pure view and live-region logic. A full Collections group ends with a "See all collections" row that opens `/collections?q=...`. A failed source shows a retry row for that group only; "Nothing found" appears only when every source answered and all were empty. Matching is accent-insensitive on the server and in the local filters (`lib/fold-text.ts`); item types are paged in by cursor, up to 1000.

## Development

Install dependencies and generate the API client first (run from the repo root):

```sh
poe sync          # installs backend + frontend deps and generates the API client
```

Then start the dev server (proxies `/api/*` to `localhost:8000`):

```sh
poe serve-frontend   # from repo root
# or
npm run dev          # from this directory
```

The backend must be running separately for API calls to work:

```sh
poe serve         # from repo root, or use docker compose up
```

## API client

The typed client lives in `src/lib/api/generated/` and is **auto-generated** - do not edit those files by hand.

To regenerate after backend schema changes:

```sh
poe generate-frontend-client   # from repo root
# or
npm run generate               # from this directory (requires openapi.json to exist)
```

The schema dump step (`poe dump-schema`) writes `frontend/openapi.json`, which the generate step reads.

## Quality checks

```sh
poe typecheck-frontend   # svelte-check + tsc
poe lint-frontend        # prettier + eslint
poe test-frontend        # Vitest unit tests
poe build-frontend       # production build
poe check                # all of the above (from repo root)
```

### Testing

Vitest tests live in `frontend/tests/*.test.ts` (not colocated with components) and run in a Node, not browser, environment - there's no component-rendering test setup here, only unit tests against plain exports (including a `.svelte` file's `<script module>` exports, e.g. `attributes-editor.svelte`'s `attributesToRows`/`rowsToAttributes`).

`vitest.config.ts` aliases `@lucide/svelte` and `bits-ui` to stubs in `tests/mocks/`. Without them, importing anything that pulls in those packages adds well over a minute per run: Vitest's Node/SSR transform has no browser-style dep pre-bundling, so their large module graphs (thousands of icon exports; floating-ui/melt internals) get compiled file-by-file every run instead of being pre-bundled once. If a test starts failing with a missing export from either package, add the missing name to the relevant stub file - don't remove the alias.

**`$effect` does not run under Vitest.** The config uses Svelte's server build, where `$effect` is a no-op, so effect timing and ordering cannot be unit-tested here. Keep logic in plain, exported functions and cover effect-driven behaviour (shortcut registration, focus, navigation) with the Playwright suite in `frontend/tests/e2e/`.

### End-to-end tests

Playwright specs live in `frontend/tests/e2e/` and run in parallel workers, each with its own backend (ports 8100 + worker index, serving the production build in `frontend/build`) and its own database in a throwaway Postgres, so they never touch a dev or deployed stack on 8000/5173. Import `test`/`expect` from `./fixtures`, not `@playwright/test`: it routes `page` and `request` to the worker's backend. Specs must not assume an empty database or any order between files. `poe sync` downloads the Chromium build; on Linux run the one-off command printed by `poe install-e2e-deps` for its system libraries. Wait for a page to settle (a heading, or the Edit button) before pressing keys: pages register their own shortcuts as they mount. The session-cookie specs (`cookies.spec.ts`) run separately with `poe test-e2e-cookies`, in three engines behind a TLS proxy. Worker count (`--workers`), `--skip-build`, ports and the single-spec workflow are in [CONTRIBUTING.md](../CONTRIBUTING.md#end-to-end-tests).

Specs run signed in: the fixtures sign each worker in as a stable administrator (first-run setup on a fresh database, otherwise login) and give `page`, `context` and `request` the session cookie (`request` also sends the app's `Origin`), so specs need no auth code. For a second person use `createUserViaApi` and `asUser` from `helpers.ts`; `browser.newContext()` starts as the worker admin, so pass explicit `storageState` for anyone else. `auth.spec.ts` and `isolation.spec.ts` cover sign-in, first-run setup and cross-user isolation; the `auth` project runs `auth.spec.ts` against its own backend (port 8190, database `menagerist_auth`). Details in [CONTRIBUTING.md](../CONTRIBUTING.md#end-to-end-tests).

A second Playwright project, `mobile` (Pixel 5 emulation at 360x740, touch enabled), reruns the viewport-agnostic specs (`collections`, `create-item`, `connect-items`, `quick-capture`) on a phone and adds the phone-only `*.mobile.spec.ts` files (the `chromium` project ignores those). `examples` is desktop-only (slow, little added on a phone). Both projects share the worker pool and databases, so a spec must not rely on other files' data and should clean up what it creates. Run it alone with `npx playwright test --project=mobile`. Keep specs viewport-agnostic: use `openNav(page, 'Collections')` from `helpers.ts` to follow a main navigation link (top bar on desktop, bottom bar on a phone) and `openQuickCapture` (shortcut on desktop, the New button on a phone); use `test.skip(({ isMobile }) => isMobile, 'reason')` only where a test genuinely cannot run on a phone, and `test.fail` with a reason for a known app bug so the test turns red once it is fixed. Keyboard-shortcut, field-type, item-type and set-item-type specs are desktop-only for now.

## Building

```sh
npm run build
```

Output goes to `build/`. In production this is copied into the `menagerist` image by the root `Dockerfile` and served by the backend process itself (`MENAGERIST_API_FRONTEND_DIST_PATH`).
