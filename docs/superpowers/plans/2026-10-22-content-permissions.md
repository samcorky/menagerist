# Content permissions (tokens plan, Phase 2) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Give every owned-content and shared-catalogue use case a real permission, held by all members, so API tokens (Phase 4) can later carry a subset. No behaviour change for any user, client or CLI command.

**Architecture:** Permissions become members of per-module `PermissionEnum` subclasses that own their implications (`implied()`), replacing the central `IMPLIES` dicts. `Content` gains a permission; `Shared` is folded into `Requires` and removed. `MEMBER_PERMISSIONS` gains the whole content set, so members hold what they already could use. `PermissionAwareRoute` documents content permissions the same way it documents admin ones.

**Tech Stack:** Python 3.14, FastAPI, pytest, mypy `--strict`, `archunitpython`; frontend generated client (`@hey-api/openapi-ts`).

**Spec:** `docs/superpowers/plans/2026-10-20-api-tokens-and-permissions.md` (Phase 2, with the 2026-10-22 decisions below) and `docs/superpowers/specs/2026-10-21-access-model-refactor-design.md` (stances, guard).

## Decisions taken (Sam, 2026-10-22)

- Permissions are the single primitive (D1). Granularity is coarse (Q3): splitting later is free if the coarse permission implies the finer ones; renaming stored permission strings is a data migration.
- New permission strings use user-facing vocabulary (`item`, `type`); existing admin strings (`graph:node_type:delete` etc.) are unchanged because they are pinned in OpenAPI and tests.
- Export-all and import-all of a user's data, and example-pack install, are separate permissions so a "read only" token never includes them.

## Global Constraints

- Never create, stage, amend or push commits. Leave changes in the working tree and report; Sam commits at each task boundary.
- British English in comments, docs and copy; short Google-style docstrings only where intent is unclear.
- `poe typecheck-backend` (`mypy --strict`) and `poe lint-backend` pass after every task; run only targeted tests while iterating, then `poe coverage` once at the end (needs live Postgres: `poe db-up`).
- Coverage floors: domain, application, shared_kernel 100%; adapters 80%; platform 70%.
- Dependency direction `entrypoints → adapters → application → domain`, enforced by `tests/architecture/test_architecture.py`: `application` may import only `application`, `ports`, `domain` and `shared_kernel`; `shared_kernel` imports nothing from modules and only `typing`, `enum`, `dataclasses` and the other primitives its architecture test allows. So `PermissionEnum` lives in `shared_kernel`, each module's permission enum in its own `application/permissions.py`, and the role-to-permission policy (`MEMBER_PERMISSIONS`, the guard adapter, `PermissionAwareRoute`) in `entrypoints/api/shared`.
- No new port or adapter is introduced. `AccessGuard` stays the port (`shared_kernel/access_guard.py`) with `InMemoryAccessGuard` as its sibling, and `RoleAccessGuard` stays the adapter; use cases keep declaring `access` and implementing `_handle`; routers translate only and gain no logic.
- Tests mirror the source tree (`tests/shared_kernel`, `tests/modules/<module>/application`, `tests/entrypoints/api/shared`); cross-cutting pins live in `tests/architecture`.
- Every `implied()` branch must be executed by a test (application and `shared_kernel` are held at 100% coverage); the catalogue test that calls `implied()` on every permission does this.
- Do not touch the set of OpenAPI security schemes, `cookie_scheme`, `api_v1_router`'s blanket `Security(cookie_scheme)`, or `swagger-init.js`. Swagger's per-operation locks and the hidden Authorize button must behave exactly as today.
- Frontend: `src/lib/api/generated/` is regenerated, never hand-edited. Any `.svelte` or `.svelte.ts` edit goes through the `svelte-file-editor` subagent (none is expected).

## Permission catalogue (the contract this plan creates)

New permissions. All are held by members, admins and the system actor. Values are exact.

