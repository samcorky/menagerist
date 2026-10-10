# Multi-user Stage 1: Accounts and Private Ownership Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Local accounts (setup, sign-in, admin-created users), content owned by its creator and invisible to everyone else, enforced in every repository, with existing data adopted by the first admin.

**Architecture:** A new `identity` module owns users and sessions (scrypt password hashes, server-side sessions in an HTTP-only cookie, double-submit CSRF). `get_current_actor` reads the session and returns a real `Actor`. A required `AccessScope` argument (all, or one user) is threaded through every content repository method and filters by `owner_id` in SQL and in the in-memory twins. Shared structure (item types, relationship types, presets) stays unowned. Destructive structure operations that touch everyone's content are admin-only and run with the all-scope. The frontend gains sign-in, first-run setup, a user menu and an admin Users page; e2e authenticates through a per-worker setup.

**Tech Stack:** Python 3.14, FastAPI, SQLAlchemy/Alembic, stdlib `hashlib.scrypt`, pytest, testcontainers; SvelteKit 5 runes, Vitest, Playwright.

**Spec:** `docs/superpowers/specs/2026-10-09-multi-user-ownership-design.md` (amended by "Decisions made while planning" below).

## Decisions made while planning (deviations and fills; owner can overrule before building)

1. **Password hashing is stdlib `hashlib.scrypt`**, not argon2: no new dependency or image weight (project rule), still an OWASP-recommended KDF. Parameters (N=2^15, r=8, p=1, 16-byte salt, 32-byte key) are stored in the hash string so they can be raised later. Swapping to argon2 later is one adapter.
2. **Accounts are created by the admin with an initial password** (shown once, the user must change it at first sign-in), not by invitation links. No email infrastructure exists, and links add expiry and token handling for no Stage 1 benefit. Invitation links remain a later option.
3. **Authorisation lives in an `AccessPolicy` (owner decision, 2026-10-10), not in the repositories.** `AccessPolicy` is a port in `shared_kernel` with one Stage 1 implementation, `OwnerAccessPolicy`, and it is the only place that knows who may see or change what: `scope_for(actor) -> AccessScope`, `assert_can_view(actor, owner_id)` (raises 404-mapped `NotFoundError`, so existence never leaks), `assert_can_modify(actor, owner_id)`, `assert_can_delete(actor, owner_id)`, `require_admin(actor)`. Repositories contain no rules: they only support an `AccessScope` *query criterion* (`AccessScope.of(user_id)` = owned by that user, `AccessScope.everyone()` = no restriction), required on every method that returns or counts content so that lists, searches and counts are filtered in SQL (post-filtering would break keyset pagination, `Total-Count` and ETag counts). Use cases never build a scope themselves: they ask the policy. A missing scope is a type error and an architecture test enforces it. Stage 2 replaces `OwnerAccessPolicy` with a `SharingAccessPolicy` (it reads share records) and widens what a scope means in SQL; use cases do not change.
4. **Edges get their own `owner_id`** (the creator). Creating an edge requires both endpoints to be visible to the actor, so in Stage 1 an edge's owner equals both endpoints' owner; visibility is `edges.owner_id = viewer`.
5. **Media assets get `owner_id`** (the uploader); attachments follow their asset; attaching needs the asset owned by the actor and the target node visible (a media-owned port, implemented by a bridge).
6. **Destructive operations on shared structure that rewrite everyone's content are admin-only**: deleting an item type or relationship type (it clears the type on all items/edges) and purging an attribute. Usage counts and attribute-value suggestions are scoped to the viewer. Creating and editing structure stays open to every member, as the spec says.
7. **Example packs install per user**: `example_installations.owner_id`, active-pack uniqueness becomes `(pack_id, owner_id)`, pack targets run as the installing actor (not the system actor). Shared types a pack needs that already exist because **the same pack was installed by another user** are reused (never recorded as owned, never removed by this user); removal of a shared type keeps it while any user's content still uses it, using the all-scope in-use check. A clash with a type from anywhere else is still a 409.
8. **Collection slugs are unique per owner** (`(owner_id, slug)` among live collections); `get_by_slug` is scoped.
9. **Owner columns stay nullable in the database in Stage 1** (nodes, edges, media_assets, example_installations). Rows with no owner are visible to nobody; the domain requires an owner on construction; the first-admin claim fills existing rows. Making them NOT NULL is a follow-up migration once every deployment has claimed its data.
10. **Before setup (no users) every `/api/v1` route except the auth routes answers 401 with problem type `setup_required`**; the frontend redirects to `/setup`. After setup, no session gives 401 `unauthenticated`.
11. **Unauthenticated routes stay**: `/api/health*`, `/api/version`, the docs routes, the SPA shell. Everything else under `/api/v1` requires a session except `/api/v1/auth/status`, `/auth/setup`, `/auth/login`.
12. **Existing owners to claim**: collections owned by `UUID(int=1)` (API-created) and `UUID(int=0)` (created by example installs through the system actor), plus all rows with a NULL owner.
13. **Swappable credentials.** Sign-in goes through an `Authenticator` port (Stage 1 adapter: local username and password) that returns a verified identity, so OIDC and trusted-proxy-header sign-in (for people running Authentik or Authelia in front) are later adapters that reuse sessions, roles and the access policy unchanged. Password hashing is a scheme registry: every stored hash carries its scheme prefix (`scrypt$...`), new hashes use the scheme named by `MENAGERIST_PASSWORD_HASHER` (default `scrypt`), any known scheme still verifies, and a hash in an older scheme is rewritten on the next successful sign-in. There is no `Clock` port: tests freeze time with a time-freezing library (see Task 1).
14. **Sign-in throttling**: after 5 failed attempts for a username within 15 minutes, further attempts for it answer 429 for the rest of the window (stored in the users table, no extra service).

