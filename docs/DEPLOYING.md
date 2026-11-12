# Deploying Menagerist

Running Menagerist for real: updating, rolling back, image tags, reverse proxies, database sizing and local overrides. For a first run, start with the quickstart in the [README](../README.md).

## Updating and image tags

```sh
docker compose pull
docker compose up -d
```

The `menagerist` container applies database migrations when it starts. Before it upgrades an existing database it writes a verified backup archive to `./backups` (turn this off with `MENAGERIST_BACKUP_BEFORE_MIGRATE=false`), so a failed upgrade can be restored.

`compose.yaml` follows the `latest` image unless `MENAGERIST_IMAGE` says otherwise ([Compose variables](settings.md#compose)). Set it in a `.env` file next to `compose.yaml` to choose another tag:

| Tag                 | What it is                                                                                                                                                                                                               |
| ------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| `latest`            | The most recent release. The `0.` in the version only means the project is not yet stable, so those releases count; release candidates (`0.2026.11.0rc1`) do not.                                                        |
| `0.2026.11.0`       | One release, by version, which never moves, even when a hotfix (`0.2026.11.0.post1`) follows it. Pin this to update only when you choose to.                                                                             |
| `0.2026.11.0.post1` | A hotfix for that release, made for a fix to the release process or packaging rather than for new features. It gets its own exact tag and moves `latest`, `0.2026.11` and `0.2026`; `0.2026.11.0` stays as it was built. |
| `0.2026.11`         | The newest release of that month, including a `.post` hotfix. Follow this to take patches and hotfixes but not the next month's changes.                                                                                 |
| `0.2026`            | The newest release of that year.                                                                                                                                                                                         |
| `0.2026.11.0rc1`    | A release candidate, published ahead of its release for testing.                                                                                                                                                         |
| `edge`              | The latest commit on `main`.                                                                                                                                                                                             |
| `sha-<commit>`      | One exact commit, by its first seven characters. Not every commit on `main` gets one: a newer merge cancels an older build that is still running.                                                                        |

A tag moves only when the release is the newest it covers. A hotfix for an older month (a `.post` of `0.2026.10.0` once `0.2026.11.0` is out) moves its own month tag, `0.2026.10`, but not `0.2026` or `latest`, which stay with the newer release. Pre-releases move none of the shared tags. Moving `latest` or a month tag back to an older release is not supported: pin the exact version instead.

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
5. Stop the app with `docker compose stop menagerist`, then restore: `docker compose run --rm --no-deps menagerist backup restore <id>`. It refuses if the revisions differ (even with `--replace`) or if the database is not empty, which is why step 3 must not have run the newer image first.
6. Start everything: `docker compose up -d`.

This procedure, including the pre-migration `backup create` step, is checked automatically in CI against a real schema change (the per-user favourites migration): a backup taken at the old revision is refused on the new one, even with `--replace`, and restores cleanly onto a database still at the old revision.

The archive holds the original media files, so they come back even onto a new media volume. It does not hold thumbnails, which are made again from the originals: if you also lost the media volume, run `docker compose run --rm --no-deps menagerist media regenerate-thumbnails --yes` after the restore, or the thumbnails stay blank until you do.

To move forward again, set `MENAGERIST_IMAGE` back to the newer tag (or delete the line to follow `latest`) and run `docker compose pull` then `docker compose up -d`. The upgrade writes a fresh pre-migration backup first. The backup commands are described in [backend/README.md](../backend/README.md).

## Behind a reverse proxy

Menagerist leaves TLS to a reverse proxy. [REVERSE-PROXY.md](REVERSE-PROXY.md) lists what the proxy must do, the settings to change, and an nginx, a Caddy and a Traefik example. Without `MENAGERIST_API_TRUSTED_PROXIES`, every visitor shares the proxy's address and sign-in can lock for everyone.

## Deployment notes

No other website may call the API unless you list its origin in `MENAGERIST_API_CORS_ORIGINS` (only needed if the frontend is hosted separately). Menagerist does not send `Strict-Transport-Security`; set it at the TLS-terminating proxy (see [REVERSE-PROXY.md](REVERSE-PROXY.md#send-hsts-from-the-proxy)). The public `/api/health/ready` answers only pass or fail; measurements are for administrators at `/api/v1/system/health/ready/detail`.

## Looking for updates

The update check contacts two hosts: `github.com` (the repository's releases) and, on a development build such as the `edge` image, `ghcr.io`, to read which commit the published `edge` image was built from and tell you whether yours is the current one. Both are read anonymously, with no token, and are sent only what any request sends: your address and a `Menagerist/<version>` user agent. Nothing about your collection leaves the instance.

It runs on `MENAGERIST_RELEASE_CHECK_SCHEDULE` (default `20 5 * * *`) and whenever an administrator chooses Check now on the Status page. Set the schedule empty to stop the timer while leaving Check now available.

To stop the instance calling out at all, set `MENAGERIST_RELEASE_CHECK_ENABLED=false`. The scheduled job is then not registered (so it is not on Administration > Scheduled tasks and cannot be run by hand), Check now is unavailable, and the Status page says checks are turned off by the deployment. It is a deployment setting on purpose, so an administrator cannot turn it back on from the interface; changing it needs a restart of both the app and the worker.

## Database memory tuning

The Postgres container is capped at 512 MB and its memory settings are sized to match, which suits a small install. Raise the memory values together on a larger machine by setting them in a `.env` file next to `compose.yaml` (Compose reads it automatically) and recreating the stack. The variables (`POSTGRES_MEM_LIMIT`, `POSTGRES_SHARED_BUFFERS`, `POSTGRES_EFFECTIVE_CACHE_SIZE`, `POSTGRES_WORK_MEM` and `POSTGRES_MAX_CONNECTIONS`), their defaults and when to change each are listed under [Compose variables](settings.md#compose).

For example, a machine with 2 GB to spare for the database: `POSTGRES_MEM_LIMIT=2g`, `POSTGRES_SHARED_BUFFERS=512MB`, `POSTGRES_EFFECTIVE_CACHE_SIZE=1GB`. To see the values in effect: `docker compose exec postgres psql -U menagerist -c "SHOW shared_buffers"`.

## Web server workers

`MENAGERIST_SERVER_WORKERS` is `auto` by default (or a number from `1` to `16`). `auto` follows the advice in [Granian's documentation](https://github.com/emmett-framework/granian), which Menagerist runs on: one worker per CPU core on a plain host, and one worker per container on Docker and Kubernetes, scaling by running more containers. So the Docker image runs one worker, and so does `serve --reload` for development. One worker already serves many requests at once, because it is asynchronous. Set a number to override it, for example on a many-core machine where you would rather not run several containers. Each worker can hold up to `MENAGERIST_DATABASE_POOL_SIZE` plus `MENAGERIST_DATABASE_MAX_OVERFLOW` database connections (5 and 10 by default, so 15), and the background worker the same again, so at startup the server reads Postgres' `max_connections` and logs a warning if the pools could exceed it; raise `POSTGRES_MAX_CONNECTIONS` with the workers, or lower the pool settings. A changed setting can take up to 5 seconds to reach every worker.

## Host folders must be writable by the container (Linux)

The container runs as user `1000:1000`. The named volumes (`media-data`, `postgres-data`) are set up with the right owner by the image, but a folder on the host that Compose bind-mounts, such as `./backups` in `compose.yaml` or `./data/media` in the override below, is created by Docker as `root` if it does not exist yet on Linux. The app then cannot write to it, so backups fail with a permission error. Create the folders yourself before the first `docker compose up`:

```sh
mkdir -p backups data/media
```

If your user is not uid 1000, also run `sudo chown 1000:1000 backups data/media`. A folder Docker already created as root needs the same `chown`. Docker Desktop on Windows and macOS maps ownership itself, so none of this is needed there.

## Secrets from files

Any setting can be read from a file as well as from its environment variable, so a secret such as the database password or the first-admin password need not sit in `.env` or show up in `docker inspect`. Docker and Compose mount secrets in `/run/secrets`; a file there named after the variable (`MENAGERIST_DATABASE_PASSWORD`, or in lower case) supplies that setting, and its trailing newline is ignored. The environment variable wins when both are set, so a secret file never overrides a value in `.env`. A host with no `/run/secrets` directory is unaffected.

The [settings reference](settings.md) marks the settings worth keeping this way: any row whose notes say "Sensitive" holds a credential or a URL that can carry one, such as `MENAGERIST_DATABASE_PASSWORD` and `MENAGERIST_IDENTITY_INITIAL_PASSWORD`. Settings that are not marked work the same way, but there is little to gain.

The database connection is a set of separate settings (`MENAGERIST_DATABASE_HOST`, `_PORT`, `_USER`, `_PASSWORD` and `_NAME`), so only the password needs to be secret. Type it as it is: it is percent-encoded for you, so characters such as `@`, `/` and `:` need no escaping. `MENAGERIST_DATABASE_URL` still works as a single value, and when it is set it replaces all five parts; use it for query options such as `?ssl=require`, which have no setting of their own.

`compose.yaml` takes the password from `POSTGRES_PASSWORD` (default `menagerist`) and gives it to the database container and to the app and worker, so you set it once, in `.env`. To keep it out of `.env` and `docker inspect`, use a secret instead. A secret is mounted under its own name, so call it after the variable (lower case is fine). Postgres reads its copy through `POSTGRES_PASSWORD_FILE`. In `compose.override.yaml`:

```yaml
secrets:
  menagerist_database_password:
    file: ./secrets/database_password

services:
  postgres:
    environment:
      POSTGRES_PASSWORD: !reset null
      POSTGRES_PASSWORD_FILE: /run/secrets/menagerist_database_password
    secrets:
      - menagerist_database_password
  menagerist:
    environment:
      MENAGERIST_DATABASE_PASSWORD: !reset null
    secrets:
      - menagerist_database_password
  worker:
    environment:
      MENAGERIST_DATABASE_PASSWORD: !reset null
    secrets:
      - menagerist_database_password
```

Keep `./secrets` out of version control and readable only by you. A setting read from a file counts as set by the deployment, the same as one from the environment.

## Your own changes: `compose.override.yaml`

Compose merges a file named `compose.override.yaml` onto `compose.yaml` automatically, so local choices stay out of the shipped file and survive an update. The repository ignores it (`.gitignore`), so create it yourself next to `compose.yaml`. Compose merges the two rather than replacing the service: a single value you set (an image, a command) replaces the one in `compose.yaml`, mappings such as `environment` are combined, and lists of `ports`, `volumes`, `labels` and `networks` are added to, with an entry replacing the one that has the same container path or published port. For example, keep media and backups in plain folders you can see and back up, and reach the database from the host for a one-off query:

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
    ports:
      - "127.0.0.1:5432:5432"
```

Create those folders first (see above). Give the app and the worker the same volumes, as above, because both read and write media. To drop an entry from `compose.yaml` rather than add to it, write the list with `!override` (replace the whole list, as `ports: !override []` does in [REVERSE-PROXY.md](REVERSE-PROXY.md)) or `!reset`. `docker compose config` prints the merged result to check it. Running `docker compose -f compose.yaml up` skips the override.

Compose also accepts `compose.override.yml`, and the repository's own development file (gitignored, used by `poe docker-up` and read by `poe generate-settings-docs`) is spelt that way. This documentation uses `.yaml` throughout, to match `compose.yaml`. Keep only one of the two: with both present Compose warns and uses the `.yml` one.