| Enum (file) | Member | Value | Implies |
|---|---|---|---|
| `GraphPermission` (existing file) | `ITEM_READ` | `graph:item:read` | |
| | `ITEM_WRITE` | `graph:item:write` | `ITEM_READ` |
| | `TYPE_READ` | `graph:type:read` | |
| | `TYPE_WRITE` | `graph:type:write` | `TYPE_READ` |
| `MediaPermission` (`modules/media/application/permissions.py`, new) | `ITEM_READ` | `media:item:read` | |
| | `ITEM_WRITE` | `media:item:write` | `ITEM_READ` |
| `CollectionPermission` (`modules/collections/application/permissions.py`, new) | `COLLECTION_READ` | `collections:collection:read` | |
| | `COLLECTION_WRITE` | `collections:collection:write` | `COLLECTION_READ` |
| `PresetPermission` (`modules/presets/application/permissions.py`, new) | `PRESET_READ` | `presets:preset:read` | |
| | `PRESET_WRITE` | `presets:preset:write` | `PRESET_READ` |
| `ExamplePermission` (`modules/examples/application/permissions.py`, new) | `PACK_READ` | `examples:pack:read` | |
| | `PACK_INSTALL` | `examples:pack:install` | `PACK_READ` |
| `BackupPermission` (existing file) | `EXPORT_OWN_DATA` | `backup:own_data:export` | |
| | `IMPORT_OWN_DATA` | `backup:own_data:import` | |

Existing admin permissions are unchanged and stay admin-only.

Use case to permission mapping (every name is `<module>.<ClassName>`; this is the pin in Task 6):

- `graph:item:read`: GetNode, ListNodes, SearchNodes, GetEdge, ListEdges, ListAttributeValues, ListItemFields, CountNodeTypeAttributeUsage, CountEdgeTypeAttributeUsage
- `graph:item:write`: CreateNode, UpdateNode, DeleteNode, CreateEdge, CreateEdges, UpdateEdge, DeleteEdge
- `graph:type:read`: GetNodeType, ListNodeTypes, GetEdgeType, ListEdgeTypes, ValidateQuery
- `graph:type:write`: CreateNodeType, UpdateNodeType, CreateEdgeType, UpdateEdgeType, PromoteExtraSchemaField (it changes the shared type, hence not `item:write`)
- `media:item:read`: GetMedia, ListNodeMedia
- `media:item:write`: AttachMedia, ClearMediaCover, DeleteMedia, DetachMedia, OrphanMedia, PromoteMedia, SetMediaCover, StageMedia, UpdateMedia, UploadAndAttachMedia
- `collections:collection:read`: CountCollectionItems, GetCollection, ListCollections, ResolveCollection
- `collections:collection:write`: AddItemsToCollection, CreateCollection, DeleteCollection, RemoveItemFromCollection, UpdateCollection
- `presets:preset:read`: ExportPresets, GetPreset, ListPresets
- `presets:preset:write`: CreatePreset, DeletePreset, ImportPresets, UpdatePreset
- `examples:pack:read`: ListExampleEntities, ListExamplePacks
- `examples:pack:install`: InstallExamplePack, UninstallExamplePack
- `backup:own_data:export`: ExportUserData, OpenUserExport
- `backup:own_data:import`: ImportUserArchive, ImportUserData

Stance per class: the graph/media/collections/examples/backup classes above that were `Content()` become `Content(<permission>)` (they keep `scope()`); the graph type classes, ValidateQuery and all presets classes that were `Shared()` become `Requires(<permission>)`. `PromoteExtraSchemaField` stays `Content` with `graph:type:write`.

## Review Focus

- A member uses every owned-content and catalogue route exactly as before. Pinned by the Task 6 test that every `Content`/`Requires` permission outside the admin set is in `MEMBER_PERMISSIONS`, and by the existing member router tests staying green.
- `ADMIN_ONLY_ACTIONS` is unchanged (the 16 admin strings). Pinned in Task 2.
- The anonymous actor is refused for `Content(permission)` before any permission lookup. Pinned in Task 2.
- Swagger still shows the cookie lock and no Authorize button, and the schema still has one security scheme. Pinned in Task 7.
- The generated frontend `Permission` type matches the backend catalogue after regeneration. Checked in Task 8.

