# Menagerist - Frontend

Static SPA served by the backend process itself (`entrypoints/api/spa.py` in `backend/`). API calls go through `/api/*` on the same origin.

Coding conventions (British English, comment style, dependency policy) are in [AGENTS.md](../AGENTS.md#general-rules) - nothing frontend-specific to add here.

## Stack

- [SvelteKit](https://svelte.dev/docs/kit) (static adapter) + Svelte 5
- [Tailwind CSS v4](https://tailwindcss.com) + [shadcn-svelte](https://shadcn-svelte.com) + [bits-ui](https://bits-ui.com)
- TypeScript
- Typed API client auto-generated from the backend's OpenAPI schema via [`@hey-api/openapi-ts`](https://heyapi.dev)

For UI work, read the core rules and terminology in [DESIGN_GUIDELINES.md](DESIGN_GUIDELINES.md), then use its reading guide for the affected feature. Read the Key patterns below for frontend changes; load feature and testing sections only when relevant.

## Key patterns

**Reactivity** - Svelte 5 runes throughout (`$state`, `$derived`, `$effect`). No global stores except singleton controllers (`src/lib/theme.svelte.ts`, `src/lib/capture.svelte.ts`, `src/lib/search-palette.svelte.ts`, `src/lib/offline.svelte.ts`).

**API client** - generated types and functions live in `src/lib/api/generated/`. Never edit those files by hand. Import everything through `src/lib/api/client.ts`.

**Routing** - file-based SvelteKit routing, client-rendered only (no `+page.server.ts`). Data is fetched inside components via the API client.

**Type icons and colours** - `src/lib/type-icons.ts` is the curated set of Lucide icons an item type can use (a component map plus search words). The server stores only the icon's name and checks its shape, so this file is the one place that decides which icons exist; `tests/type-icons-lucide.test.ts` fails if a name is not in the installed `@lucide/svelte`. To offer another icon, import it there and add its search words. Colours are the shared palette in `shared/contracts/type-colours.json`; `TypeIcon` renders either, falling back to the package icon.

**Type picker** - `TypePicker` (built on `ui/combobox`, with rows from `buildTypeItems` in `src/lib/type-picker.ts`) is the only way to choose an item type; it creates a type inline through `createNodeType`.

**Paths** - always use `resolve()` from `$app/paths` when building internal hrefs so the app works under a non-root base path.

**Component choice** - fixed-choice value inputs default to `ui/native-select` (see [design §15](DESIGN_GUIDELINES.md#15-forms)); use a custom picker for searchable/rich options or open-ended categories, and a menu for actions. For other controls, prefer an existing shadcn-svelte/bits-ui component over a hand-rolled native HTML element when one exists and fits (`npx shadcn-svelte@latest add <component>` from `frontend/`, then `npx prettier --write` the new files to match house style - the registry ships double-quoted, unformatted source). Check `src/lib/components/ui/` first; most primitives (`Button`, `Input`, `Select`, `DropdownMenu`, `Popover`, ...) are already there. Native elements are still the right call where they're genuinely better: `<input type="file">` (no shadcn equivalent, and none is needed), a `<table>` for genuinely tabular data, or a custom control (the rating field's `role="radiogroup"` star row, image-overlay buttons in `media-gallery.svelte`) that would need heavy style overrides to force into a generic component anyway. When in doubt, match whatever the surrounding file already does.

**Layout and density** - desktop controls use the compact Rhea sizes; the 44px touch size is opt-in with Tailwind's `pointer-coarse:` variant (`tests/touch-sizes.test.ts` fails on a bare `h-11`, `min-h-11` or `size-11`). Every page wraps its content in `$lib/components/page.svelte` (`Page`) and picks a width: `fluid` (grids and tables, capped at 2200px), `reading` (`max-w-5xl`), `form` (`max-w-3xl`) or `narrow` (`max-w-sm`). Tile grids use `repeat(auto-fill,minmax(11rem,1fr))` so the column count follows the width. The root layout renders the app sidebar (`app-sidebar.svelte`; destinations and groups in `src/lib/manage-nav.ts`, expanded/rail/drawer state in `src/lib/sidebar.svelte.ts`) for signed-in users, and publishes a `PAGE_ALIGN` source so non-fluid pages sit against it.

**Dashboard data** - Home loads each block independently through `src/lib/dashboard-sources.ts`; the saved queries (newest, edited, month, photo, tidy-up rows) are `Query` values in `src/lib/dashboard.ts`, and links to the Items page use the same `?f=` token, so a dashboard count and the list it opens always agree. Counts come from `POST /node/search/counts` and `GET /node/count/types` (one request each; see the backend docs), never from counting a loaded page.

**Search** - `search-palette.svelte` is the single implementation. The root layout mounts it inline in the top bar for a mouse at 768px and wider (`inlineSearch` in `src/lib/viewport.svelte.ts`) and as the full-screen sheet otherwise; both share the same sources and result rows. E2E specs use `searchPopup`, `searchField` and `openSearch` from `tests/e2e/helpers.ts`.

**Collapsible groups and editors in dialogs** - group page content with `$lib/components/collapsible-section.svelte` (open state remembered per device through `src/lib/remembered.ts`); open heavy create/edit forms in `$lib/components/type-editor-dialog.svelte`-style dialogs that ask before discarding unsaved edits.

**Installable app** - the web app manifest is served by the backend at `/manifest.webmanifest` (`modules/system/domain/web_app_manifest.py`; the dev server proxies it) and linked from `src/app.html`, which also carries the `theme-color` and iOS home-screen tags. It makes Menagerist installable as a standalone window. Instances are served from the origin root, so its `id`, `scope` and `start_url` are `/`; do not change them once people have installed the app. The icons and screenshots it names live in `static/`. The install icons in `static/` are PNGs rendered from the mark by `poe generate-pwa-icons` (`scripts/generate_pwa_icons.py`, drawn with Pillow, which the backend already uses); the maskable and iOS icons are full-bleed squares, as the platform rounds them. `THEME_COLOURS` in `src/lib/theme.svelte.ts` is the title bar colour for each theme and is repeated in `app.html` and the backend manifest; `tests/pwa-manifest.test.ts` keeps `app.html` in step and `tests/e2e/pwa.spec.ts` checks the served manifest and asks Chromium whether the app is installable.

**Back and layers** - `components/back-layer.svelte` gives an open sheet, dialog or full-screen overlay one history entry (SvelteKit shallow routing: `pushState` with `page.state.layers`), so the system Back gesture closes it. `ui/responsive-dialog` mounts it for every dialog and sheet (pass `backLayer={false}` for one that manages its own history entries, as the Filters panel does); mount it by hand in any other overlay. It removes its entry when closed another way, and the root layout's `beforeNavigate` pops open layers before a link or redirect taken from inside a sheet proceeds (`src/lib/back-layers.ts`), so a navigation adds one entry, not two. `BackButton` uses `src/lib/in-app-history.ts`, which counts the app's own pages behind the current one, instead of `history.length`; a redirect that replaces the entry calls `replaceNext()` first. Component tests alias `$app/state` and `$app/navigation` to the stubs in `tests/mocks/`; the real behaviour is in `tests/e2e/back-behaviour.mobile.spec.ts`.

**Service worker** - `src/service-worker.ts` (SvelteKit's own worker support) is for resilience, not offline data. It precaches the build's immutable files and `static/offline.html`, answers those from Cache Storage, loads pages network-first and shows the offline page only when the server cannot be reached. `src/lib/service-worker/policy.ts` decides what it may touch: only same-origin GETs, never `/api/*`, so no API response, sign-in, admin page or media is ever stored (`tests/e2e/pwa.spec.ts` checks Cache Storage). Each build gets its own cache (`menagerist-shell-<version>`) and the new worker deletes the old ones when it activates. There is no `skipWaiting()` on install: `lib/service-worker-client.ts` registers the worker from the root layout, and a new version waits behind a "A new version is ready" toast until the person taps Reload, so an update never reloads a form they are still filling in. Visiting any page with `?reset-app-cache` unregisters the worker and deletes its caches, which is the way out of a bad worker. The backend serves `service-worker.js` with `Cache-Control: no-cache` (`spa.py`), so a fixed worker is picked up at the next check.

**Progress** - long operations report a snapshot (`ProgressSnapshotResponse`: phases, an overall percentage, a note) and `src/lib/progress.ts` holds the pure helpers that turn one into words (`headline`, `phaseText`, `stoppedAt`, `percentOf`) and `pollProgress`, which reads one request at a time until stopped. `progress-bar.svelte` (a labelled `ui/progress` with the percentage beside it) is the one bar; `progress-panel.svelte` adds the headline and a done / current / waiting phase list, whose state is also in words for screen readers, and announces only the phase, never the counts. The first-run restore page (`routes/setup`) polls `GET /backups/restore/progress` while its restore request is open and shows only a `running` snapshot, because a finished one would be an earlier restore's; before the first phase starts it says the backup is being received. The Scheduled tasks page shows a compact bar and the phase beside a running task, and where a task that did not finish stopped (`runProgressText` in `src/lib/scheduled-tasks.ts`). Phases counted in bytes show no counts (`unit`).

**Icon-only actions** - toolbar and row actions use `$lib/components/icon-button.svelte` (`IconButton`): icon plus tooltip on a mouse, icon plus visible label on touch, with the label always the accessible name. Buttons that commit or cancel a decision (Save, Cancel, Delete, Sign in) and empty-state calls to action keep their text. `IconButton` uses `ui/tooltip`, not `ui/popover-tooltip`, because a popover would swallow the tap on touch.

**Keyboard shortcuts** - register every shortcut through `src/lib/shortcuts.svelte.ts` (`registerShortcut` inside a component `$effect`, returning its cleanup); never add a bare `window` `keydown` listener. One listener, attached once by the root layout (`attachShortcuts`), reads the registry at key-press time, and the `?` overlay lists whatever is registered. Shortcuts are skipped while typing in a field or inside a dialog, listbox or menu unless they set `allowInInputs`. See `docs/DECISIONS.md` for why the registry is built this way.

**Schema-driven attributes** - node and edge types carry an `attributes_schema` (JSON Schema 2020-12). The backend validates attribute payloads against this schema on every write, excluding archived fields and advisory required flags: missing category fields never block saving (see [design §16a](DESIGN_GUIDELINES.md#16a-category--relationship-type-schemas) and [DECISIONS.md](../docs/DECISIONS.md)). The frontend renders schema fields using a pluggable field-type registry (`src/lib/field-types/`): each field type owns its schema serialisation (`toSchema`/`fromSchema`), its edit widget (`InputWidget`), and an optional read-mode widget (`ViewWidget`). Adding a new field type requires only a descriptor file and one import line - no changes to the editor components. See [docs/field-types.md](../docs/field-types.md) for the full guide.

**Authentication** - `src/lib/auth.svelte.ts` is a runes singleton (`auth`) holding the signed-in account, its permissions and `passwordExpired`. The root layout calls `auth.init()` (status, then `/auth/me`, then `/auth/me/permissions` unless the password has expired), renders pages only once the route guard allows them, and redirects with the pure `guardDecision()` in `src/lib/auth.ts` (setup required -> `/setup`; no session -> `/login?next=`; expired password -> `/settings/account`; `/login` and `/setup` are the only public routes). `safeNext()` keeps `?next=` to same-origin paths. Use `auth.can('identity:user:create')` (typed with the generated permission union) to hide controls the account may not use; the server still enforces them. `src/lib/api/auth-interceptor.ts` reports a 401 (once) or a `password_expired` 403 to the controller, which the guard turns into a redirect. Signing in or out clears the ETag/body cache so nobody sees the previous person's cached responses. Signing out clears local state first, so the guard shows `/login` at once, and finishes the logout request in the background (`keepalive`); if the server did not end the session the true state is reloaded and the menu shows an error. No password is stored client-side; the session is an HttpOnly cookie.

## Feature reference

Read only the feature section relevant to the task.

### Examples

Library > Examples (`src/routes/library/examples/`) adds and removes the shipped example packs. Home links to it from the empty state and shows a dismissible line while examples are installed. The wording helpers (counts, removal messages, dismissal in `localStorage`) live in `src/lib/examples.ts` so they can be unit tested.

### Collections

`/collections` lists collections (with a search box that also takes `?q=`) and creates them, and `/collections/[id]` shows one: its items (the shared item cards, with search, list and grid views, and the Examples filter), rename and delete, an Add items dialog (`lib/components/add-items-dialog.svelte`) and Remove with Undo. The item page has a Collections card (`lib/components/item-collections.svelte`). Wording and error messages live in `src/lib/collections.ts`. Smart collections (a saved search; `kind === 'dynamic'`) are saved from the items page (`lib/components/save-smart-collection-dialog.svelte`) and show a Smart badge. Their page lists the saved conditions as locked chips (`smart-conditions.svelte`), runs `POST /node/search` with the saved sort (`lib/smart-collections.ts`) and offers **Edit conditions** (explicit Save and Cancel), no add or remove controls, and a narrowing layer: the search box, type select and **Filter** button AND ad-hoc conditions onto the saved ones (`lib/query/narrow.ts`, URL `?f=`/`?q=`/`?type=`), with a bar (`narrowed-bar.svelte`) to save as new, save as new and linked (`in collection <this>` plus the filters, `linkedNarrow`; also the only save on a manual collection narrowed by search text or type), update the collection after a confirmation, or clear. The builder also has Description, Name, Media and In collection rows (the collection picker is chips plus a combobox fed by `fetchAllCollections`, with a Retry when the read fails) and a Connection row (`query-connection-input.svelte`: relationship and direction selects, a server-searching item picker for "Is connected to", and a nested "Where the linked item…" group that cannot hold another connection; lookups come from `ConnectionLookups`). A capped count shows "1,000+" and `collection-count.svelte` (`lib/exact-count.svelte.ts`) fetches the exact figure in the background, with **Count exactly** as the retry. Collections are linked by slug (`collectionRouteParams`, which falls back to the id for an old slug that reads as one; `collectionAddress`; an id address is replaced by the slug), but once the page has loaded every API call goes by `collection.id`, after one reload by id, so the path-keyed ETag cache has a single entry per collection and definition saves carry `If-Match`, and the edit dialog has a Slug field (`collection-slug-field.svelte`). The item page's collection lists ask the server for `kind=manual` (`manualCollections` stays as a guard). A stored definition the server could not return arrives as `definition: null` and shows the unreadable-conditions message with its warning. The items page's **Save as smart collection** saves the filter, search box and type select together (`combineWithSaved`). The e2e specs are `tests/e2e/smart-collections.spec.ts` and `tests/e2e/smart-collection-conditions.spec.ts`, `tests/e2e/smart-collections-connections.spec.ts` (`E2E_BULK=1` adds a 1,003-item exact-count run). The collection page deliberately does not share its list code with the items page; keep the search debounce and the paging in step if you change either.

### Search popup

`/` opens `lib/components/search-palette.svelte`, a grouped search over Items, Collections, Item types and Pages (in that order, capped per group). `lib/palette-sources.ts` (`searchEverything`) fans out to the API and filters item types and pages locally; `lib/palette-search.ts` ranks each group and `lib/search-palette.ts` holds the pure view and live-region logic. A full Collections group ends with a "See all collections" row that opens `/collections?q=...`. A failed source shows a retry row for that group only; "Nothing found" appears only when every source answered and all were empty. Matching is accent-insensitive on the server and in the local filters (`lib/fold-text.ts`); item types are paged in by cursor, up to 1000.

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
npm run generate               # from this directory (requires ../openapi.json to exist)
```

The schema dump step (`poe dump-schema`) writes `openapi.json` at the repository root, which the generate step reads.

## Quality checks

```sh
poe typecheck-frontend   # svelte-check + tsc
poe lint-frontend        # prettier + eslint
poe test-frontend        # Vitest unit tests
poe coverage-frontend    # the same tests with V8 coverage (frontend/coverage/lcov.info)
poe build-frontend       # production build
poe check                # all of the above (from repo root)
```

### Testing

Vitest tests live in `frontend/tests/*.test.ts` (not colocated with components) and run in a Node, not browser, environment - there's no component-rendering test setup here, only unit tests against plain exports (including a `.svelte` file's `<script module>` exports, e.g. `attributes-editor.svelte`'s `attributesToRows`/`rowsToAttributes`).

Coverage (`poe coverage-frontend`, V8 provider) measures `src/**/*.ts` only, excluding the generated API client and `src/routes/`. Components are left out because this environment renders none, so counting them would report what Playwright covers as untested. The floor is the `frontend` component's `target` in `codecov.yml`, the same single source of truth as the backend layers. It applies to line coverage. `poe coverage-frontend` runs the tests, then `scripts/check_component_coverage.py --frontend` reads `coverage/lcov.info` and fails below the target. Codecov's free plan posts no project or component statuses, so it cannot enforce the target itself. CI also uploads the lcov report to Codecov under the `frontend` flag for tracking, and the `coverage-comment` job shows the figure against the target in the pull request comment. Raise the target when coverage settles higher; lower it only with a reason.

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