## Global Constraints

- British English. UI words: "collection", "item", "account"; never node, edge, graph or shelf. Touch targets at least 44 px.
- Backend: `mypy --strict` incl. tests, ruff, coverage floors (domain/application/shared_kernel 100%, adapters 80%, platform 70%). Module independence: `identity` imports no other module; bridges between modules live in `backend/src/app/entrypoints/api/shared/`. In-memory repositories are first-class siblings of every SQL repository and mirror every port change.
- In-memory UoW does not roll back: spy on writes, assert `uow.committed`.
- Every `.svelte` / `.svelte.ts` edit goes through the `svelte:svelte-file-editor` subagent.
- Never `git add`/`commit`/`push`; the owner commits (one `git add -A`, because the pre-commit hooks lint the whole repo). Run `poe migrate` after pulling.
- Secrets: no credential, session token or password hash is ever logged or returned by the API; session tokens are stored hashed (sha256); cookie `HttpOnly`, `SameSite=Lax`, `Secure` when the request is HTTPS (the app already wraps proxy headers).

## Review Focus

- **Cross-user leakage on every route**: user B gets 404 or an empty list/zero count for user A's content, including `q` search, `GET /node?collection=`, `Total-Count` headers, ETag/`If-None-Match` responses, attribute-value suggestions, media content and thumbnails, collection item counts, and example entities.
- **A 404, never a 403, for something that exists but is not yours** (existence must not leak), including collection slug conflicts.
- **Existing data adoption**: after setup, every pre-existing item, connection, file, collection and example installation belongs to the first admin and nothing is orphaned; running setup twice is refused.
- **Session safety**: logout and password change invalidate sessions; expired and tampered tokens fail; unsafe methods without a valid CSRF header fail; the login endpoint reveals nothing about whether a username exists.
- **Admin-only structure operations** cannot be performed by members, and members' routine structure edits still work.
- **The client cache**: the frontend's ETag/body cache must be cleared on sign-in and sign-out so one person never sees the previous user's cached bodies.

---

### Task 1: Identity module — users, sessions, password hashing, persistence