---

### Task 1: `PermissionEnum` base with `implied()`

**Files:**
- Create: `backend/src/app/shared_kernel/permission.py`
- Modify: `backend/src/app/shared_kernel/access.py`, `backend/src/app/entrypoints/api/shared/permissions.py`, `backend/src/app/entrypoints/api/shared/authorisation.py`, `backend/src/app/modules/{backup,graph,identity,system}/application/permissions.py`
- Test: `backend/tests/shared_kernel/test_permission.py` (create), `backend/tests/entrypoints/api/shared/test_permissions.py`, `backend/tests/entrypoints/api/shared/test_authorisation.py`, `backend/tests/architecture/test_permission_catalogue.py`

**Interfaces:**
- Produces: `class PermissionEnum(StrEnum)` with no members and `def implied(self) -> frozenset[Self]` returning `frozenset()` by default; subclasses override it. `Requires.permission: PermissionEnum`. `expand(granted: Iterable[Permission]) -> frozenset[Permission]` (the `implies` parameter is removed). `RoleAuthorisationAdapter.__init__(self, member_permissions: frozenset[Permission] = MEMBER_PERMISSIONS)` (the `implies` parameter is removed). `Permission` stays the union alias of the module enums, because pydantic and OpenAPI need concrete enums for the `/auth/me/permissions` schema.
- Consumes: nothing from earlier tasks.

- [ ] **Step 1: Write the failing tests.** In `tests/shared_kernel/test_permission.py`: `test_implied_defaults_to_nothing` (a throwaway `PermissionEnum` subclass member has `implied() == frozenset()`), `test_subclass_overrides_implied` (a subclass whose member returns another member from `implied()`). In `test_permissions.py` update the existing `expand` tests to call `expand(granted)` with the live catalogue: `expand({BackupPermission.CREATE}) == {CREATE, READ}`, transitivity via a throwaway chain A implies B implies C. In `test_permission_catalogue.py` add `test_every_catalogued_permission_declares_its_implications`: every member of `ALL_PERMISSIONS` is an instance of `PermissionEnum` and every value of `implied()` is in `ALL_PERMISSIONS`.
- [ ] **Step 2: Run** `poe test-backend -- tests/shared_kernel/test_permission.py tests/entrypoints/api/shared tests/architecture/test_permission_catalogue.py`. Expected: FAIL (module missing).
- [ ] **Step 3: Implement** `PermissionEnum` in `shared_kernel/permission.py`; change `Requires.permission` to `PermissionEnum`; make the four module enums subclass it and move each `IMPLIES` mapping into an `implied()` override (a `match self` or an `if`; a module-level dict cannot reference members inside the class body). Delete the `IMPLIES` constants and the aggregation in `entrypoints/api/shared/permissions.py`; `expand` now closes over `member.implied()`. Remove the `implies` parameter from `RoleAuthorisationAdapter`.
- [ ] **Step 4: Fix remaining callers** found by `grep -rn "IMPLIES\|implies=" backend`, and re-run Step 2 plus `poe typecheck-backend`. Expected: PASS, no mypy errors. Behaviour is identical: the existing implication tests (`BackupPermission`, `IdentityPermission.REVOKE_SESSION`) pass unchanged in meaning.
- [ ] **Step 5: Stop** and report for Sam to commit.

### Task 2: Catalogue, member grant and transitional `Content(permission)`

**Files:**
- Create: `backend/src/app/modules/{media,collections,presets,examples}/application/permissions.py`
- Modify: `backend/src/app/modules/graph/application/permissions.py`, `backend/src/app/modules/backup/application/permissions.py`, `backend/src/app/entrypoints/api/shared/permissions.py`, `backend/src/app/entrypoints/api/shared/authorisation.py`, `backend/src/app/entrypoints/api/shared/access_guard.py`, `backend/src/app/shared_kernel/access.py`
- Test: `backend/tests/entrypoints/api/shared/test_authorisation.py`, `backend/tests/entrypoints/api/shared/test_role_access_guard.py` (extend; the in-memory guard in `tests/shared_kernel/test_access_guard.py` needs no change), `backend/tests/architecture/test_permission_catalogue.py`, `backend/tests/entrypoints/api/test_permissions_router.py`

