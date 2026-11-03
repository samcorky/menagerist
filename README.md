<p align="center">
  <img src="frontend/static/favicon.svg" width="64" height="64" alt="Menagerist logo">
</p>

# Menagerist

*(meh-NAH-juh-rist)*

A lightweight, self-hostable platform for organising the things you care about.

<div align="center">

[![Release][release-badge]][release-link]
[![CI][ci-badge]][ci-link]
[![Coverage][coverage-badge]][coverage-link]
[![License: Apache-2.0][license-badge]][license-link]
[![GHCR pulls][pulls-badge]][pulls-link]
[![Download size][size-badge]][pulls-link]
[![CalVer][calver-badge]][calver-link]
[![Python][python-badge]][python-link]
[![mypy: strict][mypy-badge]][mypy-link]
[![Ruff][ruff-badge]][ruff-link]
[![uv][uv-badge]][uv-link]
[![Renovate][renovate-badge]][renovate-link]

</div>

> [!IMPORTANT]
> **Early alpha:** The API, data model, and features are still evolving. Expect breaking changes.

---

## What is it?

Menagerist is a flexible collection manager built on a graph model. Records can represent anything - items, people, events, places - and can be connected to each other in whatever way makes sense for your collection.

The graph model is deliberately hidden from the user. You interact with familiar concepts like items and relationships; Menagerist handles the structure underneath. Features are generic and reusable rather than built around one kind of collection: the same mechanisms that record a signed poster, who signed it and where can record a loan, a purchase or a membership.

---

## What you can do

**Describe anything.** Make an item type for each kind of thing you collect and give it the fields it needs: text and long text, numbers, dates (including a year or month alone), choices and multiple choices, ratings, money, quantities, durations, links, emails, phone numbers, ordered lists, checklists and repeating tables. Save a field or a list of options once and reuse it; countries and condition grades come built in. Add photos, scans and documents to any item, pick a cover, and tag or favourite what matters.

**Connect it.** Link items to each other with relationships that have their own names and fields, such as who signed a poster and where. Every item shows its connections in plain words, and Explore draws the connections map when you want the wider picture.

**Find it.** Search names, descriptions and field values (accents are ignored, so "cafe" finds "Café"), filter by type or by any field, and keep the results as a smart collection that updates itself. Manual collections hold what you choose. A dashboard counts what you care about, and deleted items wait in Recently deleted until you restore or remove them.

**Make it yours.** Dark mode, a layout that works on a phone, and a quick-capture sheet (`Cmd/Ctrl+K`) to add an item without leaving the page you are on. Install an example pack (music, recipes, movies, comic-con posters, electronic parts or games) to see how it fits together, and remove it again when you are done.