**Files:**
- Create: `backend/src/app/modules/identity/` with `domain/{user.py,session.py,errors.py}`, `ports/{user_repository.py,session_repository.py,password_hasher.py,unit_of_work.py}`, `application/` (empty for now), `adapters/persistence/{models.py,user_repository.py,in_memory_user_repository.py,session_repository.py,in_memory_session_repository.py,unit_of_work.py}`, `adapters/security/{scrypt_password_hasher.py,in_memory_password_hasher.py}`
- Modify: `backend/src/app/alembic/env.py` (import identity models), `backend/src/app/platform/config/` (new `IdentitySettings`: `session_ttl_hours=168`, `cookie_name="menagerist_session"`, `csrf_cookie_name="menagerist_csrf"`, `cookie_secure: bool | None` meaning auto), `backend/tests/architecture/test_architecture.py` (identity independent of graph, presets, examples, collections, media)
- Create: Alembic migration `j1e2f3a4b5c6_add_users_and_sessions.py`
- Test: `backend/tests/modules/identity/...`, migrations test (pytest-alembic) stays green

**Interfaces:**
- Produces:
  - `User` (kw_only dataclass, uuid7 id): `username` (case-insensitive unique, 3-64 chars, `[A-Za-z0-9._-]`), `display_name`, `password_hash: str`, `role: Role` (`Role.ADMIN`, `Role.MEMBER`), `must_change_password: bool`, `disabled: bool`, `failed_attempts: int`, `locked_until: datetime | None`, timestamps; domain methods `change_password`, `disable`, `enable`, `record_failure(now)`, `record_success()`.
  - `Session`: `id` uuid7, `user_id`, `token_hash: str` (sha256 hex), `created_at`, `expires_at`, `last_seen_at`; `is_expired(now)`.
  - `Authenticator` port: `authenticate(credentials) -> VerifiedIdentity | None` where `VerifiedIdentity` is `(subject, display_name)`; the local adapter `PasswordAuthenticator` looks the user up, verifies the password through the hasher registry, and applies the lockout rules; `SignIn` (Task 2) calls the port, then creates the session for the matching local user.
  - `PasswordHasher` port: `hash(password: str) -> str`, `verify(password: str, hashed: str) -> bool`, `needs_rehash(hashed) -> bool`. Scrypt format `scrypt$N$r$p$salt_b64$key_b64`. Constant-time compare (`hmac.compare_digest`). `SessionTokenGenerator` port: `new_token() -> str` (adapter wraps `secrets.token_urlsafe(32)`; a deterministic in-memory twin for tests) and `token_hash(token) -> str` (sha256), so the application layer needs no `secrets` import and tests stay deterministic. Password rules in the domain: 10-128 characters, not equal to the username.
  - `UserRepository`: `add`, `save`, `get`, `get_by_username`, `list_all`, `count`, `count_admins`. `SessionRepository`: `add`, `get_by_token_hash`, `delete`, `delete_for_user`, `delete_expired(now)`.
  - Tables `users`, `sessions` (index on `token_hash` unique, `user_id`).

- [ ] **Step 1:** failing tests: user and session domain rules (username rules, password rules, lockout after 5 failures within 15 minutes, success resets), scrypt round-trip, wrong password, tampered hash, parameters embedded and `needs_rehash`, repositories (in-memory and SQL) incl. case-insensitive uniqueness and token lookup, expiry cleanup; migration up/down; architecture rule.
- [ ] **Step 1b:** time handling: code takes `now` as a parameter where the domain already does (lockout, expiry) and uses `datetime.now(UTC)` only in use cases; tests freeze or move time with the time-freezing library. This repository's dependency lists do not currently contain `time-machine` or `freezegun`; if neither is available in CI, add one as a dev dependency (small, dev-only) in this task and say which.
- [ ] **Step 2:** implement; hasher registry: `PasswordHasherRegistry(schemes, default)` implementing `PasswordHasher` (hash with the default, verify by prefix, `needs_rehash` true for any non-default scheme or outdated parameters), unit-tested with a fake second scheme; `scrypt` memory limit must be set explicitly (`maxmem`) so N=2^15 works.
- [ ] **Step 3:** `uv run poe format`, `lint-backend`, `typecheck-backend`, targeted pytest, `uv run poe coverage`.

