# Access Model Refactor Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Every use case declares who may call it (`access = ...`), and one `final` method behind one `AccessGuard` enforces it, with no behaviour change.

**Architecture:** New `Guarded*` bases and an `AccessGuard` are added beside the old bases. Modules migrate one at a time (old and new coexist, tests green after each), then the old bases are deleted and `Guarded*` takes the final names `UseCase`/`CommandHandler`/`QueryHandler`.

**Tech Stack:** Python 3.14, FastAPI, pytest, mypy --strict, archunitpython, `poe` tasks.

**Spec:** `docs/superpowers/specs/2026-10-21-access-model-refactor-design.md` (stances, decisions, stance inventory). Read it first; this plan does not repeat it.

## Global Constraints

- Never run `git add`, `git commit` or push. Every "Stop" step means: tell Sam what changed and ask them to commit.
- British English in code, comments and docs (`Authorisation`, not `Authorization`) except the HTTP `Authorization` header, which must not change.
- Comments short and only where intent is unclear; Google-style docstrings.
- Run only relevant checks: `poe lint-backend`, `poe typecheck-backend` (mypy --strict), `poe test-backend`; `poe coverage` before calling the work done. Floors: domain, application, shared_kernel 100%; adapters 80%; platform 70%.
- Entity and mixin dataclasses use `kw_only=True, eq=False`; frozen value dataclasses as in `shared_kernel/access_scope.py`.
- Do not run Python from inside `backend/src/app/modules` (its `collections` package shadows the standard library); use `uv run python -I` from `backend/`.
- No behaviour change: an HTTP or CLI caller that succeeded before succeeds now, and vice versa.

## Review Focus

1. Anonymous actor against `Requires` when `MEMBER_PERMISSIONS` is later non-empty: must be denied before any permission lookup (Task 3).
2. `SYSTEM_ACTOR` calling an `OwnAccount` use case is denied; CLI flows that use `SYSTEM_ACTOR` must only hit `System`, `Shared`, `Content` or `Requires` use cases (Tasks 3, 6).
3. A non-`Content` use case calling `self.scope(actor)` raises `TypeError` (Task 4).
4. A subclass overriding `handle`, or a concrete use case with no `access`, fails an architecture test (Task 5).
5. The `Public`/`System`/`Shared` sets are pinned by name; adding one without editing the pin fails (Task 5).
6. `PermissionAwareRoute` finds use cases by the old base classes and reads `required_permission`, so a migrated use case would silently drop out of the OpenAPI docs, and `test_cross_user_isolation.py` (which treats `x-required-permission` as "admin only, skip") would start testing admin routes as member routes. The documented operations must be identical before and after (Task 5a).

---

## File structure

- Create `backend/src/app/shared_kernel/access.py`: the stance dataclasses and the `Access` union.
- Create `backend/src/app/shared_kernel/access_guard.py`: `AccessGuard` Protocol and `InMemoryAccessGuard`.
- Create `backend/src/app/shared_kernel/guarded.py`: `GuardedUseCase`, `GuardedCommandHandler`, `GuardedQueryHandler` (temporary names).
- Create `backend/src/app/entrypoints/api/shared/access_guard.py`: `RoleAccessGuard`, `get_access_guard`.
- Modify `entrypoints/api/shared/permission_aware_route.py` (Tasks 5a and 7); create `tests/entrypoints/api/shared/test_openapi_permissions_pinned.py`.
- Modify `shared_kernel/actor.py` (`is_anonymous`), `entrypoints/api/shared/dependencies.py`, every module's `adapters/api/dependencies.py` and CLI wiring, every `application/*.py` use case.
- Delete at the end: the old bases in `shared_kernel/cqrs.py`, `shared_kernel/access_policy.py`, `entrypoints/api/shared/access_policy.py` (folded into the guard).
- Tests: `tests/shared_kernel/test_access.py`, `test_access_guard.py`, `test_guarded.py` (new); `tests/architecture/test_access_stances.py` (new); update `test_cqrs.py`, `test_access_scope_rules.py` (renamed in Task 1), `test_permission_catalogue.py`.

