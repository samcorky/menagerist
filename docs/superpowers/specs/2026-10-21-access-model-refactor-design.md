# Access model refactor: design

Status: decided 2026-10-21 with Sam. Implementation plan: `docs/superpowers/plans/2026-10-20-access-model-refactor.md`. Related: `2026-10-20-api-tokens-and-permissions.md` (builds on this; its Phase 1 rename is replaced by this work).

## Intent

Every use case declares, in one explicit and test-enforced way, who may call it. Authorisation is enforced in one `final` method behind one guard. Persistence (unit of work, repositories, other ports) stays a separate concern. "Deliberately open" and "forgot the check" stop looking identical, tokens get their session-only rule for free, and resource-level sharing later changes one guard, not 100 handlers.

## Goals, non-goals, anti-goals

- Goal: no behaviour change for any user, API client or CLI command. Each use case's stance records what it does today.
- Goal: a use case without a stance fails an architecture test.
- Non-goal: new permissions, role changes, API tokens, sharing, resource-level access (Phase 6 of the old proposal; the tokens plan and a later sharing plan).
- Anti-goal: a stance that silently widens who can call something. The set of `Public`, `System` and `Shared` use cases is pinned by name in a test that Sam reviews.

## Why now

Today "plain" `CommandHandler`/`QueryHandler` mean three things (public flows, own-account actions, shared catalogue), the ownership check is manual in 43 scoped use cases, and a use case cannot need both a permission and an ownership filter through the bases. Tokens (next) need "session-only" and "grantable" as first-class ideas.

## Decisions

| Question | Decision | Basis |
|---|---|---|
| Names | `ContentFilter` (was `AccessScope`), `Access`, `AccessGuard`, stances below | Sam: defaults ok |
| Shared catalogue (item types, edge types, presets, query validation) | New `Shared` stance: any signed-in actor. Converting to `Requires(permission)` later is a one-line change per use case, done in the tokens plan | Sam, 2026-10-21 |
| `scope()` misuse | Runtime `TypeError` when a non-`Content` use case calls it; no extra base classes | default |
| Background and CLI jobs | `System` stance: only `SYSTEM_ACTOR` | default |
| Guard shape | One `AccessGuard` injected everywhere, replacing `AuthorizationPort` and `AccessPolicy` injections | default |
| `Public` use cases | Still take the guard, for one constructor shape | default |

### My calls (not in the old proposal; check these)

1. **`Content` and `Shared` carry no permission yet.** The old sketch gave `Content` a permission, but `MEMBER_PERMISSIONS` is empty and no scoped use case checks a permission today, so a permission here would lock members out. Both stances mean "signed in", and `Content` adds the ownership filter. They gain a permission in the tokens plan, the same way `Shared` does.
2. **`Requires` is not generic.** The old `TPermission` type parameter guarded against cross-module mix-ups at type-check time. An architecture test replaces it: a declared permission must be in `ALL_PERMISSIONS` and belong to the use case's own module.
3. **`access` is enforced by an architecture test**, not at construction time. `__init_subclass__` runs before `ABCMeta` knows what is abstract, and handlers write their own `__init__`.
4. **`AccessGuard` also has `assert_can_delete`**, which the old sketch dropped but `AccessPolicy` has today.
5. **Anonymous is denied by the guard before any permission lookup** for every stance except `Public`. `RoleAuthorizationAdapter` treats any non-admin, non-system actor as a member, so a later non-empty `MEMBER_PERMISSIONS` would otherwise grant the anonymous actor those permissions.
6. **New bases coexist under temporary names** (`GuardedUseCase`, `GuardedCommandHandler`, `GuardedQueryHandler`) and take the final names in the last task.

## The stances (`shared_kernel/access.py`)

| Stance | Allows | Refuses |
|---|---|---|
| `Public()` | anyone, including the anonymous actor | nothing |
| `System()` | `SYSTEM_ACTOR` | everyone else |
| `OwnAccount()` | a signed-in session actor acting on themselves | anonymous, system |
| `Shared()` | any signed-in actor, system included | anonymous |
| `Content()` | as `Shared`, plus `scope()` and the `assert_can_*` calls | anonymous |
| `Requires(permission)` | an actor whose role grants `permission` | anonymous |

Refusals raise `ForbiddenError` ("You do not have permission to do that."), the error `AuthorizationPort.check` raises today. Routers already reject anonymous callers before a handler runs; the guard is defence in depth.

## Interfaces

- `AccessGuard` (Protocol, `shared_kernel/access_guard.py`): `async check(actor, access)`, `scope_for(actor) -> ContentFilter`, `assert_can_view/modify/delete(actor, owner_id)`. Ships `InMemoryAccessGuard` beside it (like `InMemoryUnitOfWork`): records checks, can be told to deny.
- `RoleAccessGuard` (`entrypoints/api/shared/access_guard.py`): wraps `RoleAuthorisationAdapter` and `OwnerAccessPolicy`.
- `GuardedUseCase[TRequest, TResult]`: `access: ClassVar[Access]`, `_guard`, `@final handle`, abstract `_handle`, `scope(actor)`.
- `GuardedCommandHandler[TUoW, TCommand, TResult]` takes `(uow, guard)`; `GuardedQueryHandler[TRepos, TQuery, TResult]` takes `(repos, guard)`. Persistence-free use cases extend `GuardedUseCase` and take their own ports plus `guard`.

## Stance inventory (today's behaviour, 106 use cases)

| Module | Use cases | Stance |
|---|---|---|
| system | `GetHealth`, `GetHealthReady`, `GetVersion` | `Public` |
| system | the 3 `Authorised*` detail/readiness use cases | `Requires` (unchanged) |
| backup | `RestoreOnFirstRun` (called with the anonymous actor behind the setup gate) | `Public` |
| backup | 8 `AuthorisedUseCase` | `Requires` (unchanged) |
| backup | 4 `Scoped*` | `Content` |
| identity | `SignIn`, `SignOut`, `SetupFirstAdmin`, `GetCurrentUser`, `GetSetupStatus`, `HasAdministrator` | `Public` |
| identity | `ChangePassword`, `RevokeOtherSessions`, `RevokeOwnSession`, `SetOwnDisplayName`, `ListOwnSessions` | `OwnAccount` |
| identity | 7 `Authorised*` | `Requires` (unchanged) |
| presets | all 7 | `Shared` |
| graph | `Create/Update/Get/List` node and edge types, `ValidateQuery` | `Shared` |
| graph | `ClaimOrphanedItems` | `System` |
| graph | 5 `AuthorisedCommandHandler` | `Requires` (unchanged) |
| graph, collections, examples, media | every `Scoped*` | `Content` |
| media | `StageMedia` (no policy call today; verify while migrating) | `Content` |
| collections, examples, media | `ClaimLegacyCollections`, `ClaimOrphanedInstallations`, `ClaimOrphanedMedia` | `System` |

Rule for any case not listed or found wrong during migration: the stance is whatever kind of actor its callers pass today (grep the router, CLI and bridges). Report a mismatch to Sam instead of choosing.

## Left to the builder

File-by-file mechanics of each migration, test helper reuse, and wording of docstrings (Google style, British English, short).
