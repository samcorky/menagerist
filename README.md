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

</div>

> [!IMPORTANT]
> **Early alpha:** The API, data model, and features are still evolving. Expect breaking changes.

Menagerist is a flexible collection manager built on a graph model, deliberately hidden from you: you work with items and relationships, and the same generic mechanisms record a signed poster, who signed it and where, just as well as a loan, a purchase or a membership.

---

## Quickstart

You need [Docker](https://docs.docker.com/get-docker/) with Compose.

```sh
curl -fsSLO https://raw.githubusercontent.com/samcorky/menagerist/main/compose.yaml
docker compose up -d
```

Open [http://localhost:8080](http://localhost:8080) and create the administrator account. That's it - Compose also starts Postgres and a background worker, and keeps backups in `./backups` next to the Compose file.

<details>
<summary>Linux: create the backups folder first</summary>

Run `mkdir backups` before the first `docker compose up`, so Docker does not create the folder owned by root where the app cannot write to it. See [docs/DEPLOYING.md](docs/DEPLOYING.md#host-folders-must-be-writable-by-the-container-linux).

</details>

<details>
<summary>PowerShell</summary>

```powershell
Invoke-WebRequest https://raw.githubusercontent.com/samcorky/menagerist/main/compose.yaml -OutFile compose.yaml
docker compose up -d
```

</details>

<details>
<summary>Forgot the administrator password?</summary>

```sh
docker compose exec menagerist menagerist identity reset-password --username <name>
```

See [CONTRIBUTING.md](CONTRIBUTING.md#first-run-and-accounts).

</details>

<details>
<summary>Next steps</summary>

Updating, rolling back, choosing an image tag, tuning the database and keeping your own Compose changes are in [docs/DEPLOYING.md](docs/DEPLOYING.md); putting Menagerist behind a reverse proxy is in [docs/REVERSE-PROXY.md](docs/REVERSE-PROXY.md). Every environment variable, with its default, is listed in [docs/settings.md](docs/settings.md); [.env.example](.env.example) is a ready-to-copy `.env`.

</details>

---

## What you can do

- **Describe anything.** An item type for each kind of thing you collect, with the fields it needs - text, numbers, dates, choices, ratings, money, quantities, links, checklists, repeating tables and more. Photos, scans and documents attach to any item.
- **Connect it.** Link items with relationships that have their own names and fields, such as who signed a poster and where. Explore draws the connections map.
- **Find it.** Search names, descriptions and field values; filter by type or any field; save a search as a smart collection that updates itself.
- **Make it yours.** Dark mode, a layout that works on a phone, and a quick-capture sheet (`Cmd/Ctrl+K`) to add an item from anywhere. Example packs (music, recipes, movies, comic-con posters, electronic parts, games) show how it fits together.
- **Run it yourself.** One container plus Postgres. Local accounts, each seeing only their own items. Back up and restore from the command line or the admin page, with an automatic backup before each upgrade.

The full list of field kinds is in [docs/field-types.md](docs/field-types.md#built-in-field-types-and-their-json-schema-shapes).

---

## API tokens

Scripts and other tools can use Menagerist without your password through a personal access token.

1. Sign in, open Settings, then Account, and choose **New token** under Personal access tokens.
2. Name it, enter your password and pick what it may do: **Read only**, **Read and write**, or per-area access under Advanced. Choose an expiry (default 90 days, maximum 365).
3. Copy the token when it is shown. It appears only once.

Send it in a header:

```sh
curl -H "Authorization: Bearer mnst_..." https://your-server/api/v1/me/permissions
```

A token carries only the permissions you give it, never more than you hold, and stops working when it expires or you revoke it. Use **Regenerate** for a new token with the same name and access. Changing or resetting your password removes all your tokens. A token cannot manage tokens or your account, and it cannot export or import your data. The interactive docs at `/api/docs` accept a token through Authorize. Operators can tune the limits; see the `MENAGERIST_IDENTITY_API_TOKEN_*` variables in the [settings reference](docs/settings.md#identity).

---

## Stack

| Layer | Technology |
|---|---|
| Backend | Python / FastAPI / SQLAlchemy / Alembic / PostgreSQL |
| Frontend | SvelteKit / TypeScript / Tailwind CSS |
| Container | Docker / distroless image |

---

## Build from source

Want to run your own changes instead of the published image, or help develop Menagerist? Setup, the dev servers, building the Docker image and the tests are all in [CONTRIBUTING.md](CONTRIBUTING.md).

---

## Documentation

| Document | Contents |
|---|---|
| [docs/DEPLOYING.md](docs/DEPLOYING.md) | Updating, rolling back, image tags, host folders, database sizing, local overrides |
| [docs/REVERSE-PROXY.md](docs/REVERSE-PROXY.md) | What a reverse proxy must do, with Caddy and Traefik examples |
| [docs/settings.md](docs/settings.md) | Every environment variable: type, default, allowed values (generated; see also [.env.example](.env.example)) |
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

[release-link]: https://github.com/samcorky/menagerist/releases
[ci-link]: https://github.com/samcorky/menagerist/actions/workflows/ci.yml
[coverage-link]: https://codecov.io/github/samcorky/menagerist
[license-link]: LICENSE