**Interfaces:**
- Consumes: `PermissionEnum` (Task 1).
- Produces: the enums in the catalogue table above, each with the stated `implied()`; `Permission` union and `ALL_PERMISSIONS` include them; `CONTENT_PERMISSIONS: frozenset[Permission]` in `authorisation.py` (every new permission in the table); `MEMBER_PERMISSIONS = CONTENT_PERMISSIONS`; `Content.permission: PermissionEnum | None = None` (transitional, made required in Task 6). `RoleAccessGuard.check` treats `Content(permission=p)` with `p` set exactly like `Requires(p)` after the anonymous refusal, and `Content()` as today.

- [ ] **Step 1: Write the failing tests.** In `test_authorisation.py`: replace `test_the_default_member_grant_is_empty` with `test_the_default_member_grant_is_the_content_set` (`MEMBER_PERMISSIONS == CONTENT_PERMISSIONS`, the 14 new strings exactly as in the table, none of them admin) and keep `test_the_admin_only_set_matches_the_catalogue` with the same 16 strings; replace `test_members_are_forbidden_catalogue_permissions` with one asserting a member is forbidden exactly `ADMIN_ONLY_ACTIONS` and allowed the rest. In the guard tests: an anonymous actor with `Content(MediaPermission.ITEM_READ)` raises `ForbiddenError`; a member passes; an authorisation with an empty member grant makes a member fail with `ForbiddenError`. In `test_permission_catalogue.py` change `test_backup_permissions_are_catalogued_and_admin_only` to assert only the four archive permissions are admin-only and the two `own_data` ones are member permissions. In `test_permissions_router.py` assert a member's `/auth/me/permissions` lists the content set (expanded) and an admin's lists everything.
- [ ] **Step 2: Run** the four test files. Expected: FAIL.
- [ ] **Step 3: Implement** the new enums and `implied()` overrides per the table, register all in `permissions.py` (`Permission` union, `ALL_PERMISSIONS`), add `CONTENT_PERMISSIONS`/`MEMBER_PERMISSIONS` in `authorisation.py`, add the optional field to `Content`, and extend the guard's `case Requires(...)` arm to `case Requires(permission=p) | Content(permission=p) if p is not None` ahead of the bare `Content()` arm.
- [ ] **Step 4: Run** Step 2 plus `poe typecheck-backend` and `poe lint-backend`. Expected: PASS. No use case has changed stance yet.
- [ ] **Step 5: Stop** for Sam to commit.

### Task 3: Graph stances

**Files:**
- Modify: every graph use case in the mapping above under `backend/src/app/modules/graph/application/`
- Test: `backend/tests/modules/graph/application/test_graph_access_stances.py` (extend the existing per-module stance test; every module has `test_<module>_access_stances.py` beside its application tests)

**Interfaces:** Consumes `GraphPermission` members and `Content(permission)` (Task 2). Produces no new names.

- [ ] **Step 1: Write the failing test** asserting, per class, `access == Content(GraphPermission.X)` or `Requires(GraphPermission.X)` exactly as in the mapping (a dict of class to expected stance, so the whole module is one table).
- [ ] **Step 2: Run** it. Expected: FAIL.
- [ ] **Step 3: Change each `access` declaration** (`Content()` to `Content(...)`, `Shared()` to `Requires(...)` for the five type/query classes) and fix imports.
- [ ] **Step 4: Run** `poe test-backend -- tests/modules/graph tests/architecture` and `poe typecheck-backend`. Expected: PASS. `EXPECTED_SHARED` pin still lists the graph classes; Task 6 replaces it, so update that set here by removing the five graph entries to keep the architecture test green.
- [ ] **Step 5: Stop** for Sam to commit.

