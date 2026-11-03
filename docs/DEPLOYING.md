# Deploying Menagerist

Running Menagerist for real: updating, rolling back, image tags, reverse proxies, database sizing and local overrides. For a first run, start with the quickstart in the [README](../README.md).

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
| `sha-<commit>` | One exact commit, by its first seven characters. Not every commit on `main` gets one: a newer merge cancels an older build that is still running. |

### Checking where an image came from

Release images carry a signed build provenance attestation, made by the `Publish` workflow of this repository and stored beside the image in GHCR. Check it with the GitHub CLI:

```sh
gh attestation verify oci://ghcr.io/samcorky/menagerist:0.2026.11.0 --owner samcorky
```

It succeeds only when the attestation matches the image and was signed by this repository's workflow, so a rebuilt or altered image fails. Use the tag you pulled.

## Rolling back to an earlier release

Every release image stays in GHCR under its version tag and its `sha-<commit>` tag, so a known-good one can be pinned again. Put it in the `.env` file next to `compose.yaml`:

```sh
MENAGERIST_IMAGE=ghcr.io/samcorky/menagerist:0.2026.10.2
```

then run `docker compose up -d`. If the release you are leaving applied no database migration, that is the whole rollback.

Migrations only run forward. If the newer release did migrate the database, the earlier image cannot use it, and the way back is the `pre-migration` backup that was written just before the upgrade (see [Updating](#updating-and-image-tags)). A restore only works onto a database at the revision the archive was taken at, so start the older image on an empty database first:

1. Optionally keep what you have: `docker compose run --rm --no-deps menagerist backup create` writes an archive of the current data to `./backups`. Anything entered since the upgrade is otherwise lost.
2. Stop the stack with `docker compose down`, then delete the database volume: find it with `docker volume ls` (it is called `<project>_postgres-data`) and remove it with `docker volume rm`. This erases the database; the archives in `./backups` are untouched.
3. Pin the older tag as above and start only the app and database: `docker compose up -d postgres menagerist`. The empty database is set up at that release's own revision, and no backup is taken because there is nothing to protect.
4. Find the archive labelled `pre-migration` with `docker compose run --rm --no-deps menagerist backup list`. Its `ALEMBIC_REVISION` is the revision before the upgrade.
5. Stop the app with `docker compose stop menagerist`, then restore: `docker compose run --rm --no-deps menagerist backup restore <id>`. It refuses if the revisions differ.
6. Start everything: `docker compose up -d`.

To move forward again, set `MENAGERIST_IMAGE` back to the newer tag (or delete the line to follow `latest`) and run `docker compose pull` then `docker compose up -d`. The upgrade writes a fresh pre-migration backup first. The backup commands are described in [backend/README.md](../backend/README.md).

## Behind a reverse proxy

Menagerist leaves TLS to a reverse proxy. [REVERSE-PROXY.md](REVERSE-PROXY.md) lists what the proxy must do, the settings to change, and a Caddy and a Traefik example. Without `MENAGERIST_API_TRUSTED_PROXIES`, every visitor shares the proxy's address and sign-in can lock for everyone.

## Deployment notes

No other website may call the API unless you list its origin in `MENAGERIST_API_CORS_ORIGINS` (only needed if the frontend is hosted separately). Menagerist does not send `Strict-Transport-Security`; set it at the TLS-terminating proxy (see [REVERSE-PROXY.md](REVERSE-PROXY.md#send-hsts-from-the-proxy)). The public `/api/health/ready` answers only pass or fail; measurements are for administrators at `/api/v1/system/health/ready/detail`.

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

## Host folders must be writable by the container (Linux)

The container runs as user `1000:1000`. The named volumes (`media-data`, `postgres-data`) are set up with the right owner by the image, but a folder on the host that Compose bind-mounts, such as `./backups` in `compose.yaml` or `./data/media` in the override below, is created by Docker as `root` if it does not exist yet on Linux. The app then cannot write to it, so backups fail with a permission error. Create the folders yourself before the first `docker compose up`:

```sh
mkdir -p backups data/media
```

If your user is not uid 1000, also run `sudo chown 1000:1000 backups data/media`. A folder Docker already created as root needs the same `chown`. Docker Desktop on Windows and macOS maps ownership itself, so none of this is needed there.

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

Create those folders first (see above). Give the app and the worker the same volumes, as above, because both read and write media. `!override` replaces a list instead of adding to it. `docker compose config` prints the merged result to check it. Running `docker compose -f compose.yaml up` skips the override.