---

### Task 1: Rename `AccessScope` to `ContentFilter`

**Files:** Rename `shared_kernel/access_scope.py` -> `content_filter.py`, `tests/shared_kernel/test_access_scope.py` -> `test_content_filter.py`, `tests/architecture/test_access_scope_rules.py` -> `test_content_filter_rules.py`; modify the ~148 files that mention `AccessScope` or `access_scope`.

**Interfaces:**
- Produces: `app.shared_kernel.content_filter.ContentFilter` with the same members (`user_id`, `of`, `everyone`, `is_everyone`, `covers`). Variable and parameter names such as `scope` stay.

- [ ] **Step 1: Rename the three files** with `mv` (no git commands).
- [ ] **Step 2: Replace identifiers** across `backend/` and `docs/`: `AccessScope` -> `ContentFilter`, `access_scope` -> `content_filter`, `test_access_scope_rules` -> `test_content_filter_rules`. Use a single `sed -i` over `grep -rl` results; skip `.venv`, `node_modules`, `__pycache__`, and the `frontend/src/lib/api/generated/` directory.
- [ ] **Step 3: Verify nothing remains:** `grep -rn "AccessScope\|access_scope" backend docs AGENTS.md` returns no hits except historical notes in `docs/superpowers/plans/` and `docs/DECISIONS.md`; leave those.
- [ ] **Step 4: Run** `poe lint-backend && poe typecheck-backend && poe test-backend`. Expected: all pass.
- [ ] **Step 5: Stop.** Ask Sam to commit ("refactor: rename AccessScope to ContentFilter").

### Task 2: British spelling for the authorisation port

**Files:** `shared_kernel/authorization.py` -> `authorisation.py`; `entrypoints/api/shared/authorization.py` -> `authorisation.py`; `tests/shared_kernel/test_authorization_port.py` -> `test_authorisation_port.py`; ~52 referencing files.

**Interfaces:**
- Produces: `AuthorisationPort`, `RoleAuthorisationAdapter`, `get_authorisation_port`, `get_role_authorisation`, modules `app.shared_kernel.authorisation` and `app.entrypoints.api.shared.authorisation`. The `check(actor, action)` signature is unchanged.

- [ ] **Step 1: Rename files and replace identifiers:** `AuthorizationPort`, `RoleAuthorizationAdapter`, `get_authorization_port`, `get_role_authorization`, `shared_kernel.authorization`, `shared.authorization`, and constructor parameter names `authorization`/`_authorization` where they refer to the port (leave any `Authorization` HTTP header, `authorization` in test headers and OpenAPI text untouched; review the diff for those).
- [ ] **Step 2: Run** `poe lint-backend && poe typecheck-backend && poe test-backend`. Expected: pass.
- [ ] **Step 3: Stop.** Ask Sam to commit ("refactor: use British spelling for the authorisation port").

### Task 3: Stances, `AccessGuard`, `RoleAccessGuard`

**Files:** Create `shared_kernel/access.py`, `shared_kernel/access_guard.py`, `entrypoints/api/shared/access_guard.py`; modify `shared_kernel/actor.py`, `entrypoints/api/shared/dependencies.py`; tests `tests/shared_kernel/test_access.py`, `tests/shared_kernel/test_access_guard.py`, `tests/entrypoints/api/shared/test_access_guard.py`, `tests/shared_kernel/test_actor.py`.