### Task 4: Media and collections stances

Same shape as Task 3 for `modules/media` and `modules/collections` (stance test per module; `Content(MediaPermission.*)`, `Content(CollectionPermission.*)`; no `Shared` classes in these modules).

**Files:** the use cases in `backend/src/app/modules/{media,collections}/application/`; tests `tests/modules/{media,collections}/application/test_{media,collections}_access_stances.py` (extend the existing files).

- [ ] **Step 1:** Write the two table-driven stance tests from the mapping. **Step 2:** run, expect FAIL. **Step 3:** change the declarations. **Step 4:** run `poe test-backend -- tests/modules/media tests/modules/collections tests/architecture` plus typecheck; expect PASS.
- [ ] **Step 5: Composite use cases.** `grep` for use cases that construct or call other use cases with the same guard (for example `UploadAndAttachMedia`). Add one test per composite asserting which permissions the inner calls need, so Phase 4 can decide how an outer permission covers them. Members hold all of them today, so this is a pin, not a behaviour change. Record each composite and its inner permissions in the report file.
- [ ] **Step 6: Stop** for Sam to commit.

### Task 5: Presets, examples and user-backup stances

Same shape for `modules/presets` (all seven are `Shared` today, become `Requires`), `modules/examples` (`Content`), and the four user-data use cases in `modules/backup` (`Content`; the admin `Requires` ones are untouched).

**Files:** use cases under `backend/src/app/modules/{presets,examples,backup}/application/`; tests `tests/modules/{presets,examples,backup}/application/test_{presets,examples,backup}_access_stances.py` (extend the existing files).

- [ ] **Step 1:** Write the table-driven stance tests. **Step 2:** run, expect FAIL. **Step 3:** change declarations and remove the presets entries from `EXPECTED_SHARED`. **Step 4:** run `poe test-backend -- tests/modules/presets tests/modules/examples tests/modules/backup tests/architecture`, typecheck and lint; expect PASS. **Step 5:** Stop for Sam to commit.

### Task 6: Tighten the stance model and pin the contract

**Files:**
- Modify: `backend/src/app/shared_kernel/access.py`, `backend/src/app/entrypoints/api/shared/access_guard.py`, `backend/src/app/shared_kernel/access_guard.py`, `backend/src/app/shared_kernel/cqrs.py` (only if it names `Shared`), `backend/tests/architecture/test_access_stances.py`
- Create: `backend/tests/architecture/test_permission_mapping.py`
- Test: the same, plus `tests/shared_kernel/test_access.py`

**Interfaces:** `Content.permission: PermissionEnum` (required). `Shared` is deleted from `access.py`, the `Access` union, the guard arms and `InMemoryAccessGuard`/`DenyAllAccessGuard` if they mention it.

