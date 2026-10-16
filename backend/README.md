# Menagerist Backend Architecture

Hexagonal (ports-and-adapters) architecture with DDD, organised as vertical slices by bounded context. This describes the pattern itself - how modules, ports, adapters, and routers relate - not a snapshot of what's currently built.

## Coding conventions

Shared project-wide conventions (British English, comment style, dependency policy) are in [AGENTS.md](../AGENTS.md#general-rules). Backend-specific rules:

- Prefer Google-style docstrings for Python functions, methods, classes, and modules that are public or non-trivial. Keep the summary brief and use `Args:`, `Returns:`, and `Raises:` sections only when they add real value.
- This project targets Python 3.14. The backend type-checking config in `backend/pyproject.toml` is strict: `mypy` runs with `strict = true`, `plugins = ["pydantic.mypy"]`, `warn_unused_configs = true`, and `show_error_codes = true`.
- Use native Python 3.14 typing syntax and avoid quoted type annotations entirely. Prefer `str | None`, `list[str]`, and explicit concrete parameter/return types over stringified annotations or `Optional[...]`/`Union[...]` where the modern form is clearer.
- Do not add `from __future__ import annotations`; the repo explicitly bans it because runtime frameworks need annotations to be resolvable at runtime.
- Keep annotations explicit, precise, and readable; avoid `Any` unless it is truly necessary and document the reason when you do use it.

## Hexagonal architecture

Domain sits at the center and depends on nothing: entities, value objects, and business rules, with zero FastAPI/SQLAlchemy/Pydantic imports. Application wraps domain with use cases and defines **ports** - Python `Protocol`s describing what a use case needs from the outside world (a repository, a clock, an event publisher) without knowing how it's implemented. Adapters come in two directions:

- **Driving (inbound) adapters** call *into* the application layer - API routers, CLI commands, scheduler consumers. They translate an external trigger (an HTTP request, a CLI invocation, a due cron job) into a use-case call.
- **Driven (outbound) adapters** get called *by* the application layer through a port - a SQLAlchemy repository implementing a `NodeRepository` port, an HTTP client implementing a `MetadataEnricher` port.

Dependency direction is the one rule everything else protects:

```
entrypoints  →  adapters  →  application  →  domain
```

Nothing on the right imports anything on the left. Application depends on port interfaces it defines itself, never on the concrete adapter satisfying them. The concrete adapter is chosen and wired in at the composition root (the entrypoint).

## Modules as bounded contexts

The organising principle is *what domain concept this is about* - `graph`, `media`, `search`, `identity` - never *what kind of code this is*. There's no repo-wide `models/`, `services/`, or `routers/`; each module carries its own domain, application, ports, and adapter code:

```
modules/<context>/
├── domain/            # entities, value objects - no framework imports
├── application/       # use cases only - no ports here
├── ports/             # the slice's public contract - one Protocol per file
│   ├── node_repository.py
│   └── unit_of_work.py
└── adapters/
    ├── api/            # FastAPI router - driving adapter
    ├── cli/             # Cyclopts commands, if the context needs one - driving adapter
    └── persistence/     # driven adapters implementing ports/
        ├── models.py
        ├── node_repository.py            # e.g. SqlAlchemyNodeRepository
        ├── in_memory_node_repository.py  # fast-test double, sibling file, no impl/ nesting
        └── unit_of_work.py
```

`ports/` is a standalone package, not colocated inside `application/`, so it's importable by `application/`, `adapters/`, and tests without pulling in SQLAlchemy or FastAPI. In `adapters/persistence/`, a port's real and in-memory implementations are plain sibling files named to match the port they satisfy - no `impl/` subfolder.

A module whose driven adapters aren't persistence at all - `system`'s health-check and app-info adapters, for instance - names that directory `adapters/platform/` instead of `adapters/persistence/`, since the folder name should describe what the adapters do, not just default to the common case.

A module is created the day its first entity or use case is written, not scaffolded ahead of time. `graph`, modeling nodes, edges, node types, and edge types, is the first module in the codebase.

Infra with no domain and nothing swappable behind it lives in `platform/` instead of a module - package metadata, logging config, the database engine. The test: is more than one implementation plausible? If yes (a second repository backend, a second notification channel), it's a port inside a module. If there's exactly one reasonable way to do it, it's a `platform/` primitive.

## Routers are driving adapters, not where logic lives

A router's only job is translating HTTP into a use-case call and the result back into a response. Business rules belong in application/domain, where they're testable without FastAPI running.

```python
@router.post("/nodes", response_model=NodeResponse)
async def create_node(
    payload: CreateNodeRequest,
    use_case: Annotated[CreateNode, Depends(get_create_node_use_case)],
    actor: Annotated[Actor, Depends(get_current_actor)],
) -> NodeResponse:
    node = await use_case.handle(payload.to_command(), actor)
    return NodeResponse.from_domain(node)
```

The router depends on the use case, not on the repository the use case happens to use - that dependency is resolved once, at the composition root, and injected down. CLI commands follow the identical shape: a Cyclopts command is a driving adapter calling the same use case a router would, just triggered from a terminal. A use case never needs a second implementation to be reachable from a second entrypoint.

## Request bodies: named Pydantic models, not `Form()` fields

A request body is a Pydantic `BaseModel` (`XxxRequest`, with a `to_command()` method converting it to the use case's command), not a collection of individual `Form()`/`Body()` parameters - even when the payload happens to be small, e.g. `AttachMediaRequest` for `POST /media/{asset_id}/attachments`. FastAPI treats a single Pydantic model parameter as a JSON body automatically, and `@hey-api/openapi-ts` turns it into a properly named type for the frontend client (`AttachMediaRequest`) instead of an untyped bag of form fields.

The one case that can't use a plain model is an endpoint that also accepts an `UploadFile` - multipart file uploads can't be embedded inside a Pydantic model, so those fields stay as `Form()` parameters alongside the `UploadFile`. FastAPI then synthesises its own request-body wrapper schema for the multipart body, always named `Body_<operation_id>` (see `fastapi.routing.APIRoute._get_body_field` - there is no per-route parameter to override this name). Left alone, that produces awkward generated-client types like `Body_upload_and_attach_media`. `configure_openapi()` in `entrypoints/api/openapi.py` renames every `Body_*` component schema after generation (`Body_upload_and_attach_media` -> `UploadAndAttachMediaBody`) so the frontend client gets a sane name without changing the route's `operation_id`.

## Ports carry data, not machinery

A port exposes only what the caller needs, never the internals that produce it. A scheduler port takes a `job_key` string, not a reference to the task registry that resolves it - resolution happens on the inbound side that already owns the registry. If a port signature includes a callable, a registry, or an ORM model, the interface is leaking an adapter's implementation detail into a contract that's supposed to be adapter-agnostic.

Same discipline for ownership boundaries: a use case reconciling system-owned data (schedules, config) and one reconciling user-owned equivalents go through separate ports, even against the same table, so a user-facing edit can't silently touch system-managed state.

## Shared kernel

`shared_kernel/` is a top-level package, a sibling of `modules/` and `platform/`, for domain vocabulary that doesn't belong to one bounded context: the `Identifiable`/`Timestamped`/`SoftDeletable` mixins entities compose from, base exception types (`DomainError`, `NotFoundError`, `ConflictError`, `ValidationError`, `ForbiddenError`) that module-specific errors subclass, and the `Actor`/`AuthorizationPort`/`UnitOfWork`/CQRS Protocols every module depends on. Same purity rule as any module's `domain/` layer: zero framework imports. A mixin or error type genuinely specific to one module stays in that module's `domain/` instead.

`platform/` is the other kind of shared code: infra with exactly one plausible implementation (the database engine, logging config, package metadata). `shared_kernel/` is for domain concepts that cut across contexts; `platform/` is for infra that has no domain shape to begin with.

## Error handling wiring

`register_exception_handlers(app)` is called once inside `create_app()`, mapping `shared_kernel.errors` base types to RFC 9457 (`application/problem+json`) responses:

| Error | Status |
|---|---|
| `ValidationError` | 400 |
| `ForbiddenError` | 403 |
| `NotFoundError` | 404 |
| `ConflictError` | 409 |

A module-specific error like `NodeNotFoundError(NotFoundError)` gets the correct HTTP status for free, purely from subclassing. Routers never carry a `try/except` - the mapping is global, not per-endpoint.

## Persistence and configuration

The async engine, `async_sessionmaker`, and shared declarative `Base` live in `platform/database.py`, configured via `pydantic-settings` (`DATABASE_URL`) - a `platform/` concern by the same one-plausible-implementation test as everything else there.

What's module-specific is which unit of work and use case get constructed from that session factory. That wiring lives in `modules/<context>/adapters/api/dependencies.py`, turning `Depends(get_session_factory)` into `create_graph_uow(session_factory)`, then a `CreateNode` use case. There's no separate per-request session dependency - the unit of work owns session lifecycle itself (see below).

`NodeRepository` has two read paths. `list` and `count` take plain filters (`type`, `q`, `favourite`, `ids`) and order by id. `search` and `search_count` take a `ResolvedQuery` (a parsed condition tree plus the field kinds of the item types it names), page by an opaque `Cursor` over the sort values and id (nulls last), and `search_count` takes an optional `limit` so the database stops counting early; the application layer caps the total at `TOTAL_CAP`. `SqlAlchemyNodeRepository` compiles the tree to SQL in `query_sql.py` (with the text prefilter in `search_sql.py`). The Python evaluator in `query_eval.py`, used by the in-memory adapter, is the reference semantics: the SQL must agree with it, and one scenario table in `tests/modules/graph/adapters/persistence/test_node_search.py` runs against both. Text queries run with `SET LOCAL jit = off`. The reasoning and measurements are in `docs/DECISIONS.md`.

## Local adapters for fast testing

Every port ships an in-memory adapter alongside its real backend adapter, as a first-class citizen rather than a private test-only fake. Application-layer and router-level tests wire the in-memory adapter directly (constructor injection, or FastAPI `dependency_overrides` for router tests) and need no live infrastructure. Only tests checking the *real* adapter's correctness (a `SqlAlchemyNodeRepository` round-tripping through Postgres) are `@pytest.mark.integration` and can be skipped where that infrastructure isn't available.

The `SchedulerPort` will need the same shape later (Postgres/APScheduler/Cron adapters plus an in-memory one), so treat this as a named convention rather than something reinvented per port.

## Domain entities

- Every entity primary key is `uuid7` - time-ordered, so it supports keyset pagination without a separate sort key. List ports paginate as `after: UUID | None` + `limit`, ordered by `id ASC`, not an offset. (`NodeRepository.search` is the exception: it pages by keyset on the query's sort values, then id.)
- Entities set their own timestamps in domain methods (`datetime.now(UTC)`, alongside `uuid7()` generation) rather than via SQLAlchemy `server_default`/`onupdate`. Timestamping is domain behavior, testable with `freezegun`/`time-machine` without a live database.
- Mixins compose vertically: `Timestamped`, `SoftDeletable(Timestamped)` (a lifecycle change is itself timestamped), concrete entities like `Node(Identifiable, SoftDeletable)`.
- `kw_only=True, eq=False` on every mixin/entity dataclass - keyword-only keeps constructors unambiguous as fields accumulate across mixins; these entities need identity equality (by ID), not structural equality.
- Invariant checks live in `__post_init__` and raise `shared_kernel.errors.ValidationError` (or a module-specific subclass), never a bare `ValueError` - so a violation bubbling up through a use case gets the correct 400 response for free, through the same handler every other domain error goes through.

## Testing mirrors the architecture

Coverage floors (defined in the root `codecov.yml`, enforced by `poe coverage` and Codecov): domain 100%, application 100%, shared_kernel 100%, adapters 80%, platform 70% - matching how much of each layer's correctness is structural versus incidental. Domain code has no framework dependencies and is exhaustively unit-testable; adapters carry real sessions/HTTP/external services where 100% is impractical or low-signal. `@pytest.mark.integration` separates the fast domain-heavy loop from the slower suite touching real adapters.

`ports/` is tracked but has no fixed floor (`target: auto` in `codecov.yml`) rather than the 100% used for domain/application/shared_kernel - its files are `Protocol` interfaces whose stub method bodies (`...`) never execute, so forcing 100% there wouldn't test anything real.

`backend/tests/` mirrors `src/app/modules/<context>/{domain,application,adapters}` directory-for-directory, plus `tests/architecture/`: an `archunitpython` suite encoding the dependency-direction rule itself (domain may not depend on application/adapters/entrypoints, application may not depend on adapters/entrypoints, adapters may not depend on entrypoints). No I/O, always runs, catches a boundary violation before it becomes a design problem.

## Migrations

One Alembic environment, one `alembic/versions/` directory, for the whole backend - not one per module. All bounded contexts share a single Postgres schema in v1. Each module's SQLAlchemy models register on the shared `Base` from `platform/database.py`; `alembic/env.py` imports every module's `adapters/persistence/models.py` explicitly so their tables exist on `Base.metadata` before autogenerate runs.

## Running things

Backend tests, migrations, and quality checks run as `poe` tasks from the workspace root - `poe test-backend`, `poe test-backend-integration`, `poe migrate`, `poe lint-backend`, `poe typecheck-backend`, etc. Full task list in the root `pyproject.toml`.

## Unit of work: a shared Protocol, not a per-module subclass

`shared_kernel/unit_of_work.py` defines `UnitOfWork[TRepos]` as a `Protocol` - `__aenter__() -> TRepos`, `__aexit__`, `commit()` - satisfied structurally by two implementations written once and reused by every module:

- `platform/unit_of_work.py::SqlAlchemySessionUnitOfWork[TRepos]` - opens a session from an `async_sessionmaker`, owns begin/rollback-on-exception/always-close/commit. Lives in `platform/` for the same reason `platform/database.py` does: exactly one plausible implementation.
- `shared_kernel/unit_of_work.py::InMemoryUnitOfWork[TRepos]` - wraps an already-built repo bundle directly. `__aenter__` just returns what it was given, so there's no session to open or spoof. `.committed`/`.rolled_back` flags let a test assert a use case reached (or correctly avoided) its commit point.

A module contributes a repo-bundle dataclass (`modules/graph/ports/unit_of_work.py::GraphRepos(nodes, edges, node_types, edge_types)`) and a `GraphUnitOfWork = UnitOfWork[GraphRepos]` alias next to it, plus two one-line factories in `adapters/persistence/unit_of_work.py` - `create_graph_uow(session_factory)` and `create_in_memory_graph_uow(repos)` - each constructing one of the two shared implementations around a `GraphRepos`. No module writes `__aenter__`/`__aexit__`/`commit` itself.

A single central unit of work listing every module's repositories was rejected: it couples every module's use cases to every other module's repositories, and implies transactions spanning bounded contexts, which DDD treats as the wrong boundary. Cross-context consistency is handled by referencing IDs and accepting eventual consistency. A second module gets its own `Repos` dataclass and factories on the same two shared implementations, not a slot added to `GraphRepos`.

This also decouples the transaction from the HTTP request/response cycle - the same use case is reachable from a CLI command or a scheduled job, neither of which has a "request" to hang a commit off. The use case owns the commit via the unit of work it's given, so the transaction boundary travels with it regardless of which driving adapter called it.

**Commands take the unit of work; queries take a plain repository.** `CreateNode`/`CreateEdge` depend on `GraphUnitOfWork` and call `await uow.commit()` once their invariants pass. `GetNode`/`ListNodes`/`GetEdge` are read-only and depend on `NodeRepository`/`EdgeRepository` directly - a read has no commit boundary to own.

## CQRS is a typing convention, not a dispatcher

`shared_kernel/cqrs.py` defines two generic Protocols, `CommandHandler[TCommand, TResult]` and `QueryHandler[TQuery, TResult]`, each with `handle(self, command_or_query, actor: Actor) -> TResult`. Every use case gets a matching `*Command`/`*Query` dataclass (`CreateNodeCommand`, `GetNodeQuery`, ...) and implements the corresponding Protocol, so `mypy --strict` verifies every use case in every module is shaped the same way.

`actor` is a `handle()` parameter, not a field on the command/query - it travels alongside the unit of work/repository rather than being baked into the "what to do" data.

There's no bus or mediator between a router/CLI command and the use case it calls - the router calls the use case directly, as shown above. A bus with pipeline behaviors would give a single seam for cross-cutting concerns (logging, authorization) applied uniformly, but nothing here needs that uniformity enforced yet. The typed-handler convention, plus every handler already taking an `actor`, is a prerequisite for a bus regardless, so this doesn't foreclose adding one later.

## Logging

The backend uses **structlog** (configured in `platform/logging_config.py`) with two output modes: colourised console in development, JSON in production (`MENAGERIST_LOG_JSON=true`). The effective log level is controlled by `MENAGERIST_LOG_LEVEL` (default: `INFO`).

**Where loggers live** - application-layer use cases and adapter modules only. The domain layer has zero framework imports, so it carries no logger. In-memory adapters are test infrastructure and are also logger-free.

**Level semantics:**

| Level | When to use |
|---|---|
| `INFO` | One log per mutating action (create, update, delete, promote, attach, detach, stage, orphan, cleanup). Logged after `commit()` so only committed work is recorded. |
| `DEBUG` | Trace-level detail: repository method calls, SQL queries (via SQLAlchemy's stdlib logger), file operations, thumbnail generation steps. Only emitted when `MENAGERIST_LOG_LEVEL=DEBUG`. |
| `WARNING` | Recoverable anomalies that need attention (content-type mismatch, degraded trust level). |
| `ERROR` | Unhandled exceptions, caught by the global exception handler. |

**SQL query logging** is automatic at `DEBUG` level - SQLAlchemy emits every compiled statement through Python's `logging.getLogger("sqlalchemy.engine")`, which structlog's stdlib bridge picks up. No parameters are logged. Enable with `MENAGERIST_LOG_LEVEL=DEBUG`.

**Call-site pattern:**

```python
import structlog

logger = structlog.get_logger()

# In a mutating use case, after commit:
logger.info("node created", node_id=node.id, node_type=node.type)

# In a query use case or adapter:
logger.debug("fetching node", node_id=node_id)
```

Pass values directly - `uuid.UUID` objects are serialised to strings automatically by the `_serialise_uuids` processor in the shared pipeline. Never use f-strings or string formatting for structured fields.

**Request log context** - every line logged while handling a request carries `request_id` (bound by `RequestContextMiddleware`). Once a session resolves, the actor dependencies (`get_current_actor`, `get_signed_in_user`) also bind `user_id` and `session_id` and copy them to `request.state`, so use-case and adapter lines need not pass them. Requests with no valid session carry neither. `session_id` is the session row's id, which cannot authenticate; the cookie token and its hash are secrets and must never appear in a log line, repr or response.

**Access log** - `RequestContextMiddleware` writes one line per request after the response (logger `app.access`), shaped like Granian's access line: event `"<METHOD> <path>"` with `addr` (the client address after the proxy-header wrapper), `method`, `path`, `protocol`, `status`, `dt_ms`, `request_id`, plus `user_id` and `session_id` when a session resolved. It logs at `info`, or `warning` for 5xx (4xx is ordinary traffic); an unhandled exception is logged as 500 and re-raised. The query string and all headers (`Cookie`, `Authorization`, `X-CSRF-Token`, `Set-Cookie`) are never logged; the path may contain ids. Sign-in and setup requests carry no ids on their own line (the session is created during the request); the "signed in" and "first administrator created" events carry them. The logged path is the raw, still percent-encoded one with control characters escaped, and a client `Request-Id` is only kept if it matches `[A-Za-z0-9._:-]{1,128}`. Only `/api/` paths are logged, minus `/api/health*` (probe polling); the SPA's static files write nothing. `dt_ms` measures time until the response starts. Switch it off with `MENAGERIST_ACCESS_LOG=false`. Granian's own access line is off by default now; `serve --access-log` turns it back on (it uses `GRANIAN_ACCESS_LOG_FORMAT` and carries no user or session ids).

**Future:** when an event bus / pipeline behavior is introduced, cross-cutting logging will migrate to a central pipeline stage. The per-use-case logger calls will be removed at that point.

## Example packs

`modules/examples/` installs and removes optional example content (item types, connection types, items, connections and presets). It does not import `graph` or `presets`: it defines its own ports (`PresetTarget`, `GraphTarget`) and `entrypoints/api/shared/example_targets.py` supplies adapters that call the real use cases, the same pattern as `preset_usage.py` for cross-module reads. Install is an ordered list of steps with one commit per step and compensation on failure; removal keeps anything the user edited, connected or attached (rules in `docs/DECISIONS.md`).

### Writing an example pack

Packs are package data in `modules/examples/packs/`, read with `importlib.resources`. To add one:

1. Create `<id>.json` and add `{id, name, description}` to `index.json`. The id is lowercase letters, digits and hyphens, and prefixes every type slug (`music-person`), so packs never clash with a user's own types.
2. The file has `format` (`menagerist-example-pack`), `version` (`1`, `2` if it has collections, `3` if an item type has a `cover`, `4` if it has `requires`), `id` and five sections: `presets`, `relationship_types`, `item_types`, `items`, `connections`. Version 2 also allows an optional sixth, `collections`; version 4 allows `requires`. Parsing is strict: unknown or missing keys are errors, and `collections` in a version 1 file is rejected.
3. Every entity has a local `ref` (lowercase ASCII letters, digits and hyphens). Items name their type by `type`, connections name their endpoints `from` and `to` and their connection type `type`, all by `ref`. A schema refers to a preset with `{"$preset": "<ref>"}`.
4. Item and connection values must use keys their type's `attributes_schema` defines. Write schemas the way the editor would (`x-menagerist` carries the field kind and display options, for example `"display": "words"` on a duration).
5. Collections (version 2): each is `{"ref", "name", "description" (optional), "items": [item refs]}`. List at least one item, no duplicates, only items from the same pack; names are 1 to 120 characters (checked at parse time, mirroring the collections module) and should be unique within a pack (the contract test checks that; the parser does not), and should not be "Favourites" (items already have a favourite flag). The collections module derives each slug, so a pack collection can never clash with the user's own. A collection's items can be of different types.
6. Covers (version 3): an item type may carry `"cover": {"style": "sleeve" | "poster" | "box" | "card"}`. Installing then draws one PNG cover per item of that type (`PillowCoverRenderer`: a coloured background from the item name, one initial, a shape per style: sleeve for records, poster for films, box for board games, card for recipes), attaches it through the `CoverTarget` port (bridged to media in `entrypoints/api/shared/`), and records it as a removable entity. Covers are deterministic from the name, so a reinstall gives identical images. Unknown styles are rejected at parse time.
7. Add-ons (version 4): a pack may list `requires` (pack ids) and refer to a required pack's item types, relationship types and items as `pack:ref` (for example `games:game`, `games:published-by`, `games:lantern-harbour`) in item `type`, connection `from`, `to` and `type`, and collection `items`. An add-on never changes the required pack's types or items; everything it creates is recorded in its own installation. Installing it is refused until every required pack is installed, and removing a required pack is blocked (not cascaded) while an add-on is installed. An add-on item of a base item type inherits that type's cover style. One ships: `games-extras` ("Extra board games", requires `games`: five games including an expansion, publisher connections and a collection, no types of its own). An add-on's display name must not start with another pack's name.
8. Links (version 5): a pack may list `links` to another pack (`{"with": "movies", "from": "night-drive", "to": "movies:cold-harbour", "type": "soundtrack-of"}`). Unprefixed refs are the pack's own, `<with>:<ref>` refs are the other pack's items, and `type` is one of the pack's own relationship types. A link is made, as an ordinary connection recorded under the declaring pack's installation (ref `link:<with>:<n>`), once both packs are installed, whichever was added second, and only between one person's own installations. It is skipped quietly if an end is gone or the same connection already exists. Removing either pack removes the links first and is never blocked; an edited link is kept like any connection. Music ships four "Soundtrack of" links to Movies. Use `requires` for content that cannot exist without the other pack and `links` for connections that are only nice to have.
8. Content: fictional (no real titles, companies or people: check game, film and product names), British English, small and finished, with a few deliberate blanks so an item looks lived in.

`tests/modules/examples/application/test_shipped_packs.py` runs against every pack listed in `index.json`: it installs, removes and reinstalls cleanly, checks slug prefixes, descriptions, British spelling, valid schemas and that all values match their type. `frontend/tests/example-packs.test.ts` checks the same packs from the frontend side. Neither needs editing when a pack is added.

**Covers on removal.** Covers settle before items, so a pack's own cover never counts as the person's file. An untouched cover is deleted with its item. A cover the person replaced is their file: it is kept and keeps its item. Reinstalling re-adopts a kept cover, and a pack never takes over a cover the person added to an item that had none. Known limit: the built-in Pillow font draws only ASCII initials, so a name starting with anything else shows "?" (every shipped item name starts with an ASCII letter).

**Reinstalling after keeping things.** Anything kept on removal also keeps the item types it uses. Installing the pack again re-adopts it rather than refusing: `InstallExamplePack` resolves, from the pack's installations newest first (`InstallationRepository.list_for_pack`, `adoptable_records`), every kept entity that still exists (item and relationship types must also still have the pack's slug) and records it as owned by the new installation with its original content hash, so an edited item is still kept on the next removal. `InstallResult.adopted` counts these beside `created`. A slug taken by something that is not a kept example is still a 409. Known limit: an adopted collection is left as the user has it, so items created afresh are not added to it.

## Collections

`modules/collections/` holds named lists of items. A collection refers to items by id only; it does not import `graph`, and `graph` does not import it. The two meet through ports and bridges in `entrypoints/api/shared/`: `collection_items.py` implements the collections module's `ItemLookup` (which of these ids are live items) from graph's repository, and `collection_members.py` implements graph's `CollectionMembers` (the item ids on a collection) from the collections repositories, for the `?collection=<id>` filter on the item list. Membership changes bump the collection's `updated_at`, and its ETag also covers the live item count (see `docs/DECISIONS.md`). Every collection is scoped to its owner (see "Access scope").

`GET /collection` takes `q` (up to 200 characters; blank means unfiltered) to keep collections whose name or description contains the text, ignoring case and accents (Postgres `unaccent`, enabled by migration), with LIKE wildcards matched literally; it combines with `item_id` and paging.

## Identity

`modules/identity/` owns accounts (`User`, `Role`), sessions, sign-in, first-run setup and the `menagerist identity` CLI. It imports no other module and no content module imports it (architecture tests enforce both); other modules see an account only as the `Actor` that `get_current_actor` builds. Ports: `UserRepository`, `SessionRepository`, `SignInAttemptRepository` (failure counters keyed on hashes of the username and the client address, so throttling never depends on the account existing), `PasswordHasher`, `SessionTokenGenerator`, `Authenticator` (local username and password today; OIDC or trusted-proxy sign-in would be further adapters) and `ExistingDataClaim` (supplied by the entrypoint, since the claim spans modules). Passwords are hashed by a scheme registry (`adapters/security/`, default `scrypt`, `MENAGERIST_PASSWORD_HASHER`); session and cookie settings are in `platform/config/identity.py` (`MENAGERIST_SESSION_TTL_HOURS`, `MENAGERIST_SESSION_IDLE_HOURS`, `MENAGERIST_COOKIE_NAME`, `MENAGERIST_CSRF_COOKIE_NAME`, `MENAGERIST_COOKIE_SECURE`, `MENAGERIST_SIGN_IN_USERNAME_ATTEMPTS`, `MENAGERIST_SIGN_IN_IP_ATTEMPTS`, `MENAGERIST_SIGN_IN_WINDOW_MINUTES`). The CLI alone reads `IdentityCliSettings` (`platform/config/identity_cli.py`: `MENAGERIST_INITIAL_PASSWORD` or a `menagerist_initial_password` secret file). User management is permission-gated (`IdentityPermission`, `identity:user:*`) through the `Authorised*` handlers; the CLI gets its `AuthorizationPort` from the entrypoint (`use_authorization`) and fails closed without it. The lifespan (`entrypoints/api/startup.py`) logs one warning when no enabled administrator exists. Rationale for these choices is in [docs/DECISIONS.md](../docs/DECISIONS.md).

Identity routes use identity's own actor dependencies (`get_identity_actor`, `get_signed_in_user`), so an account whose `password_expired` flag is set can still change its password and sign out; every other route answers 403 `password_expired` until it does. Tests that need the real session lookup are marked `@pytest.mark.real_actor`; otherwise `tests/conftest.py` gives each `TestClient` a default member actor and a matching CSRF cookie and header, and the `as_user` fixture builds a client for a given account and role.

## Access scope

Who may see or change what is decided in one place, the `AccessPolicy` port (`shared_kernel/access_policy.py`, implemented by `OwnerAccessPolicy` in `entrypoints/api/shared/`). Repositories hold no rules; they only apply an `AccessScope` (`AccessScope.of(user_id)` or `AccessScope.everyone()`).

**The rule: every repository method that returns or counts content takes a required keyword-only `scope: AccessScope`.** Only the minimal write methods (`add`, `save`, `update`, `delete`, `remove`, `lock_target`, `claim_orphaned`) are exempt, and the architecture tests (`tests/architecture/test_access_scope_rules.py`) and the generated cross-user isolation test (`tests/entrypoints/test_cross_user_isolation.py`) enforce it. Use cases extend `ScopedCommandHandler` / `ScopedQueryHandler`, fetch with `self._policy.scope_for(actor)`, and call `assert_can_view/modify/delete(actor, entity.owner_id)` after the fetch. A foreign id is a `NotFoundError`, so existence never leaks. `everyone()` is for system jobs (media clean-up, thumbnail regeneration), the first-admin claim and deliberate all-user checks on shared structure (a type's in-use check); comment each such site.

**Adding a new content type or route safely:**

1. Compose the entity from `Owned` and its model from `OwnedMixin`; stamp `owner_id=actor.id` when creating. Add an `(owner_id, id)` index in the migration.
2. Give every port method that returns or counts content a required keyword-only `scope`, and the same signature on the SQL repository (use `owned_by()` in one predicate helper, applied to every statement) and on the in-memory twin (`scope.covers(owner_id)`).
3. Extend `ScopedCommandHandler` / `ScopedQueryHandler`, fetch with the policy's scope and call `assert_can_*` before acting.
4. Add the route to the generated isolation test, or to its `ALLOWED` dict with a one-line reason (for example shared vocabulary or a route that creates and references nothing). A new route that is neither fails the meta test.
5. Add two-user tests at the repository, use-case and router levels (the existing `*_scope.py`, `*_ownership.py` and `*_two_users.py` files are the pattern).

**Adding an admin-only permission:**

1. Add a member to the module's permission enum (`modules/<context>/application/permissions.py`, value `<module>:<resource>:<action>`).
2. If it implies others, add it to the module's `IMPLIES` mapping.
3. If it is a new module's first permission, add the enum to `entrypoints/api/shared/permissions.py` (`Permission`, `ALL_PERMISSIONS`, `IMPLIES`). The `Permission` alias becomes a union at that point. Leave it out of `MEMBER_PERMISSIONS` to keep it admin-only; `tests/architecture/test_permission_catalogue.py` checks the catalogue.
4. Make the use case extend `AuthorisedCommandHandler` / `AuthorisedQueryHandler`, set `required_permission`, and implement `_handle` (not `handle`).
5. The route's OpenAPI entry gets `x-required-permission` from `PermissionAwareRoute`; mention the 403 in the route's `responses`, regenerate the client (`poe generate-frontend-client`) and hide the control in the frontend with `auth.can(...)`.

## Cross-cutting concerns

**Permissions - role-based, enforced.** `shared_kernel/actor.py::Actor` (an id plus a set of role names) and `shared_kernel/authorization.py::AuthorizationPort` (`check(actor, action) -> None`, raising `ForbiddenError`) live in `shared_kernel/`. The concrete adapter, `entrypoints/api/shared/authorization.py::RoleAuthorizationAdapter`, is wired at the composition root (`entrypoints/api/shared/dependencies.py`) because it has no bounded-context owner. Administrators and the system actor hold every permission; members hold `MEMBER_PERMISSIONS` (empty today). A grant is expanded through the module's `IMPLIES` catalogue, and a permission outside the catalogue is denied to everyone. `get_current_actor` resolves the session cookie to the signed-in account's `Actor` (401 otherwise). Row-level rules (whose content an actor may see) are a separate concern: see "Access scope" below.

**`PermissionAwareRoute` - OpenAPI reflection, not enforcement.** `entrypoints/api/shared/permission_aware_route.py::PermissionAwareRoute` reads a use case's statically declared `required_permission` (a plain class attribute or `StrEnum` member - not a computed `@property` value, since it's read via `getattr` on the *class*, before any instance exists) and reflects it into the OpenAPI schema as `x-required-permission`, plus a "Requires permission" line in the endpoint description and a documentation-only `APIKeyCookie` security scheme. It does not check anything at request time; real enforcement stays in the `Authorised*` handler bases' `handle()` via `AuthorizationPort.check()`.

Every leaf router that declares endpoints (`@router.get`/`post`/etc.) must construct its `APIRouter` with `route_class=PermissionAwareRoute` directly - it is **not** enough to set `route_class` only on the top-level `api_router`/`api_v1_router` in `entrypoints/api/__init__.py`. FastAPI resolves an included router's routes from the `APIRoute` objects the leaf router already built at decoration time, not from the including router's `route_class`, so the parent's setting never cascades down through `include_router`. Don't wrap `APIRouter(...)` in a helper/factory function either: this project's ruff config (`runtime-evaluated-decorators` in `pyproject.toml`) statically pattern-matches `router = APIRouter(...)` to know `@router.get` etc. are runtime-evaluated - hiding the call behind a factory breaks that detection and flake8-type-checking starts flagging every import used only in route-handler signatures as needing a `TYPE_CHECKING` block.

**Backups - deferred.** Not designed yet. Whatever shape it takes (infra-level `pg_dump`, an app-level export/import module composing each slice's own export port, or both) should reuse the `Actor`/`AuthorizationPort` seam above unmodified, since exporting data is itself an actor-attributed action - but the design is future work, not scaffolded ahead of time.