**Interfaces:**
- Produces in `access.py`: frozen dataclasses `Public`, `System`, `OwnAccount`, `Shared`, `Content` (no fields) and `Requires(permission: StrEnum)`; `Access = Public | System | OwnAccount | Shared | Content | Requires`.
- Produces in `Actor`: `is_anonymous` property (`"anonymous" in roles`).
- Produces in `access_guard.py`: `class AccessGuard(Protocol)` with `async def check(self, actor: Actor, access: Access) -> None`, `scope_for(self, actor: Actor) -> ContentFilter`, `assert_can_view / assert_can_modify / assert_can_delete(self, actor: Actor, owner_id: uuid.UUID | None) -> None`; and `class InMemoryAccessGuard` with the same methods that records `checked: list[tuple[Actor, Access]]` and takes `deny: bool = False` (raises `ForbiddenError` from `check` when true), `scope_for` returning `ContentFilter.of(actor.id)` (everyone for the system actor), `assert_can_*` delegating to an `OwnerAccessPolicy`-equivalent rule (own content or system).
- Produces in `entrypoints/api/shared/access_guard.py`: `class RoleAccessGuard(authorisation: AuthorisationPort, policy: AccessPolicy)` implementing `AccessGuard`, and `get_access_guard() -> AccessGuard` returning one process-wide instance built from `get_authorisation_port()` and `OwnerAccessPolicy()`.

- [ ] **Step 1: Write failing tests** in `tests/entrypoints/api/shared/test_access_guard.py` (parametrised over actors `ANONYMOUS_ACTOR`, `SYSTEM_ACTOR`, a member `Actor(roles={"member"})`, an admin) asserting the allow/refuse table in the spec for every stance, plus:
  - `Requires(p)` for the anonymous actor raises `ForbiddenError` even when the injected authorisation allows everything (Review Focus 1);
  - `Requires(p)` for a member delegates to the authorisation port and propagates its `ForbiddenError`;
  - `scope_for`, `assert_can_view/modify/delete` give the same results as `OwnerAccessPolicy` for the same inputs.
  In `test_access_guard.py`: `InMemoryAccessGuard` records the checked pairs and raises when `deny=True`. In `test_actor.py`: `ANONYMOUS_ACTOR.is_anonymous` is true, the others false.
- [ ] **Step 2: Run** `poe test-backend -- tests/shared_kernel tests/entrypoints/api/shared -q`. Expected: FAIL (modules missing).
- [ ] **Step 3: Implement** the interfaces above. `RoleAccessGuard.check` is a `match` over the stance type: `Public` returns; `System` requires `actor.is_system`; `OwnAccount` requires not anonymous and not system; `Shared`/`Content` require not anonymous; `Requires` requires not anonymous, then `await authorisation.check(actor, access.permission)`. Every refusal raises `ForbiddenError("You do not have permission to do that.")`. `scope_for` and `assert_can_*` delegate to `policy`.
- [ ] **Step 4: Run** the same command. Expected: PASS; then `poe typecheck-backend`.
- [ ] **Step 5: Stop.** Ask Sam to commit ("feat(access): add access stances and the access guard").

### Task 4: `Guarded*` bases

**Files:** Create `shared_kernel/guarded.py`; test `tests/shared_kernel/test_guarded.py`.

**Interfaces:**
- Consumes: `Access`, `Content`, `AccessGuard`, `ContentFilter`.
- Produces: `GuardedUseCase[TRequest, TResult]` (ABC): `access: ClassVar[Access]`; `__init__` is left to subclasses but they must set `self._guard: AccessGuard`; `@final async def handle(self, request, actor) -> TResult` doing `await self._guard.check(actor, self.access)` then `return await self._handle(request, actor)`; `@abstractmethod async def _handle(...)`; `def scope(self, actor: Actor) -> ContentFilter` that raises `TypeError` unless `isinstance(self.access, Content)`, else `self._guard.scope_for(actor)`.
  `GuardedCommandHandler[TUoW, TCommand, TResult]`: `__init__(self, uow: TUoW, guard: AccessGuard)` setting `_uow`, `_guard`. `GuardedQueryHandler[TRepos, TQuery, TResult]`: `__init__(self, repos: TRepos, guard: AccessGuard)` setting `_repos`, `_guard`.