- [ ] **Step 1: Write the failing tests.** `test_permission_mapping.py` holds `EXPECTED_PERMISSIONS: dict[str, str]` mapping every `<module>.<ClassName>` in the mapping above (and the existing admin ones) to its permission value, and asserts the live `access.permission` of every `Content` and `Requires` use case equals it, with no extras or omissions. Also `test_every_non_admin_permission_is_a_member_permission`: for every `Content`/`Requires` use case whose permission is not in `ADMIN_ONLY_ACTIONS`, the permission is in `MEMBER_PERMISSIONS` (this is the "members lose nothing" safety net). Add `test_catalogue_is_pinned`: `{p.value for p in ALL_PERMISSIONS}` equals a literal set of all strings (30 values: 16 admin, 14 member), with a comment that permissions are never renamed, only deprecated through `implied()`. In `test_access_stances.py` remove `EXPECTED_SHARED` and its assertions, and in `tests/shared_kernel/test_access.py` assert `Content()` without a permission raises `TypeError`.
- [ ] **Step 2: Run** `poe test-backend -- tests/architecture tests/shared_kernel`. Expected: FAIL.
- [ ] **Step 3: Implement:** make the field required, delete `Shared`, drop its guard arm and docs, and update every remaining reference (`grep -rn "Shared" backend/src backend/tests`).
- [ ] **Step 4: Ownership guard-rail.** Create `backend/tests/architecture/test_no_direct_ownership_checks.py`: parse every module under `app.modules.*.application` (the identity module is excluded, since its comparisons are about sessions and accounts, not content) with `ast` and fail on any comparison (`==` or `!=`) between an `owner_id` attribute or name and `actor.id` or `actor_id`. The ownership rule must stay inside `AccessGuard`, so sharing later changes one place. Today `examples/application/install_example_pack.py` compares `i.owner_id` with `actor_id` and `actor.id` in two places; list that file in an explicit `ALLOWED` set with a comment saying it is to be routed through the guard when sharing lands, and assert the allow-list entries still exist (a stale entry fails). Write the test first and confirm it fails without the allow-list.
- [ ] **Step 5: Run** `poe test-backend` (whole unit suite), typecheck and lint. Expected: PASS.
- [ ] **Step 6: Stop** for Sam to commit.

### Task 7: `PermissionAwareRoute`, OpenAPI tests and API description

**Files:**
- Modify: `backend/src/app/entrypoints/api/shared/permission_aware_route.py`, `backend/src/app/entrypoints/api/docs/templates/api-description.md`
- Test: `backend/tests/entrypoints/api/shared/test_openapi_permissions_pinned.py`, `backend/tests/entrypoints/api/shared/test_permission_aware_route.py`, `backend/tests/entrypoints/api/docs/test_docs.py`

**Interfaces:** `_declared_permission(use_case_cls) -> str | None` returns the permission of a `Requires` or `Content` stance and `None` otherwise. Everything else in the module is unchanged: `cookie_scheme`, the `Security(cookie_scheme)` dependency, and `x-required-permission` and the `**Requires permission:**` description line (now on content routes too). `api-description.md` keeps its `$session_cookie_name` placeholder as the only `$` placeholder.

- [ ] **Step 1: Write the failing tests.**
  - `test_openapi_permissions_pinned.py`: keep `EXPECTED` literally as the admin pin, and filter the live map to operations whose permission is in `ADMIN_ONLY_ACTIONS` before comparing. Add `test_every_documented_permission_is_a_catalogue_permission`. Add `test_documented_permission_matches_the_use_case` walking `create_app().routes` the way `test_permission_aware_route.py` does, asserting each route's `x-required-permission` equals its use case's declared permission and that routes whose use case is `Public`, `OwnAccount`, `System` or absent carry no permission line. Replace `test_other_operations_document_no_permission` with that last assertion.
  - `test_permission_aware_route.py`: a `Content(MediaPermission.ITEM_READ)` stub route gets the extension and the description line.
  - `test_docs.py`: `test_swagger_security_is_unchanged` asserts `components.securitySchemes` contains exactly the cookie scheme (`type apiKey`, `in cookie`) and that representative content, admin and public operations (for example `GET /api/v1/node`, `GET /api/v1/user`, `POST /api/v1/auth/login`) keep the same `security` entries as before this task (the cookie scheme for the first two, none for the public one). Keep the existing placeholder test green.
- [ ] **Step 2: Run** `poe test-backend -- tests/entrypoints/api`. Expected: FAIL on the new assertions.
- [ ] **Step 3: Implement** the `_declared_permission` change and update the "Permissions" section of `api-description.md`: every operation that needs a permission names it; members hold the content permissions, administrators hold all; `GET /api/v1/auth/me/permissions` lists yours. Do not mention tokens yet.
- [ ] **Step 4: Run** Step 2, then the Swagger browser spec `frontend/tests/e2e/swagger.spec.ts` with the repo's e2e command (see `CONTRIBUTING.md`). Expected: PASS, including the assertion that the Authorize button is hidden.
- [ ] **Step 5: Stop** for Sam to commit.

