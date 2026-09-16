# Menagerist — Frontend

Static SPA served by nginx. API calls proxy through `/api/*` to the backend.

## Coding conventions

These conventions apply across the project, including frontend work.

- Use British English for project copy, comments, and user-facing docs unless a library, API, or existing convention explicitly requires a different spelling.
- Keep code comments short, factual, and concise. Only add a comment when the intent would otherwise be unclear.
- Only add or update dependencies when they are strictly necessary or clearly recommended for the task. Prefer the smallest, most targeted dependency that solves the problem and avoid adding libraries that duplicate existing functionality or increase the runtime surface area without a clear benefit.
- Before adding or updating dependencies, review `.github/renovate.json` and keep the change aligned with the repository's Renovate rules and review policy (grouping, schedule, automerge, and manual review for majors/runtime dependencies).
- When evaluating a dependency, estimate the impact on the final Docker image size and runtime footprint, and favour lighter or more maintainable options when trade-offs are similar.

## Stack

- [SvelteKit](https://svelte.dev/docs/kit) (static adapter) + Svelte 5
- [Tailwind CSS v4](https://tailwindcss.com) + [shadcn-svelte](https://shadcn-svelte.com) + [bits-ui](https://bits-ui.com)
- TypeScript
- Typed API client auto-generated from the backend's OpenAPI schema via [`@hey-api/openapi-ts`](https://heyapi.dev)
- Chainguard distroless nginx, non-root, port 8080

For UX and UI rules, see [DESIGN_GUIDELINES.md](DESIGN_GUIDELINES.md).

## Key patterns

**Reactivity** — Svelte 5 runes throughout (`$state`, `$derived`, `$effect`). No global stores except singleton controllers (`src/lib/theme.svelte.ts`, `src/lib/capture.svelte.ts`).

**API client** — generated types and functions live in `src/lib/api/generated/`. Never edit those files by hand. Import everything through `src/lib/api/client.ts`.

**Routing** — file-based SvelteKit routing, client-rendered only (no `+page.server.ts`). Data is fetched inside components via the API client.

**Paths** — always use `resolve()` from `$app/paths` when building internal hrefs so the app works under a non-root base path.

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
poe serve         # from repo root, or use docker compose -f compose.dev.yaml up
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
poe build-frontend       # production build
poe check                # all of the above (from repo root)
```

## Building

```sh
npm run build
```

Output goes to `build/`. In production this is served by the nginx container defined in `frontend/Dockerfile`.
