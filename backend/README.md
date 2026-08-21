# Menagerist Backend Architecture

Hexagonal (ports-and-adapters) architecture with DDD, organised as vertical slices by bounded context. This is a guide to the pattern itself - how modules, ports, adapters, and routers relate - rather than a snapshot of what's currently built.

## Hexagonal architecture

Domain sits at the center and depends on nothing: entities, value objects, and business rules, with zero FastAPI/SQLAlchemy/Pydantic imports. Application wraps domain with use cases, and is where **ports** get defined - Python `Protocol`s describing what the use case needs from the outside world (a repository, a clock, an event publisher) without knowing how any of it is implemented. Adapters live outside that and come in two directions:

- **Driving (inbound) adapters** call *into* the application layer – API routers, CLI commands, scheduler consumers. They translate an external trigger (an HTTP request, a CLI invocation, a due cron job) into a use-case call.
- **Driven (outbound) adapters** get called *by* the application layer through a port it defined - a SQLAlchemy repository implementing a `NodeRepository` port, an HTTP client implementing a `MetadataEnricher` port.

Dependency direction is the one rule everything else protects:

```
entrypoints  →  adapters  →  application  →  domain
```

Nothing on the right imports anything on the left. Application depends on port interfaces it defines itself, never on the concrete adapter that satisfies them - the concrete adapter is chosen and wired in at the composition root (the entrypoint), not referenced from inside application code.

## Modules as bounded contexts

The organising principle is *what domain concept this is about* - `graph`, `media`, `search`, `identity` - never *what kind of code this is*. There's no repo-wide `models/`, `services/`, or `routers/`; each module is a self-contained vertical slice that carries its own domain, application, and adapter code:

```
modules/<context>/
├── domain/          # entities, value objects - no framework imports
├── application/      # use cases; defines ports as Protocols
├── ports.py          # (or colocated with application) the interfaces adapters implement
└── adapters/
    ├── api/          # FastAPI router - driving adapter
    ├── cli/           # Cyclopts commands, if the context needs one - driving adapter
    └── persistence/   # SQLAlchemy repository implementing a domain-defined port - driven adapter
```

A module is created the day its first entity or use case is actually written, not scaffolded ahead of time - there's no value in a module folder with nothing but empty ports. `graph`, modeling nodes and edges, is the first bounded context in line.

Infra that has no domain and nothing swappable behind it doesn't belong in a module at all - it lives in a shared `platform/` package instead. The test is whether there's more than one plausible implementation: something like reading installed package metadata has exactly one reasonable way to be done, so it's a shared primitive, not a port with an adapter behind it. If a second implementation is plausible (a second repository backend, a second notification channel), that's the signal it should be a port inside a module.

## Routers are driving adapters, not where logic lives

An API router's only job is translating HTTP into a use-case call and the use-case's result back into an HTTP response. It shouldn't contain business rules - those belong in application/domain, where they're testable without spinning up FastAPI.

```python
@router.post("/nodes", response_model=NodeResponse)
def create_node(
    payload: CreateNodeRequest,
    create_node: Annotated[CreateNode, Depends(get_create_node_use_case)],
) -> NodeResponse:
    node = create_node(payload.to_command())
    return NodeResponse.from_domain(node)
```

The router depends on the use case (application layer), not on the repository the use case happens to use - that dependency is resolved once, at the composition root, and injected down. CLI commands follow the identical shape: a Cyclopts command is a driving adapter calling the same use case a router would, just triggered from a terminal instead of an HTTP request. That symmetry is deliberate - it means a use case never needs a second implementation to be reachable from a second entrypoint.

## Ports carry data, not machinery

A port should expose only what the caller needs, never the internals that produce it. A scheduler port takes a `job_key` string, not a reference to the task registry that resolves it - resolution from `job_key` to callable happens on the inbound side that already owns the registry, not across the port. If a port signature includes a callable, a registry, or an ORM model, that's usually a sign the interface is leaking an adapter's implementation detail into a contract that's supposed to be adapter-agnostic.

This same discipline applies to keeping different ownership domains from crossing where they shouldn't - a use case for reconciling system-owned data (schedules, config) and a use case for user-owned equivalents should go through entirely separate ports, even if the underlying table is the same, so a user-facing edit can never silently interact with system-managed state.

## Shared kernel