### Task 8: Regenerate the frontend client

**Files:**
- Modify: `frontend/src/lib/api/generated/` (by regeneration only)

- [ ] **Step 1:** Run `poe generate-frontend-client`. **Step 2:** `git diff --stat frontend/src/lib/api/generated` should show only the `Permission` enum growing (and descriptions gaining the permission line). **Step 3:** Run `poe typecheck-frontend`, `poe lint-frontend`, `poe test-frontend`. Expected: PASS; `auth.can()` callers are unaffected because the type only gained members. **Step 4:** Stop for Sam to commit.

### Task 9: Documentation and the tokens plan

**Files:**
- Modify: `docs/superpowers/plans/2026-10-20-api-tokens-and-permissions.md`, `docs/DECISIONS.md`, `docs/ARCHITECTURE.md`, `backend/README.md` (only the access sections that name `Shared`, `IMPLIES` or the empty member grant), `AGENTS.md` (only the "Access stances" paragraph)

- [ ] **Step 1: Update the tokens plan.**
  - Mark Phase 2 done with this plan's link, fix the stale plan file names (`2026-10-20-access-model-refactor.md`, `2026-10-20-csrf-origin-protection.md`; the settings handoff plan does not exist, so drop that reference), and move Phases 5 and 6 out to "separate plans needed".
  - Rewrite Phase 4 with the review decisions: grantability is opt-in (`token_grantable` defaults to false; v1 grants only content permissions, no Admin preset); grants are validated against the owner's current permissions at creation; creating a token requires the password again; expiry is mandatory with a maximum; an invalid or expired bearer is a 401 and never falls back to the cookie; the secret is stored as SHA-256 and compared in constant time; never log the `Authorization` header; token id is logged on create, use and revoke; user lock or deactivation stops tokens at once; an architecture test keeps `actor.is_admin` out of everything except the authorisation adapter; `Authorization` is added to CORS only if a cross-origin browser client exists; the token UI shows human labels (Items, Item types, Collections, Media, Presets), never `graph:*` strings, per `DESIGN_GUIDELINES.md`.
  - Add a "Swagger and `PermissionAwareRoute`" section to Phase 4: define a bearer `HTTPBearer(auto_error=False)` scheme beside `cookie_scheme`; replace the router-wide `Security(cookie_scheme)` with a per-route choice made in `PermissionAwareRoute` (`Requires`/`Content`: cookie or bearer; `OwnAccount`: cookie only; `Public`: none), checked by a generated-schema test that FastAPI emits them as alternatives; there are no OAuth scopes on an HTTP bearer scheme, so grants are documented through `x-required-permission` only; show the Authorize button for the bearer scheme only (today `.auth-wrapper` is hidden in `swagger.html` and `swagger.spec.ts` asserts that) and keep `persistAuthorization: false`; `cookieSchemes()` in `swagger-init.js` already ignores `http` schemes, so the session lock logic is untouched; make sure `prepareRequest` never strips `Authorization`; document "Using a token" in `api-description.md` (mind the single `$` placeholder test); `GET /auth/me/permissions` returns the intersection for a token actor; add a Playwright test that authorises a token in Swagger and calls a content route.
  - Add composite use cases to the risks: record the inner permissions found in Task 4.
  - The "Later: sharing and resource-level access" section was rewritten on 2026-10-22 and needs no further change here beyond keeping it linked from Phase 4.
- [ ] **Step 2: Update `DECISIONS.md`** with one entry: permissions are enums owning `implied()`; strings are a public contract (never renamed, split through implication); coarse-first granularity; member grant equals the content set. **Step 3:** Fix the access paragraphs in `ARCHITECTURE.md`, `backend/README.md` and `AGENTS.md` (the `Shared` stance is gone; `Content` and `Requires` carry a permission; `Content` is the only stance that may call `scope()`; the pins are now the mapping and catalogue tests). **Step 4:** Run `poe coverage` (with `poe db-up`) once; expected: all floors met. **Step 5:** Stop for Sam to commit.