- [ ] **Step 1: Write failing tests** (using `InMemoryAccessGuard`): `handle` checks `(actor, cls.access)` before `_handle` runs and a denying guard stops `_handle` (assert it did not run); command handler stores `_uow` and `_guard`; query handler stores `_repos` and `_guard`; `scope()` returns the guard's filter for a `Content` use case and raises `TypeError` for `Shared`, `Public`, `Requires` (Review Focus 3).
- [ ] **Step 2: Run** `poe test-backend -- tests/shared_kernel/test_guarded.py -q`. Expected: FAIL.
- [ ] **Step 3: Implement** the interfaces. Keep `cqrs.py` untouched.
- [ ] **Step 4: Run** the test and `poe typecheck-backend`. Expected: PASS.
- [ ] **Step 5: Stop.** Ask Sam to commit ("feat(access): add guarded use case bases").

### Task 5: Architecture tests for stances

**Files:** Create `tests/architecture/test_access_stances.py`; modify `tests/architecture/test_permission_catalogue.py`.

**Interfaces:**
- Consumes: `GuardedUseCase` and the `Access` types; module discovery as in `test_permission_catalogue._use_cases()`.

- [ ] **Step 1: Write the tests** (they pass trivially now, because no use case is guarded yet; they bite as modules migrate):
  - every concrete (non-abstract) `GuardedUseCase` subclass in `app.modules.*.application` has `access` as an `Access` instance (`"access" in vars(cls)` somewhere in the MRO below `GuardedUseCase`);
  - no concrete `GuardedUseCase` subclass defines `handle` in its own `__dict__` (Review Focus 4);
  - `Requires` permissions are in `ALL_PERMISSIONS` and are members of an enum defined in the same module's `application.permissions`;
  - `Public`, `System` and `Shared` sets are pinned: three `frozenset[str]` constants of `module.ClassName` strings (`EXPECTED_PUBLIC`, `EXPECTED_SYSTEM`, `EXPECTED_SHARED`), start empty, filled by the module tasks; the test asserts the actual sets equal them (Review Focus 5);
  - `Content` use cases are exactly those on the old `Scoped*` bases before migration. Express this as the pin `EXPECTED_CONTENT`, also filled by the module tasks.
- [ ] **Step 2: Run** `poe test-backend -- tests/architecture -q`. Expected: PASS (vacuous).
- [ ] **Step 3: Stop.** Ask Sam to commit ("test(access): enforce access stances on every use case").

### Task 5a: Keep `PermissionAwareRoute` working across the migration

`PermissionAwareRoute` (`entrypoints/api/shared/permission_aware_route.py`) documents permissions in OpenAPI and passes today (`test_permission_aware_route.py`, `test_auth_router.py::test_openapi_documents_the_new_responses_and_permissions`, the Swagger e2e spec). It only documents; it enforces nothing, and it stays that way. Only `Requires` use cases are documented, exactly as `Authorised*` ones are today.

**Files:** Modify `permission_aware_route.py`; create `tests/entrypoints/api/shared/test_openapi_permissions_pinned.py`; extend `tests/entrypoints/api/shared/test_permission_aware_route.py`.

**Interfaces:**
- Produces: `_find_use_case_type(endpoint)` recognises both the legacy `UseCase`/`CommandHandler` and `GuardedUseCase`/`GuardedCommandHandler`, still preferring a command handler of either kind; `_permission_value` input comes from `required_permission` (legacy) or from `access.permission` when `access` is a `Requires`. No other stance adds a description, `x-required-permission` or `Security` dependency.

