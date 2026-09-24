# Menagerist — Frontend

Static SPA served by the backend process itself (`entrypoints/api/spa.py` in `backend/`). API calls go through `/api/*` on the same origin.

Coding conventions (British English, comment style, dependency policy) are in [AGENTS.md](../AGENTS.md#general-rules) — nothing frontend-specific to add here.

## Stack

- [SvelteKit](https://svelte.dev/docs/kit) (static adapter) + Svelte 5
- [Tailwind CSS v4](https://tailwindcss.com) + [shadcn-svelte](https://shadcn-svelte.com) + [bits-ui](https://bits-ui.com)
- TypeScript
- Typed API client auto-generated from the backend's OpenAPI schema via [`@hey-api/openapi-ts`](https://heyapi.dev)

For UX and UI rules, see [DESIGN_GUIDELINES.md](DESIGN_GUIDELINES.md).

## Key patterns

**Reactivity** — Svelte 5 runes throughout (`$state`, `$derived`, `$effect`). No global stores except singleton controllers (`src/lib/theme.svelte.ts`, `src/lib/capture.svelte.ts`).

**API client** — generated types and functions live in `src/lib/api/generated/`. Never edit those files by hand. Import everything through `src/lib/api/client.ts`.

**Routing** — file-based SvelteKit routing, client-rendered only (no `+page.server.ts`). Data is fetched inside components via the API client.

**Paths** — always use `resolve()` from `$app/paths` when building internal hrefs so the app works under a non-root base path.

**Component choice** — prefer an existing shadcn-svelte/bits-ui component over a hand-rolled native HTML element when one exists and fits (`npx shadcn-svelte@latest add <component>` from `frontend/`, then `npx prettier --write` the new files to match house style — the registry ships double-quoted, unformatted source). Check `src/lib/components/ui/` first; most primitives (`Button`, `Input`, `Select`, `DropdownMenu`, `Popover`, ...) are already there. Native elements are still the right call where they're genuinely better: `<input type="file">` (no shadcn equivalent, and none is needed), a `<table>` for genuinely tabular data, or a custom control (the rating field's `role="radiogroup"` star row, image-overlay buttons in `media-gallery.svelte`) that would need heavy style overrides to force into a generic component anyway. When in doubt, match whatever the surrounding file already does.

**Schema-driven attributes** — node and edge types carry an `attributes_schema` (JSON Schema 2020-12). The backend validates attribute payloads against this schema on every write. The frontend renders schema fields using a pluggable field-type registry (`src/lib/field-types/`): each field type owns its schema serialisation (`toSchema`/`fromSchema`), its edit widget (`InputWidget`), and an optional read-mode widget (`ViewWidget`). Adding a new field type requires only a descriptor file and one import line — no changes to the editor components. See [docs/field-types.md](../docs/field-types.md) for the full guide.

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

The typed client lives in `src/lib/api/generated/` and is **auto-generated** — do not edit those files by hand.

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

Vitest tests live in `frontend/tests/*.test.ts` (not colocated with components) and run in a Node, not browser, environment — there's no component-rendering test setup here, only unit tests against plain exports (including a `.svelte` file's `<script module>` exports, e.g. `attributes-editor.svelte`'s `attributesToRows`/`rowsToAttributes`).

`vitest.config.ts` aliases `@lucide/svelte` and `bits-ui` to stubs in `tests/mocks/`. Without them, importing anything that pulls in those packages adds well over a minute per run: Vitest's Node/SSR transform has no browser-style dep pre-bundling, so their large module graphs (thousands of icon exports; floating-ui/melt internals) get compiled file-by-file every run instead of being pre-bundled once. If a test starts failing with a missing export from either package, add the missing name to the relevant stub file — don't remove the alias.

## Building

```sh
npm run build
```

Output goes to `build/`. In production this is copied into the `menagerist` image by the root `Dockerfile` and served by the backend process itself (`MENAGERIST_FRONTEND_DIST_PATH`).
