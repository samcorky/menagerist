# Deploying Menagerist

Running Menagerist for real: updating, image tags, reverse proxies, database sizing and local overrides. For a first run, start with the quickstart in the [README](../README.md).

## Updating and image tags

```sh
docker compose pull
docker compose up -d
```

The `menagerist` container applies database migrations when it starts. Before it upgrades an existing database it writes a verified backup archive to `./backups` (turn this off with `MENAGERIST_BACKUP_BEFORE_MIGRATE=false`), so a failed upgrade can be restored.

`compose.yaml` pulls `ghcr.io/samcorky/menagerist:latest` unless `MENAGERIST_IMAGE` says otherwise. Set it in a `.env` file next to `compose.yaml` to choose another tag:

| Tag | What it is |
|---|---|
| `latest` | The most recent release. The `0.` in the version only means the project is not yet stable, so those releases count; release candidates (`0.2026.11.0rc1`) do not. |
| `0.2026.11.0` | One release, by version. Pin this to update only when you choose to. |
| `0.2026.11.0rc1` | A release candidate, published ahead of its release for testing. |
| `edge` | The latest commit on `main`. |
| `sha-<commit>` | One exact commit. |

## Behind a reverse proxy

Set `MENAGERIST_API_TRUSTED_PROXIES` to the proxy's address or network, and tell Menagerist its public address with `MENAGERIST_API_PUBLIC_ORIGIN=https://menagerist.example.com` plus `MENAGERIST_IDENTITY_COOKIE_SECURE=origin` if the proxy terminates TLS. Without the first, every visitor shares the proxy's address and 20 failed sign-ins from anyone lock sign-in for everyone for 15 minutes; without the second, the session cookie may be sent without `Secure`. `MENAGERIST_IDENTITY_COOKIE_SECURE` is `auto` by default (Secure when the app sees HTTPS), `origin` (follow the scheme of the public address, and refuse to start if none is set), or `always` / `never`. Signing in over plain `http://` sends the password and session cookie unencrypted, which is fine on `localhost` and a home network you trust, and not over the internet. Details are in [CONTRIBUTING.md](../CONTRIBUTING.md#first-run-and-accounts).

## Sign-in and first-run setup refuse requests from other sites

The browser's own `Sec-Fetch-Site` header decides: `cross-site` is refused and `same-origin` is accepted, whatever the proxy does to the scheme or host. Without that header (very old browsers, or plain HTTP on a LAN address) or when it says `same-site`, the request's `Origin` must match the origin the app sees, so there the proxy must pass `Host` and `X-Forwarded-Proto` through and be listed in `MENAGERIST_API_TRUSTED_PROXIES`. `MENAGERIST_API_CORS_ORIGINS` is not the fix for a proxy problem.

## If the proxy setup looks wrong, Menagerist says so

The first time in an hour it sees forwarding headers from a peer it does not trust, or a browser whose origin differs from the one it saw, it logs a warning (`reverse proxy may be misconfigured`) with the setting to change. With `MENAGERIST_API_PUBLIC_ORIGIN` set it also notices requests that arrive at a different address (`publicOriginMismatch`) or over plain `http` when the public address is `https` (`insecureOrigin`); the container's own health check is ignored. Administrators also see a warning for `proxy:configuration` at `/api/v1/system/health/ready/detail` for the next hour. It is a warning only: `/api/health/ready` still answers pass. Find your proxy's network with `docker network inspect <network>` and list it, for example `MENAGERIST_API_TRUSTED_PROXIES=172.21.0.0/16`, in `.env`, then recreate the container.

## Send HSTS from the proxy

Menagerist trusts the browser's headers, and the browser only keeps using HTTPS if the proxy tells it to. Set `Strict-Transport-Security` at the TLS-terminating proxy so a browser never falls back to plain HTTP for your address (Caddy `header Strict-Transport-Security "max-age=15552000"`, nginx `add_header Strict-Transport-Security "max-age=15552000" always;`, Traefik's `stsSeconds` headers middleware). The app does not send it itself because it cannot know it is reached over HTTPS.

## Deployment notes

No other website may call the API unless you list its origin in `MENAGERIST_API_CORS_ORIGINS` (only needed if the frontend is hosted separately). Menagerist does not send `Strict-Transport-Security`; set it at the TLS-terminating proxy (see above). The public `/api/health/ready` answers only pass or fail; measurements are for administrators at `/api/v1/system/health/ready/detail`.

## Database memory tuning

The Postgres container is capped at 512 MB and its memory settings are sized to match. Set any of these in a `.env` file next to `compose.yaml` (Compose reads it automatically) and recreate the stack. The defaults suit a small install; raise them together on a larger machine.

| `.env` variable | Default | Postgres' own default | When to change it |
| --- | --- | --- | --- |
| `POSTGRES_MEM_LIMIT` | `512m` | no limit | The container's hard memory cap. Raise it with the values below if the database is large. |
| `POSTGRES_SHARED_BUFFERS` | `128MB` | `128MB` | About a quarter of the memory cap. The most useful one to raise on a bigger machine. |
| `POSTGRES_EFFECTIVE_CACHE_SIZE` | `256MB` | `4GB` | A planner hint for how much data the OS can cache; keep it near half the memory cap so the planner is not over-optimistic. |
| `POSTGRES_WORK_MEM` | `4MB` | `4MB` | Memory per sort or hash in a query. Raise it only if large sorts spill to disk, as it applies to each step of each connection. |
| `POSTGRES_MAX_CONNECTIONS` | `100` | `100` | Each worker process keeps a pool of connections; lower it on a very small machine, and keep it above the total of all pools. |

For example, a machine with 2 GB to spare for the database: `POSTGRES_MEM_LIMIT=2g`, `POSTGRES_SHARED_BUFFERS=512MB`, `POSTGRES_EFFECTIVE_CACHE_SIZE=1GB`. To see the values in effect: `docker compose exec postgres psql -U menagerist -c "SHOW shared_buffers"`.

## Web server workers

`MENAGERIST_SERVER_WORKERS` is `auto` by default (or a number from `1` to `16`). `auto` follows the advice in [Granian's documentation](https://github.com/emmett-framework/granian), which Menagerist runs on: one worker per CPU core on a plain host, and one worker per container on Docker and Kubernetes, scaling by running more containers. So the Docker image runs one worker, and so does `serve --reload` for development. One worker already serves many requests at once, because it is asynchronous. Set a number to override it, for example on a many-core machine where you would rather not run several containers. Each worker can hold up to 15 database connections, and the background worker another 15, so at startup the server reads Postgres' `max_connections` and logs a warning if the pools could exceed it; raise `POSTGRES_MAX_CONNECTIONS` with the workers. A changed setting can take up to 5 seconds to reach every worker.

## Your own changes: `compose.override.yaml`

Compose merges a file named `compose.override.yaml` onto `compose.yaml` automatically, so local choices stay out of the shipped file and survive an update. The repository ignores it (`.gitignore`), so create it yourself next to `compose.yaml`. Anything you set replaces the matching entry in `compose.yaml`; the rest is kept. For example, keep media and backups in plain folders you can see and back up, and reach the database from the host for a one-off query:

```yaml
services:
  menagerist:
    volumes:
      - ./data/media:/data/media
      - ./backups:/data/backups
  worker:
    volumes:
      - ./data/media:/data/media
      - ./backups:/data/backups
  postgres:
    ports: !override
      - "127.0.0.1:5432:5432"
```

Give the app and the worker the same volumes, as above, because both read and write media. `!override` replaces a list instead of adding to it. `docker compose config` prints the merged result to check it. Running `docker compose -f compose.yaml up` skips the override.
