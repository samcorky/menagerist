# Menagerist — Frontend

Static SPA served by nginx. Proxied behind `/api/*` to the backend in both dev and prod.

## Stack

- [SvelteKit](https://svelte.dev/docs/kit) (static adapter) + Svelte 5
- [TailwindCSS 4](https://tailwindcss.com) + [shadcn-svelte](https://shadcn-svelte.com)
- TypeScript 6
- Typed API client auto-generated from the backend's OpenAPI schema via [`@hey-api/openapi-ts`](https://heyapi.vercel.app)

## Development

Install dependencies and generate the API client first (run from the repo root):

```sh
poe sync          # installs backend + frontend deps and generates the API client
```

Then start the dev server (proxies `/api/*` to `localhost:8000`):

```sh
poe dev           # from repo root
# or
npm run dev       # from this directory
```

The backend must be running separately for API calls to work. Start it with:

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

## Building

```sh
npm run build
```

Output goes to `build/`. In production this is served by the nginx container — see `compose.prod.yaml` at the repo root.