### Task 2: Identity application and auth API, CSRF, first-run setup

**Files:**
- Create: `identity/application/{setup_first_admin.py,sign_in.py,sign_out.py,get_current_user.py,change_password.py,create_user.py,list_users.py,update_user.py,reset_password.py}`, `identity/adapters/api/{auth_router.py,user_router.py,schemas.py,dependencies.py}`, `backend/src/app/entrypoints/api/shared/csrf.py`
- Modify: `backend/src/app/entrypoints/api/__init__.py` (register routers, CSRF middleware, tighten CORS: no credentials), settings
- Test: use-case tests, router tests

**Interfaces:**
- Produces use cases (all take `actor` first-class where relevant):
  - `SetupFirstAdmin(username, display_name, password)`: only when `UserRepository.count() == 0`, else 409 `SetupAlreadyDoneError`; creates an ADMIN, signs in, **and calls the `ExistingDataClaim` port** (Task 8) in the same transaction.
  - `SignIn(username, password) -> (Session token, User)`: throttled (429 `TooManyAttemptsError` with `Retry-After`), generic 401 `InvalidCredentialsError` for unknown user, wrong password and disabled account alike (same message, comparable timing: always hash-verify against a dummy hash for unknown users), rehash on success if parameters changed, creates a session with a random 32-byte token (`secrets.token_urlsafe`), stores only its sha256.
  - `SignOut`, `GetCurrentUser(token) -> User | None` (expired/unknown -> None; updates `last_seen_at` at most once per minute), `ChangePassword(current, new)` (invalidates all other sessions, clears `must_change_password`), admin-only `CreateUser`, `ListUsers`, `UpdateUser` (display name, role, disable/enable; never disable or demote the last active admin: 409), `ResetPassword` (sets a new initial password, `must_change_password=True`, deletes the user's sessions).
- Routes: `GET /api/v1/auth/status` -> `{setup_required: bool}`; `POST /auth/setup`; `POST /auth/login` (sets session cookie and the readable CSRF cookie `menagerist_csrf`); `POST /auth/logout`; `GET /auth/me`; `POST /auth/password`; admin: `GET/POST /user`, `PATCH /user/{id}`, `POST /user/{id}/password`. Cookies: `HttpOnly; SameSite=Lax; Path=/`, `Secure` automatically when the request scheme is https (setting overrides), max-age from `session_ttl_hours`.
- CSRF: `entrypoints/api/shared/csrf.py` middleware/dependency: every unsafe method (POST, PUT, PATCH, DELETE) under `/api/v1` except `/auth/login` and `/auth/setup` requires header `X-CSRF-Token` equal to the `menagerist_csrf` cookie (constant-time compare); failure 403 problem `csrf_failed`. Safe methods unaffected.

- [ ] **Step 1:** failing tests for every use case and rule above; router tests incl. cookie attributes, CSRF failure and success, throttle 429, generic credential errors, last-admin protection, setup-twice 409, setup creating a signed-in session, password change invalidating other sessions.
- [ ] **Step 2:** implement; use-case tests use in-memory repositories and the in-memory hasher; one Postgres integration test of setup + login + `/me`.
- [ ] **Step 3:** regenerate the frontend client (`uv run poe generate-frontend-client`); `lint-backend`, `typecheck-backend`, `typecheck-frontend`, `uv run poe coverage`.

### Task 3: Real actor, `AccessScope`, 401s, router-test fixture

**Files:**
- Create: `backend/src/app/shared_kernel/access_scope.py`, `backend/tests/conftest.py` fixtures (or a router-test helper module) providing `as_user(app, user_id, role)`.
- Modify: `backend/src/app/entrypoints/api/shared/dependencies.py` (`get_current_actor` becomes async, takes `Request`, reads the session cookie through the identity use case, returns `Actor(id, roles={"admin"|"member"})`; raises 401 problems `unauthenticated` / `setup_required`), `authorization.py` (role-based `AuthorizationPort`: actions requiring admin are an explicit set), `permission_aware_route.py` (the cookie scheme is now real: `APIKeyCookie(name=settings cookie)`), `shared_kernel/actor.py` (helper `is_admin`)
- Test: shared_kernel (100%), dependency tests, existing router tests keep passing through the default override fixture

**Interfaces:**
- Produces: `AccessScope` frozen dataclass (value object, no rules): `AccessScope.of(user_id: UUID)`, `AccessScope.everyone()`, `.user_id: UUID | None`, `.is_everyone`. `AccessPolicy` port (see decision 3) in `shared_kernel/access_policy.py` and `OwnerAccessPolicy` in `shared_kernel`-independent adapter code (`entrypoints/api/shared/access_policy.py`, pure, no I/O); `SYSTEM_ACTOR` always gets `everyone()`; `get_access_policy()` dependency injected into every use case that touches content. Unauthenticated routes (auth status/setup/login, health, version, docs) do not depend on `get_current_actor`.
- Test helper: a default `get_current_actor` override used by all existing router tests (member `UUID(int=1)`); explicit multi-user tests override per request.

- [ ] **Step 1:** failing tests: missing/expired/invalid cookie -> 401 `unauthenticated`; no users -> 401 `setup_required`; valid session -> Actor with the right id and role; disabled user's session rejected; `AccessScope` equality and constructors; admin action set denies members with 403.
- [ ] **Step 2:** implement; update the existing router tests' app construction to use the default override so the rest of the suite stays green.
- [ ] **Step 3:** gates incl. full coverage and the architecture tests.

### Task 4: Graph module — items and connections scoped

**Files:**
- Modify: `graph` ports and SQL/in-memory repositories (`node_repository.py`, `edge_repository.py` and twins): add required `scope: AccessScope` keyword argument to `get`, `list`, `count`, `count_with_attribute`, `list_with_attribute`, `list_attribute_values`, `clear_type`, and the edge equivalents (`get`, `list`, `list_for_node`, `has_edges_of_type`, `count_with_attribute`, `list_with_attribute`); `NodeModel`/`EdgeModel` gain nullable `owner_id` (UUID, indexed `(owner_id, id)`); `Node`/`Edge` domain entities require `owner_id`; all graph use cases take the `AccessPolicy`, pass `policy.scope_for(actor)` to repository calls, call `assert_can_view/modify/delete` on fetched entities, and set `owner_id=actor.id` on create; `CreateEdge`/`CreateEdges` require both endpoints visible (404 otherwise); admin-only use cases (`DeleteNodeType`, `DeleteEdgeType`, `Purge*Attribute`) check the role through `AuthorisedCommandHandler` and run their repository calls with `AccessScope.everyone()`; usage counts and attribute-value suggestions use the viewer's scope.
- Create: Alembic migration `k2f3a4b5c6d7_add_owner_to_nodes_and_edges.py`
- Test: repository tests (in-memory and Postgres) for every scoped method with two owners; use-case tests; node/edge/node_type/edge_type router tests with two users.

**Interfaces:**
- Consumes: Task 3 `AccessScope` and `AccessPolicy` (use cases call `policy.scope_for(actor)` and the `assert_can_*` methods; nothing reads `actor.id` as an owner outside the policy except when stamping `owner_id` on create).
- Produces: the scoped graph ports used by Tasks 5-7 and the bridges. Keyset pagination and the search clause (`_search_clause`) get the owner predicate ANDed first; `count` mirrors `list` exactly (so `Total-Count` cannot leak).

- [ ] **Step 1:** failing tests: for each repository method, A's rows invisible to B, visible to A and to `everyone()`; soft-deleted rows still excluded; search by `q` (name, description, attribute values, accent-insensitive) scoped; `ids=` filter scoped; counts equal list totals; creating an edge to another user's item is 404; members get 403 on admin-only structure operations while admins succeed and the effect spans all users' content.
- [ ] **Step 2:** implement; keep SQL predicates in one helper per repository so no query forgets them.
- [ ] **Step 3:** gates incl. the Postgres integration tests and `uv run poe coverage`.

### Task 5: Collections module — owner scope, per-owner slugs, per-viewer counts

**Files:**
- Modify: `collections` ports/repositories (+ twins): `get`, `get_by_slug`, `list` take `scope`; `uq_collections_slug_live` becomes `(owner_id, slug)` among live rows (migration `l3a4b5c6d7e8_collections_slug_per_owner.py`, also add the missing `owner_id` index); collection use cases pass `policy.scope_for(actor)`; `AddItemsToCollection` requires the items visible to the actor; the `ItemLookup` port gets a scope (`live_ids(ids, scope)`); bridges `collection_items.py` (`GraphItemLookup`) and `collection_members.py` pass the scope; `GET /node?collection=` returns nothing for a collection the viewer does not own (404 for the collection); ETags: `item_count` is the viewer-visible count.
- Test: use-case, bridge and router tests with two users.

**Interfaces:**
- Consumes: Task 4 scoped graph ports.
- Produces: collections visible only to their owner (slug lookups included), per-owner slug derivation (`-2` suffix independent of other users).

- [ ] **Step 1:** failing tests: B cannot get, list, update, delete or add to A's collection (404); the same collection name/slug for A and B both work; B adding A's item id to B's collection is rejected as not found; item counts reflect only visible items; `GET /node?collection=<A's id>` as B is 404; ETag differs between viewers when visible counts differ.
- [ ] **Step 2:** implement the migration and changes; slug uniqueness conflicts still answer 409 within one owner.
- [ ] **Step 3:** gates incl. Postgres tests.

### Task 6: Media module — asset ownership and access checks

**Files:**
- Modify: media models (`media_assets.owner_id` nullable, indexed), repositories/ports (+ twins): `MediaAssetRepository.get/list_by_status/...` take `scope` (system jobs `list_expired`, `list_by_status` use `everyone()`), `MediaAttachmentRepository.list_for_target/list_for_asset` follow the asset; domain `MediaAsset` requires `owner_id`; use cases set the owner from the actor and check ownership on get/content/thumbnail/update/delete/attach/detach/cover/promote/orphan; a new media-owned port `AttachTargetAccess.can_attach(target_type, target_id, scope) -> bool` implemented by a bridge in `entrypoints/api/shared/` using the scoped graph repositories (nodes and edges); CLI commands (`cleanup`, `regenerate_thumbnails`) run with `AccessScope.everyone()`.
- Create: migration `m4b5c6d7e8f9_add_owner_to_media_assets.py`
- Test: media use-case, bridge and router tests with two users (content and thumbnail endpoints included).

- [ ] **Step 1:** failing tests: B gets 404 for A's asset on get, content, thumbnail, update, delete, attachments; B cannot attach A's asset or attach to A's item; listing media for A's node as B is 404/empty; staged uploads are owned by their uploader; system cleanup still sees everything.
- [ ] **Step 2:** implement; also set `Cache-Control: private` where responses are user-specific (content already is), and keep the immutable sha-keyed cache.
- [ ] **Step 3:** gates incl. Postgres tests.

### Task 7: Examples module — per-user installations and shared type reuse

**Files:**
- Modify: `example_installations` model/repository (+ twin): `owner_id` nullable, unique active index becomes `(pack_id, owner_id)`; all `InstallationRepository` methods take `scope` (`get_active_for_pack`, `list_active`, `list_for_pack`, `get`); install/uninstall/list use cases take the actor and run pack targets as that actor (thread the actor/scope through `build_*_stores` and the four pack targets in `entrypoints/api/shared/example_targets.py`, replacing `SYSTEM_ACTOR`); `required_by`/`dependants_by_pack` and requirement resolution use the installing user's installations only; **shared types**: `_check_slugs` reuses an existing type whose slug is created by an installation of the same pack owned by another user (decision 7) and records nothing for it; type removal's in-use check (`nodes.list(type=)`, `has_edges_of_type`) uses `AccessScope.everyone()` so another user's content keeps the type alive; `ListExampleEntities` (Example badge) is scoped to the viewer's own installations.
- Create: migration `n5c6d7e8f9a0_example_installations_per_owner.py`
- Test: examples use-case and Postgres tests with two users.

- [ ] **Step 1:** failing tests: A and B each install the same pack; both get their own items and collections; B's install reuses the shared types and does not 409; A removing the pack keeps the shared types while B's items use them and removes them once B also removes; A cannot see B's installation or entities; a type clash with an unrelated type still 409s; add-on requirements resolve against the installer's own base installation; reinstall/re-adoption works per user.
- [ ] **Step 2:** implement; update the existing examples tests' `make_world` for the actor.
- [ ] **Step 3:** gates incl. Postgres tests and the full coverage run.

### Task 8: Existing-data claim and `identity` CLI

**Files:**
- Create: `identity/ports/existing_data_claim.py` (`ExistingDataClaim.claim(owner_id) -> ClaimReport`, owned by identity); **each module owns the claim of its own tables** through a small use case and port of its own: `graph` `ClaimOrphanedItems` (nodes and edges with a NULL owner), `collections` `ClaimLegacyCollections` (collections owned by `UUID(int=0)`, `UUID(int=1)` or NULL), `media` `ClaimOrphanedMedia` (assets with a NULL owner), `examples` `ClaimOrphanedInstallations`; the bridge `entrypoints/api/shared/claim_existing_data.py` implements identity's `ExistingDataClaim` by calling those four use cases in one unit of work (no module touches another's tables), `identity/adapters/cli/identity_app.py` (`menagerist identity create-admin --username`, `reset-password --username`, `list`; passwords read from a prompt or `MENAGERIST_INITIAL_PASSWORD`, never echoed) registered in the main CLI.
- Modify: `SetupFirstAdmin` (Task 2) to call the claim port; the router for `POST /auth/setup` returns the claim counts.
- Test: bridge test on Postgres with rows in every table including NULL and the two legacy owner ids; setup twice refused; CLI tests.

- [ ] **Step 1:** failing tests: after setup every pre-existing row has `owner_id = admin.id`; counts reported; rows created after setup are untouched; a failure inside the claim rolls the whole setup back (no admin, no partial claim).
- [ ] **Step 2:** implement; gates incl. Postgres.

### Task 9: Generated cross-user route check and architecture rules

**Files:**
- Create: `backend/tests/entrypoints/test_cross_user_isolation.py`, additions to `backend/tests/architecture/test_architecture.py`

- [ ] **Step 1:** the generated check: build the real app with in-memory repositories for every module, seed user A with content in every content type (item, connection, collection with item, media asset attached to an item, example installation with entities, plus a staged upload), then enumerate **every route from the app's OpenAPI/route table** that is not in a small explicit allow-list (health, version, docs, SPA, auth routes, structure list/get routes, preset routes), call it as user B with A's ids filled into path/query/body by parameter name, and assert 404, 403 (admin-only), or an empty/zero result. A route missing from both the allow-list and the check fails the test, so a new route cannot ship without isolation coverage. Include list/search/count routes with `q` and filters, `Total-Count`, ETag conditional requests, and media content/thumbnail.
- [ ] **Step 2:** architecture tests: every public method on the `NodeRepository`, `EdgeRepository`, `CollectionRepository`, `MembershipRepository`, `ItemLookup`, `MediaAssetRepository`, `MediaAttachmentRepository` and `InstallationRepository` ports that is not on a short explicit allow-list (`add`, `save`) has a `scope` parameter of type `AccessScope`; the same for the in-memory and SQL implementations (compare signatures).
- [ ] **Step 3:** gates.

### Task 10: Frontend sign-in, setup, user menu, Users page (svelte-file-editor)

**Files:**
- Create: `frontend/src/routes/login/+page.svelte`, `frontend/src/routes/setup/+page.svelte`, `frontend/src/routes/settings/users/+page.svelte`, `frontend/src/routes/settings/account/+page.svelte`, `frontend/src/lib/auth.svelte.ts` (singleton controller: current user, status check, sign in/out, `mustChangePassword`), pure helpers in `frontend/src/lib/auth.ts` (+ tests)
- Modify: `frontend/src/routes/+layout.svelte` (guard: on load call `/auth/status` and `/auth/me`; redirect to `/setup` when setup is required, to `/login?next=` when unauthenticated, to the account page when a password change is required; a header user menu with display name, Account, Sign out; hide Users for members), `frontend/src/lib/api/client.ts` and `etag-interceptor.ts` (send the `X-CSRF-Token` header from the `menagerist_csrf` cookie on unsafe methods; a response interceptor: 401 clears auth state and redirects to sign-in once; **clear the ETag/body cache on sign-in and sign-out**), `frontend/src/routes/settings/+page.svelte` (Users and Account cards), `frontend/README.md`, shortcut registry unaffected.
- Test: Vitest for the helpers and interceptors; the route guard logic as a pure function.

**Interfaces:**
- Consumes: Task 2 generated client. Produces: pages with 44 px targets, plain-words errors from the server's `detail`, the `next` parameter validated to same-origin paths only (open-redirect guard, unit-tested), password fields with `autocomplete` attributes, no password ever stored client-side.

- [ ] **Step 1:** unit tests for `safeNext`, the guard decision table (status x route), CSRF header attachment, 401 handling once, cache clearing.
- [ ] **Step 2:** the pages and layout changes; Svelte autofixer on each real file; mobile layout at 360 px.
- [ ] **Step 3:** `uv run poe format`, `lint-frontend`, `typecheck-frontend`, `test-frontend`, `npm run build`.

### Task 11: E2E authentication, isolation specs, docs and final gate

**Files:**
- Modify: `frontend/playwright.config.ts` and `frontend/tests/e2e/fixtures.ts` (per-worker global setup: call `POST /auth/setup` on the worker's backend if the database has no users, otherwise sign in; store `storageState` per worker; the CSRF header is attached to `request` fixtures and `page` API calls; `scripts/e2e_migrate.py` leaves databases empty so setup runs through the real endpoint), `frontend/tests/e2e/helpers.ts` (`signIn`, `createUserViaApi(admin, ...)`, `asUser(browser, user)`), every spec that calls the API directly through `request` (they need the CSRF token and session; adjust the shared helper once).
- Create: `frontend/tests/e2e/auth.spec.ts` (first-run setup on a dedicated extra database/backend `menagerist_auth` on port 8190 via a Playwright project `auth` with its own `webServer`; sign in, sign out, wrong password message, forced password change, expired session redirect), `frontend/tests/e2e/isolation.spec.ts` (two users: B sees none of A's items/collections/media in lists, search, collection page, direct URLs 404; admin creates a member; a member cannot open Users; per-user example install).
- Modify docs: `docs/DECISIONS.md` (accounts and ownership entry replacing "AllowAll authorization adapter in v1" and "Collection ownership is stored but not enforced"; the planning decisions above), `docs/ARCHITECTURE.md`, `backend/README.md` (identity module, AccessScope rule, scoping every new repository method), `CONTRIBUTING.md` (first-run setup, `menagerist identity` commands, resetting a forgotten admin password), `frontend/README.md`, root `README.md` quickstart (first visit creates the admin).

- [ ] **Step 1:** make the existing e2e suite authenticate with minimal churn (one fixture + helper change), run it single-spec on chromium and mobile, then add the new specs.
- [ ] **Step 2:** full gate, real totals from final summary lines: `uv run poe lint`, `uv run poe typecheck`, `uv run poe coverage`, `uv run poe test-frontend`, full `uv run poe test-e2e` (expect a longer run; report wall-clock).
- [ ] **Step 3:** hand the owner one commit message (or a commit per task if the diff is large; the pre-commit hooks require everything staged together) and the migration reminder: `poe migrate`, then open the app and create the first admin.
