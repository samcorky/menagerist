# Access model refactor: declared access stances, one guard, fewer handler bases

Status: proposal, nothing implemented; names and open questions below are not confirmed by Sam. Written 2026-10-20 from a design discussion. Facts come from `shared_kernel/cqrs.py`, `shared_kernel/actor.py`, `entrypoints/api/shared/{authorization,permissions,dependencies,access_policy,permission_aware_route}.py`, `tests/architecture/test_permission_catalogue.py`, three example use cases (`graph/application/{update_node,get_node,delete_node_type}.py`) and a count of every use case class in `modules/*/application/`. The sketches are not compiled or type-checked.

Related plans: `api-tokens-and-permissions-plan.md` (this plan is its foundation; it replaces that plan's Phase 1 rename and shapes its Phase 2), `csrf-header-protection-plan.md` (independent), `settings-handoff-plan.md` (independent).

Working rules (from `AGENTS.md` / `CLAUDE.md`): never create, stage or push commits (ask Sam to commit); British English; `.svelte` and `.svelte.ts` files go through the `svelte-file-editor` subagent; run only the relevant `poe` checks for touched code (`poe lint-backend`, `poe typecheck-backend` (mypy --strict), `poe test-backend`, `poe coverage` before calling backend work done); coverage floors (domain, application, shared_kernel 100%, adapters 80%, platform 70%); every port ships an in-memory sibling; domain errors subclass `shared_kernel.errors`; no try/except in routers; the clone is read-only here, so deliver complete files for Sam to commit. Beware: running Python from inside `backend/src/app/modules` fails, because the `collections` module there shadows the standard library; run scripts from elsewhere with `python3 -I`.

## Goal

Every use case declares, in one explicit and test-enforced way, who may call it. Authorisation (permission, ownership filter, session-only) is enforced in one `final` method behind one guard. Persistence (unit of work, repos, other ports) stays a separate concern. This makes "forgot to add a check" impossible, gives API tokens their session-only rule for free, and gives resource-level permissions and sharing a single place to change later.

## What exists today (class counts in `application/`)

| Base | Count | Used for |
|---|---|---|
| `UseCase` | 3 | system health and version (no persistence, no check) |
| `CommandHandler` | 21 | sign-in, sign-out, set-up, own-account changes, graph type create/update, presets, "claim orphaned" jobs (a UoW, no check) |
| `QueryHandler` | 11 | set-up status, own sessions, type and preset reads (repos, no check) |
| `ScopedCommandHandler` / `ScopedQueryHandler` | 26 / 17 | items, media, collections, examples (ownership through `AccessPolicy`, called by hand) |
| `AuthorisedUseCase` | 6 | backup (permission check, no UoW) |
| `AuthorisedCommandHandler` / `AuthorisedQueryHandler` | 10 / 4 | admin identity, graph schema deletion and purge, system detail (permission check, UoW or repos) |

Problems this plan fixes:
1. "Plain" `CommandHandler`/`QueryHandler` mean three things: public pre-sign-in flows, own-account actions, and shared catalogue content. "Deliberately open" and "forgot the check" look identical.
2. The permission check is automatic (`handle()` is `@final`, subclasses write `_handle()`); the ownership check is manual in each scoped use case (`policy.scope_for`, `assert_can_modify`). Scoped and plain handlers override `handle()` directly.
3. A use case cannot need both a permission and a content filter through the base classes (`DeleteNodeType` builds `AccessScope.everyone()` by hand).
4. Three persistence-free variants exist because the other bases force a UoW or repos. Those use cases do not have "no dependencies": they take ports such as `BackupStore`, `DatabaseSnapshot`, `MediaFiles`, `HealthCheckPort`, `AppInfoPort`.
5. Spelling: `Authorised*` classes but `AuthorizationPort` and `RoleAuthorizationAdapter` (British English rule).
6. To verify: graph node and edge type create/update use plain `CommandHandler`, so any signed-in member can change the shared schema. Intended?

## Target design

Declarations (in `shared_kernel/access.py`):
```python
@dataclass(frozen=True)
class Public: ...                  # anyone, including signed out (sign-in, set-up, health)
@dataclass(frozen=True)
class OwnAccount: ...              # any signed-in session actor acting on themselves
@dataclass(frozen=True)
class Requires[P: StrEnum]:        # a permission, no ownership filtering (admin work, shared catalogue)
    permission: P
@dataclass(frozen=True)
class Content[P: StrEnum]:         # a permission plus the content filter (items, media, collections)
    permission: P

Access = Public | OwnAccount | Requires[Any] | Content[Any]
```
Possible fifth stance for background and CLI jobs (see Q4).

Guard (replaces separate `AuthorizationPort` and `AccessPolicy` injections; ships an in-memory sibling):
```python
class AccessGuard(Protocol):
    async def check(self, actor: Actor, access: Access) -> None: ...
    def scope_for(self, actor: Actor) -> ContentFilter: ...
    def assert_can_view(self, actor: Actor, owner_id: UUID | None) -> None: ...
    def assert_can_modify(self, actor: Actor, owner_id: UUID | None) -> None: ...
```
`check()` rules: `Public` allows (the actor is not looked at, so probes can pass the anonymous actor); `OwnAccount` requires a signed-in session actor (`actor.grants is None` once tokens exist, so tokens are refused here); `Requires` and `Content` require the role to grant the permission and, for a token actor, the token to grant it too.

Three bases (root plus two thin persistence layers):
```python
class UseCase[TRequest, TResult](ABC):
    access: ClassVar[Access]            # a concrete subclass without it cannot be built
    _guard: AccessGuard

    @final
    async def handle(self, request: TRequest, actor: Actor) -> TResult:
        await self._guard.check(actor, self.access)
        return await self._handle(request, actor)

    @abstractmethod
    async def _handle(self, request: TRequest, actor: Actor) -> TResult: ...

    def scope(self, actor: Actor) -> ContentFilter:
        assert isinstance(self.access, Content)   # only Content use cases may filter by owner
        return self._guard.scope_for(actor)

class CommandHandler[TUoW, TCommand, TResult](UseCase[TCommand, TResult], ABC):
    def __init__(self, uow: TUoW, guard: AccessGuard) -> None: ...   # adds the commit boundary

class QueryHandler[TRepos, TQuery, TResult](UseCase[TQuery, TResult], ABC):
    def __init__(self, repos: TRepos, guard: AccessGuard) -> None: ...  # repos, no commit
```
Persistence-free use cases (backup, system) extend `UseCase` directly and inject their own ports plus `guard`; `AuthorisedUseCase` disappears.

How existing classes read:
```python
class GetNode(QueryHandler[GraphRepos, GetNodeQuery, Node]):
    access = Content(GraphPermission.READ_NODE)

class DeleteNodeType(CommandHandler[GraphUnitOfWork, DeleteNodeTypeCommand, None]):
    access = Requires(GraphPermission.DELETE_NODE_TYPE)     # was AuthorisedCommandHandler

class SignIn(CommandHandler[IdentityUoW, SignInCommand, SignInResult]):
    access = Public()

class ChangePassword(CommandHandler[IdentityUoW, ChangePasswordCommand, None]):
    access = OwnAccount()

class ListBackups(UseCase[ListBackupsQuery, list[Backup]]):
    access = Requires(BackupPermission.READ)
    def __init__(self, store: BackupStore, guard: AccessGuard) -> None: ...

class GetVersion(UseCase[GetVersionQuery, AppInfo]):
    access = Public()
```
Per-module typing: keep the old `TPermission` cross-module protection with a thin helper per module, for example `def graph(p: GraphPermission) -> Content[GraphPermission]`, so a graph use case cannot declare a backup permission.

Design notes:
- Every use case's `_handle` replaces `handle`; the signature test (`tests/shared_kernel/test_cqrs.py`) must forbid overriding `handle`, allow `guard` in any constructor, and require `access` on every concrete class.
- Session-only for API tokens falls out of the stances: `Public` and `OwnAccount` are never granted to tokens. Permissions still need a "grantable to tokens" flag in the catalogue (see the tokens plan).
- Resource-level readiness: handlers only call `self.scope(actor)` and `guard.assert_can_*`, so sharing and per-token resource limits later change the guard, the policy and the repositories, not 43 handlers.

## Phases (each shippable on its own; run the relevant `poe` checks after each)

### Phase 1: mechanical renames (no behaviour change)
- `AccessScope` -> `ContentFilter` (suggested), so "scope" is free for token scopes; update the ~53 files that mention it, `tests/architecture/test_access_scope_rules.py` (rename too), docs wording.
- `AuthorizationPort` / `RoleAuthorizationAdapter` / `get_authorization_port` -> British spelling (`Authorisation...`). Separate commit or PR from the first rename.
- `Scoped*Handler` keeps its name until Phase 4 (it disappears there).
- **Checkpoint Q1:** final names.

### Phase 2: declare access on today's classes (still no behaviour change)
- Add `access = ...` to every use case on the existing bases, using the stance names above as plain declarations (the `Access` types and an `ACCESS` marker only; nothing enforces them yet except the test).
- Architecture test: every concrete `UseCase` subclass in `application/` declares `access`; a `Requires`/`Content` permission is in the catalogue; the `Public` list is small and explicit and reviewed by Sam; `Content` use cases are the ones that use the scoped bases today.
- This is where the unverified question lands: decide per use case whether graph type create/update, presets and the shared catalogue are `Requires(...)` (need a new permission) or stay open to members (`Content`/new `Shared`?). **Checkpoint Q2.**
- Flush out classes that have no obvious stance (system-actor jobs, CLI-only flows). **Checkpoint Q4.**

### Phase 3: introduce the guard and the new bases beside the old ones
- `AccessGuard` protocol, a real implementation that wraps `RoleAuthorizationAdapter` and `OwnerAccessPolicy`, and an in-memory sibling for tests.
- New `UseCase`/`CommandHandler`/`QueryHandler` in `shared_kernel/cqrs.py` under temporary names or a new module while the old ones remain; the composition root provides one guard everywhere.
- Unit tests for each stance with fake actors: public with the anonymous actor; own-account with and without a session; permission present/absent; content stance exposes `scope()` and other stances assert.

### Phase 4: migrate module by module (old and new bases coexist)
Order (smallest and most self-contained first): system, backup (persistence-free), identity, presets and examples, collections, media, graph. For each class: change the base, move the body to `_handle`, replace `self._policy` with `self.scope(actor)` and `self._guard`, update the constructor and its unit test. After each module: `poe lint-backend`, `poe typecheck-backend`, `poe test-backend`; `poe coverage` at the end of the phase.

### Phase 5: remove the old bases
- Delete `ScopedCommandHandler`, `ScopedQueryHandler`, `AuthorisedUseCase`, `AuthorisedCommandHandler`, `AuthorisedQueryHandler`, `_PolicyHolder`, `_PermissionGate` and the old tests. Update `AGENTS.md`, `backend/README.md` and `docs/DECISIONS.md` (new entry), `ARCHITECTURE.md` if it names the bases.

### Phase 6 (later, with sharing or per-resource tokens): resource-level access
Not part of this refactor; it is what this refactor prepares for. Needed then:
- `ContentFilter` becomes a predicate ("owned by me OR shared with me OR in my token's allowed set") and repositories translate it (share table join, indexes).
- `assert_can_view/modify(actor, owner_id)` becomes `assert_can_*(actor, resource_ref)` with id and kind so the policy can look up shares.
- Decide inheritance (does sharing a collection share its items and media?), share management endpoints, the effect of deleting a user on their shares, and per-token resource limits (intersect the filter).
- Sam said (2026-10-20) resource-level permissions are wanted later.

## Risks
- Phase 4 touches about 100 classes. Mitigation: module-by-module, old and new bases coexist, tests green after each.
- A wrong stance silently changes who can call something. Mitigation: Phase 2 records today's behaviour first (stance = what it does now), the architecture test lists all `Public` use cases, and member-can-still-do-everything tests exist before Phase 4.
- `scope()` asserting at call time catches misuse at test time, not type-check time. Accept, or split `ContentCommandHandler` and `ContentQueryHandler` subclasses if static checking is wanted (Q3).
- Constructor changes ripple into the composition root and every unit test that builds a handler.

## Open questions
- **Q1:** final names (`ContentFilter`, `Access`, `Public`/`OwnAccount`/`Requires`/`Content`, `AccessGuard`).
- **Q2:** are graph node/edge type create/update, presets and other shared catalogue operations meant to be open to every member, and under which stance (`Requires` with a new member-held permission, or a dedicated `Shared` stance)?
- **Q3:** enforce "only Content use cases may call `scope()`" at runtime (assert) or by separate base classes?
- **Q4:** background jobs and CLI flows that run as `SYSTEM_ACTOR` (`ClaimOrphaned*`, `CleanupExpiredMedia`, `PruneBackups`, others): a `System` stance, or `Requires` with a permission only the system holds?
- **Q5:** one `AccessGuard` object, or keep two injections (authorisation and policy)? One is simpler to inject; two keeps the existing ports.
- **Q6:** should `Public` use cases still take a guard for uniformity, or is a guard-less `PublicUseCase` simpler for health probes?