Not everything domain-shaped belongs to one bounded context. `shared_kernel/` is a top-level package, a sibling of `modules/` and `platform/`, holding domain vocabulary every module needs: the `Identifiable`/`Timestamped`/`SoftDeletable` mixins entities compose from, and base exception types (`DomainError`, `NotFoundError`, `ConflictError`, `ValidationError`) that module-specific errors subclass. It follows the exact same purity rule as any module's `domain/` layer - zero framework imports.

This is distinct from `platform/`: `platform/` is for infra with exactly one plausible implementation and nothing domain-shaped in it (package metadata, logging config, the database engine). `shared_kernel/` is for domain concepts - just ones that don't belong to a single bounded context. If a mixin or error type is genuinely specific to one module, it stays in that module's `domain/`, not here.

## Error handling wiring

`problem_response()` isn't called manually per endpoint - that would mean every router carries at least a `try/except`, which violates "routers have zero business logic." Instead it's registered once, at the composition root, as global FastAPI exception handlers (`register_exception_handlers(app)` inside `create_app()`), mapping the `shared_kernel.errors` base types to RFC 9457 (`application/problem+json`) responses (`NotFoundError` → 404, `ConflictError` → 409, `ValidationError` → 400, ...). A module-specific error like `NodeNotFoundError(NotFoundError)` gets correct HTTP mapping for free, purely from subclassing - the router that raises it (indirectly, via the use case) never imports anything error-related at all.

## Persistence and configuration

The async engine, `async_sessionmaker`, and shared declarative `Base` live in `platform/database.py`, configured via `pydantic-settings` (`DATABASE_URL`). This is a `platform/` concern, not a module concern, because "how do I get a database session" has exactly one plausible implementation in this project - the same test that keeps mixins out of `platform/` also keeps the engine out of `shared_kernel/`.

What *is* module-specific is which repository and use case get constructed from that session - that wiring lives in `modules/<context>/adapters/api/dependencies.py`, turning `Depends(get_db_session)` into a `SqlAlchemyNodeRepository`, then a `CreateNode` use case. Sessions are per-request: the FastAPI dependency yields a session, commits on success, rolls back on exception, and always closes.

## Local adapters for fast testing

Every port ships an in-memory adapter as a first-class citizen alongside its real backend adapter - not a private test-only fake bolted onto a test file. Application-layer tests and router-level tests wire the in-memory adapter directly (constructor injection, or FastAPI `dependency_overrides` for router tests), so they need no live infrastructure and can't flake on a database connection. Only the tests that check the *real* backend adapter's correctness (a `SqlAlchemyNodeRepository` actually round-tripping through Postgres) are `@pytest.mark.integration` and may be skipped when that infrastructure isn't configured locally or in CI.

This isn't specific to persistence - it's the same shape the `SchedulerPort` will need later (Postgres/APScheduler/Cron adapters, plus an in-memory one for fast tests), so it's worth treating as a named convention rather than something reinvented per port.

## Domain entities

Conventions applied consistently across modules:

- Every entity/edge primary key is `uuid7` - time-ordered, so it works with keyset pagination without a separate sort key. List ports take this literally: pagination is `after: UUID | None` + `limit`, ordered by `id ASC`, not an offset - that's the concrete payoff of a time-ordered PK, not just a nice property left unused.
- Entities set their own timestamps in domain methods (`datetime.now(timezone.utc)`, alongside `uuid7()` generation) rather than via SQLAlchemy `server_default`/`onupdate` - timestamping is domain-meaningful behavior, not a persistence side effect, and keeping it in domain code makes it testable with `freezegun`/`time-machine` instead of requiring a live database.
- Mixins compose vertically rather than each entity declaring every concern itself: a `Timestamped` mixin, a `SoftDeletable` mixin that inherits `Timestamped` (because a lifecycle change is itself something that must be timestamped), and concrete entities like `Node(Identifiable, SoftDeletable)` inheriting `Timestamped` transitively.
- `kw_only=True, eq=False` on every mixin/entity dataclass - keyword-only keeps constructor calls unambiguous as fields accumulate across mixins; identity equality (by ID) is what these entities need, not field-by-field structural equality.

## Testing mirrors the architecture