**Run it yourself.** One container plus Postgres. Every person has a local account and sees only their own items; administrators manage users, settings, scheduled tasks and backups from the app. Back up and restore from the command line or the admin page, with an automatic backup before each upgrade. Scripts use scoped, expiring [API tokens](#api-tokens). A Status page shows the instance's health checks and version, and administrators are told there when a newer release is out.

---

## Quickstart

You need [Docker](https://docs.docker.com/get-docker/) with Compose. Download the Compose file and start the stack:

```sh
curl -fsSLO https://raw.githubusercontent.com/samcorky/menagerist/main/compose.yaml
docker compose up -d
```

On PowerShell, download with `Invoke-WebRequest https://raw.githubusercontent.com/samcorky/menagerist/main/compose.yaml -OutFile compose.yaml` instead.

On Linux, run `mkdir backups` before the first `docker compose up`, so Docker does not create the folder owned by root where the app cannot write to it (see [docs/DEPLOYING.md](docs/DEPLOYING.md#host-folders-must-be-writable-by-the-container-linux)).

Open [http://localhost:8080](http://localhost:8080). Compose starts Postgres, the app (which sets up its own database on first start) and a background worker, and keeps backups in `./backups` next to the Compose file.

**First visit:** Menagerist asks you to create the administrator account (a username and a password of at least 10 characters). Anything already in the database is adopted by that account. The administrator can then add other people under Settings > Users, and each person sees only their own items. Accounts are local to your instance; there is no email or external sign-in yet. If you forget the administrator password, reset it from the command line: `docker compose exec menagerist menagerist identity reset-password --username <name>` (see [CONTRIBUTING.md](CONTRIBUTING.md#first-run-and-accounts)).

**Next steps.** Updating, rolling back, choosing an image tag, tuning the database and keeping your own Compose changes are in [docs/DEPLOYING.md](docs/DEPLOYING.md); putting Menagerist behind a reverse proxy is in [docs/REVERSE-PROXY.md](docs/REVERSE-PROXY.md).

---

## API tokens

Scripts and other tools can use Menagerist without your password through a personal access token.

1. Sign in, open Settings, then Account, and choose **New token** under Personal access tokens.
2. Name it, enter your password and pick what it may do: **Read only**, **Read and write**, or per-area access under Advanced. Choose an expiry (default 90 days, maximum 365).
3. Copy the token when it is shown. It appears only once.

Send it in a header:

```sh
curl -H "Authorization: Bearer mnst_..." https://your-server/api/v1/auth/me/permissions
```

A token carries only the permissions you give it, never more than you hold, and stops working when it expires or you revoke it. Use **Regenerate** for a new token with the same name and access. Changing or resetting your password removes all your tokens. A token cannot manage tokens or your account, and it cannot export or import your data. The interactive docs at `/api/docs` accept a token through Authorize. Operators can tune the limits with `MENAGERIST_IDENTITY_API_TOKEN_DEFAULT_DAYS`, `MENAGERIST_IDENTITY_API_TOKEN_MAX_DAYS` and `MENAGERIST_IDENTITY_API_TOKENS_PER_USER`.

---

## Stack

| Layer | Technology |
|---|---|
| Backend | Python / FastAPI / SQLAlchemy / Alembic / PostgreSQL |
| Frontend | SvelteKit / TypeScript / Tailwind CSS |
| Container | Docker / distroless image |

---

## Build from source

To run your own changes instead of the published image, build it locally. The build produces the backend's OpenAPI schema and the frontend's typed client itself, so a fresh clone needs nothing pre-generated.

Install [uv](https://docs.astral.sh/uv/):

```bash
curl -LsSf https://astral.sh/uv/install.sh | sh   # macOS/Linux
```

```powershell
powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"   # Windows
```

Then, from the repo root:

```sh
uv run poe init
uv run poe docker-up
```

The app is available at [http://localhost:8080](http://localhost:8080). Everything about developing it, including the dev servers and the tests, is in [CONTRIBUTING.md](CONTRIBUTING.md).

### One `poe` task at a time

```sh
uv run poe init            # sync deps + install git hooks
uv run poe docker-build    # build the Menagerist image
uv run poe docker-up       # start Postgres + Menagerist, detached
```

### Without `poe`

```sh
docker buildx bake -f docker-bake.hcl local
MENAGERIST_IMAGE=menagerist:local docker compose up -d --force-recreate
```

`compose.yaml` pulls the published image unless `MENAGERIST_IMAGE` says otherwise, so `poe docker-up` and the line above point it at the image you just built. On PowerShell, set the variable first: `$env:MENAGERIST_IMAGE = "menagerist:local"`.

`uv run` syncs and resolves the backend package on its own - no separate install step. If you've activated the project's venv instead (see [CONTRIBUTING.md](CONTRIBUTING.md)), drop the `uv run` prefix and call `menagerist` directly.

---

## Documentation

| Document | Contents |
|---|---|
| [docs/DEPLOYING.md](docs/DEPLOYING.md) | Updating, rolling back, image tags, host folders, database sizing, local overrides |
| [docs/REVERSE-PROXY.md](docs/REVERSE-PROXY.md) | What a reverse proxy must do, with Caddy and Traefik examples |
| [CONTRIBUTING.md](CONTRIBUTING.md) | Dev setup, commands, testing and releases |
| [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) | System topology and data model |
| [docs/DECISIONS.md](docs/DECISIONS.md) | Significant technical decisions and rationale |
| [backend/README.md](backend/README.md) | Backend architecture and conventions |
| [frontend/README.md](frontend/README.md) | Frontend stack and dev workflow |
| [frontend/DESIGN_GUIDELINES.md](frontend/DESIGN_GUIDELINES.md) | Frontend UX/UI rules |
| [SECURITY.md](SECURITY.md) | Reporting a vulnerability |
| [CODE_OF_CONDUCT.md](CODE_OF_CONDUCT.md) | How we expect people to behave, and how to report a problem |
| [ACCESSIBILITY.md](ACCESSIBILITY.md) | What the interface aims for, known gaps and how to report a barrier |

---

## Why Menagerist?

Inspired by the idea of a *menagerie* - a curated collection of things. Rather than forcing everything into predefined categories, Menagerist is designed to be general-purpose and adaptable.

> **Your collection, your structure.**

A subtle nod to *Star Trek: The Original Series - The Menagerie*.

[release-badge]: https://img.shields.io/github/v/release/samcorky/menagerist?include_prereleases&logo=github
[ci-badge]: https://img.shields.io/github/actions/workflow/status/samcorky/menagerist/ci.yml?branch=main&logo=githubactions&label=CI
[coverage-badge]: https://codecov.io/github/samcorky/menagerist/graph/badge.svg
[license-badge]: https://img.shields.io/github/license/samcorky/menagerist
[pulls-badge]: https://img.shields.io/badge/dynamic/json?url=https://ghcr-badge.elias.eu.org/api/samcorky/menagerist/menagerist&query=downloadCount&label=pulls&logo=docker&logoColor=white&color=2496ED
[size-badge]: https://ghcr-badge.egpl.dev/samcorky/menagerist/size?tag=latest&label=download%20size%20(amd64)
[calver-badge]: https://img.shields.io/badge/calver-0.YYYY.MM.PATCH-22bfda
[python-badge]: https://img.shields.io/badge/dynamic/regex?url=https://raw.githubusercontent.com/samcorky/menagerist/main/.python-version&search=(.%2B)&replace=%241&label=python&logo=python&logoColor=white&color=blue
[mypy-badge]: https://img.shields.io/badge/mypy-strict-blue?logo=python&logoColor=white
[ruff-badge]: https://img.shields.io/endpoint?url=https://raw.githubusercontent.com/astral-sh/ruff/main/assets/badge/v2.json
[uv-badge]: https://img.shields.io/endpoint?url=https://raw.githubusercontent.com/astral-sh/uv/main/assets/badge/v0.json
[renovate-badge]: https://img.shields.io/badge/renovate-enabled-brightgreen?logo=renovatebot&logoColor=white

[release-link]: https://github.com/samcorky/menagerist/releases
[ci-link]: https://github.com/samcorky/menagerist/actions/workflows/ci.yml
[coverage-link]: https://codecov.io/github/samcorky/menagerist
[license-link]: LICENSE
[pulls-link]: https://github.com/samcorky/menagerist/pkgs/container/menagerist
[calver-link]: https://calver.org
[python-link]: https://www.python.org/
[mypy-link]: https://mypy-lang.org/
[ruff-link]: https://github.com/astral-sh/ruff
[uv-link]: https://github.com/astral-sh/uv
[renovate-link]: https://renovatebot.com