- [ ] **Step 1: Pin today's output before touching anything.** Create `test_openapi_permissions_pinned.py` with `EXPECTED: dict[tuple[str, str], str]` mapping `(path, method)` to the permission value for every operation in `create_app().openapi()["paths"]` that has `x-required-permission` (generate it once with `uv run python -I` from `backend/`, then paste it as a literal). The test asserts the live mapping equals `EXPECTED`, and that every other operation has no `x-required-permission` and no "Requires permission" in its description. Run it: PASS.
- [ ] **Step 2: Write failing tests** in `test_permission_aware_route.py` with dummy guarded use cases and `InMemoryAccessGuard`: `_find_use_case_type` returns a `GuardedCommandHandler` over a `GuardedQueryHandler` in either parameter order; a `Requires(Permission.GRAPH_READ)` use case produces the same `x-required-permission`, description line and `APIKeyCookie` security as the legacy `DocumentedUseCase`; `Public()`, `System()`, `OwnAccount()`, `Shared()` and `Content()` use cases produce no `x-required-permission`, no extra description and no `security`.
- [ ] **Step 3: Run** `poe test-backend -- tests/entrypoints/api/shared/test_permission_aware_route.py -q`. Expected: the guarded cases FAIL.
- [ ] **Step 4: Implement** the interfaces: accept a tuple of base classes in the `issubclass` checks, and add `_declared_permission(use_case_cls)` returning `access.permission` for `Requires`, else the legacy `required_permission` attribute, else `None`.
- [ ] **Step 5: Run** the two test files above, `tests/entrypoints/test_cross_user_isolation.py` and `poe typecheck-backend`. Expected: PASS.
- [ ] **Step 6: Stop.** Ask Sam to commit ("feat(openapi): document Requires stances in PermissionAwareRoute").

### Task 5a: Keep `PermissionAwareRoute` working across the migration

`PermissionAwareRoute` (`entrypoints/api/shared/permission_aware_route.py`) documents permissions in OpenAPI and passes today (`test_permission_aware_route.py`, `test_auth_router.py::test_openapi_documents_the_new_responses_and_permissions`, the Swagger e2e spec). It only documents; it enforces nothing, and it stays that way. Only `Requires` use cases are documented, exactly as `Authorised*` ones are today.

**Files:** Modify `permission_aware_route.py`; create `tests/entrypoints/api/shared/test_openapi_permissions_pinned.py`; extend `tests/entrypoints/api/shared/test_permission_aware_route.py`.

**Interfaces:**
- Produces: `_find_use_case_type(endpoint)` recognises both the legacy `UseCase`/`CommandHandler` and `GuardedUseCase`/`GuardedCommandHandler`, still preferring a command handler of either kind; the permission comes from `required_permission` (legacy) or from `access.permission` when `access` is a `Requires`. No other stance adds a description, `x-required-permission` or `Security` dependency.

- [ ] **Step 1: Pin today's output before touching anything.** Create `test_openapi_permissions_pinned.py` with `EXPECTED: dict[tuple[str, str], str]` mapping `(path, method)` to the permission value for every operation in `create_app().openapi()["paths"]` that has `x-required-permission` (generate it once with `uv run python -I` from `backend/`, then paste it as a literal). The test asserts the live mapping equals `EXPECTED`, and that every other operation has no `x-required-permission` and no "Requires permission" in its description. Run it: PASS.
- [ ] **Step 2: Write failing tests** in `test_permission_aware_route.py` with dummy guarded use cases and `InMemoryAccessGuard`: `_find_use_case_type` returns a `GuardedCommandHandler` over a `GuardedQueryHandler` in either parameter order; a `Requires(Permission.GRAPH_READ)` use case produces the same `x-required-permission`, description line and `APIKeyCookie` security as the legacy `DocumentedUseCase`; `Public()`, `System()`, `OwnAccount()`, `Shared()` and `Content()` use cases produce no `x-required-permission`, no extra description and no `security`.
- [ ] **Step 3: Run** `poe test-backend -- tests/entrypoints/api/shared/test_permission_aware_route.py -q`. Expected: the guarded cases FAIL.
- [ ] **Step 4: Implement** the interfaces: accept a tuple of base classes in the `issubclass` checks, and add `_declared_permission(use_case_cls)` returning `access.permission` for `Requires`, else the legacy `required_permission` attribute, else `None`.
- [ ] **Step 5: Run** the two test files above, `tests/entrypoints/test_cross_user_isolation.py` and `poe typecheck-backend`. Expected: PASS.
- [ ] **Step 6: Stop.** Ask Sam to commit ("feat(openapi): document Requires stances in PermissionAwareRoute").