Coverage floors are tiered to match how much of each layer's correctness is structural versus incidental: domain 100%, application 90%, infrastructure/API 80%. Domain code has no framework dependencies and should be exhaustively testable in isolation with plain unit tests; adapters carry integration surface (real sessions, real HTTP, real external services) where 100% coverage is either impractical or low-signal. `@pytest.mark.integration` separates the fast, domain-heavy loop from the slower suite that touches real adapters - so the dependency-direction rule is also what makes the fast test loop possible: everything below the adapter boundary can be tested without infrastructure at all.

`backend/tests/` mirrors `src/app/modules/<context>/{domain,application,adapters}` directory-for-directory, plus a top-level `tests/architecture/` suite that encodes the dependency-direction rule itself as an `archunitpython` test - domain may not depend on application/adapters/entrypoints, application may not depend on adapters/entrypoints, adapters may not depend on entrypoints. That test has no I/O and always runs; it's what catches an accidental import across the boundary before it becomes a design problem.

## Migrations

One Alembic environment, one `alembic/versions/` directory, for the whole backend - not one per module. All bounded contexts share a single Postgres schema in v1, so there's no reason yet to migrate modules independently. Each module's SQLAlchemy models register on the single shared `Base` from `platform/database.py`; `alembic/env.py` imports every module's `adapters/persistence/models.py` explicitly so their tables exist on `Base.metadata` before autogenerate runs.

## Running things

Backend tests, migrations, and quality checks run as `poe` tasks from the workspace root - `poe test-backend`, `poe test-backend-integration`, `poe migrate`, `poe lint-backend`, `poe typecheck-backend`, etc. The full task list lives in the root `pyproject.toml`.

## Unit of Work is scoped per bounded context

A transaction boundary is a module concern, not a whole-application one. `shared_kernel/unit_of_work.py` holds only the async-context-manager ceremony every unit of work needs - `__aenter__`/`__aexit__` with rollback-on-exception and always-release - as a small base class with no repository attributes of its own. Each module builds its own concrete unit of work on top of that base: `modules/graph/application/ports.py::GraphUnitOfWork` exposes `nodes`/`edges`, nothing else.

A single central unit of work listing every module's repositories was deliberately rejected: it would couple every module's use cases to every other module's repositories (the same repo-wide-`models/` problem the module-per-bounded-context structure exists to avoid), and it would imply transactions spanning bounded contexts - which DDD treats as the wrong boundary. Cross-context consistency is handled by referencing IDs and accepting eventual consistency, not by sharing one transactional object across contexts. When a second module needs a unit of work, it gets its own concrete class on the same shared base, not a slot added to `GraphUnitOfWork`.

This also fixes a real limitation of tying the transaction to the HTTP request/response cycle: the same use case is meant to be reachable from a CLI command (and eventually a scheduled job), neither of which has a "request" to hang a commit off of. Making the use case own the commit - via the unit of work it's given - means the transaction boundary travels with the use case regardless of which driving adapter called it.

**Commands take the unit of work; queries take a plain repository.** `CreateNode`/`CreateEdge` depend on `GraphUnitOfWork` and call `await uow.commit()` themselves once their invariants pass. `GetNode`/`ListNodes`/`GetEdge` are read-only and depend on `NodeRepository`/`EdgeRepository` directly - a read has no commit boundary to own. Correspondingly, the session dependency in `platform/database.py` only yields a session and always closes it; it does not auto-commit. Commit is something a use case decides to do, not something that happens to it implicitly at the edge of a request.

## CQRS is a typing convention, not a dispatcher

`shared_kernel/cqrs.py` defines two generic Protocols, `CommandHandler[TCommand, TResult]` and `QueryHandler[TQuery, TResult]`. Every use case gets a matching `*Command`/`*Query` dataclass (`CreateNodeCommand`, `GetNodeQuery`, ...) and implements the corresponding handler Protocol, so `mypy --strict` verifies every use case in every module is shaped the same way.

There's deliberately no bus or mediator sitting between a router/CLI command and the use case it calls - the router still calls the use case directly, exactly as shown above. A full command/query bus with pipeline behaviors would give a single seam for cross-cutting concerns (logging, authorization) applied uniformly across every use case, but nothing in a single-owner application with no authorization model yet needs that uniformity enforced. The typed-handler convention is a strict prerequisite for a bus regardless, so adopting it now doesn't foreclose adding one later if a concrete cross-cutting need shows up (most likely once auth lands).