### Task 6: Migrate a module (repeat per module, in this order)

Order: system, backup, identity, presets, examples, collections, media, graph. One module per repetition; each ends green and is a stopping point.

**Files per module:** each `modules/<m>/application/*.py` use case; `modules/<m>/adapters/api/dependencies.py` (and `user_dependencies.py` for backup) and any CLI wiring in `modules/<m>/adapters/cli/*.py`, `entrypoints/cli/*.py`, `entrypoints/api/shared/bridges/*.py` that builds these handlers; the module's use case tests; the `EXPECTED_*` pins in `tests/architecture/test_access_stances.py`.

**Interfaces:**
- Consumes: the stance for each class from the spec's inventory table; `GuardedUseCase/CommandHandler/QueryHandler`; `get_access_guard`.
- Produces: each migrated class has `access = <stance>`, implements `_handle` (not `handle`), takes `guard` as its last constructor argument (`uow, guard` / `repos, guard` / own ports then `guard`), and no longer holds `_policy` or `_authorization`. Calls `self._policy.scope_for(actor)` become `self.scope(actor)`; `self._policy.assert_can_*` become `self._guard.assert_can_*`.

For each module:

- [ ] **Step 1: Confirm stances.** For each class, grep its callers (router, CLI, bridges) and confirm the actor kind matches the inventory. Report any mismatch to Sam before changing it (spec: stance records today's behaviour).
- [ ] **Step 2: Update that module's tests first** to build handlers with `InMemoryAccessGuard()` in place of the policy/authorisation stubs, and add one test per module asserting the declared stances as a dict `{UseCaseClass: access}` for its non-`Requires` classes. Run `poe test-backend -- tests/modules/<m> -q`. Expected: FAIL.
- [ ] **Step 3: Migrate the classes** as described under Interfaces. Replace the old permission property (`required_permission`) with `access = Requires(<Permission>.<MEMBER>)` for `Authorised*` classes; keep the same permission value.
- [ ] **Step 4: Update wiring** in the dependency functions and CLI so each handler receives `Depends(get_access_guard)` (API) or the process-wide guard (CLI/bridges); delete now-unused `get_access_policy`/`get_authorisation_port` parameters in that module only.
- [ ] **Step 5: Fill the pins** for the module in `test_access_stances.py`.
- [ ] **Step 6: Run** `poe lint-backend && poe typecheck-backend && poe test-backend`. Expected: pass. Also run the module's router tests; HTTP status codes must be unchanged. `test_openapi_permissions_pinned.py` must pass unedited: if it fails, a migrated route lost or gained a documented permission; fix the migration, never the pin. After the last module, run `poe test-e2e swagger.spec.ts` once.
- [ ] **Step 7: Stop.** Ask Sam to commit ("refactor(<module>): declare access stances").

Module-specific notes:
- **identity:** CLI `identity_app.py` calls `Authorised*` use cases with `SYSTEM_ACTOR` and `SetupFirstAdmin` with `ANONYMOUS_ACTOR`; both keep working. `GetCurrentUser` is called with `ANONYMOUS_ACTOR` from `dependencies.get_current_actor`.
- **backup:** `RestoreOnFirstRun` is `Public` (called with `ANONYMOUS_ACTOR` behind `backup_setup_gate`); it extends `GuardedUseCase` and takes `guard` after its own ports.
- **graph, media, collections, examples:** `Claim*` jobs are `System`; the bridges in `entrypoints/api/shared/bridges/` pass `SYSTEM_ACTOR` today (confirm).
- **media:** if `StageMedia` turns out to read ownership from `actor.id` without any policy call, `Content` is still the stance; its ownership behaviour does not change.

### Task 7: Remove the old bases and rename `Guarded*`

**Files:** `shared_kernel/cqrs.py` (replace contents), delete `shared_kernel/guarded.py`, `shared_kernel/access_policy.py`, `entrypoints/api/shared/access_policy.py` (move `OwnerAccessPolicy` into `access_guard.py` or keep the file if the guard still imports it), update `tests/shared_kernel/test_cqrs.py`, `test_guarded.py`, `test_access_policy_port.py`, `tests/architecture/test_access_stances.py`, `test_content_filter_rules.py`, `test_permission_catalogue.py`.

**Interfaces:**
- Produces: `app.shared_kernel.cqrs.UseCase`, `CommandHandler`, `QueryHandler` with the exact definitions of `Guarded*` from Task 4. Nothing named `Scoped*`, `Authorised*`, `_PolicyHolder`, `_PermissionGate`, `AccessPolicy` remains.

- [ ] **Step 1: Write the failing check:** extend `test_access_stances.py` so every concrete `UseCase` in `application/` has an `access` (replacing the `Guarded*` references) and add `test_no_legacy_bases`: `cqrs` exposes no attribute starting with `Scoped` or `Authorised`.
- [ ] **Step 2: Replace `cqrs.py`** with the `Guarded*` code under the final names; rename `Guarded*` -> final names across `backend/` with `sed`; move the `test_guarded.py` cases into `test_cqrs.py`, deleting the old Scoped/Authorised cases; keep the application-layer rules (`test_all_application_use_cases_inherit_from_cqrs_base`, `test_command_handlers_store_uow_not_repository`).
- [ ] **Step 3: Simplify `PermissionAwareRoute`:** drop the legacy `required_permission` and old-base support from Task 5a (only `UseCase`/`CommandHandler` and `access.permission` remain); update `test_permission_aware_route.py` to the final names and `access = Requires(...)`; update the comment that names `AuthorisationPort.check()`. `test_openapi_permissions_pinned.py` stays unchanged and must pass.
- [ ] **Step 3b: Delete** the `AccessPolicy` Protocol file and `get_access_policy`; the guard owns `OwnerAccessPolicy` directly.
- [ ] **Step 4: Run** `poe lint-backend && poe typecheck-backend && poe test-backend`. Expected: pass.
- [ ] **Step 5: Stop.** Ask Sam to commit ("refactor(access): replace legacy use case bases with the guarded bases").

### Task 8: Docs and the full gate

**Files:** `AGENTS.md` (Business logic / CQRS convention lines), `backend/README.md` (use case bases and permissions sections), `docs/DECISIONS.md` (new entry: why declared access stances, why `Shared` before tokens), `docs/ARCHITECTURE.md` if it names the old bases, the tokens plan's Phase 1 note, `docs/superpowers/plans/2026-10-20-api-tokens-and-permissions.md`.

- [ ] **Step 1: Update docs** to describe the six stances, "declare `access`, write `_handle`", and that `Shared`/`Content` gain a permission with tokens. British English; no graph terminology in user-visible text.
- [ ] **Step 2: Run** `poe coverage`. Expected: all floors met (`shared_kernel` and `application` at 100%).
- [ ] **Step 3: Stop.** Report the result and ask Sam to commit ("docs(access): document access stances").

## Self-review notes

- Spec coverage: stances (Task 3), guard (3), bases (4), pins and enforcement (5), inventory migration (6), final names (7), docs (8). Phase 6 resource-level access is out of scope by design.
- Types: `AccessGuard`, `Access`, `ContentFilter`, `GuardedUseCase` names are used identically in Tasks 3 to 7; `Guarded*` becomes `UseCase`/`CommandHandler`/`QueryHandler` only in Task 7.
- Risks: Task 6 touches ~106 classes (mitigated by module-by-module stopping points); a wrong stance would silently change access (mitigated by Step 1 call-site check and the pinned sets).
