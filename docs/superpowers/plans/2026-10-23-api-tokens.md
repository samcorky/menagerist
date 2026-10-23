# API tokens (personal access tokens) Implementation Plan

**Status:** done 2026-10-23, committed as `b77a920` (identity storage, use cases, bearer authentication), `a7c4105` (token endpoints, bearer scheme in the API docs, Swagger session section) and `a1f1318` (Tokens card, accurate error documentation, token-aware Swagger). Decisions are recorded in `docs/DECISIONS.md`, "Personal access tokens (2026-10-23)".

**Deviations from this plan:**

- Request and response fields are snake_case (`expires_in_days`, `created_at`, `last_used_at`), not camelCase.
- Request `grants` is `list[str]`, so an unknown or unheld grant is a 400, not a 422; `GET /api/v1/tokens/grants` returns the grantable `Permission` list.
- The bearer scheme is derived by `PermissionAwareRoute` from `get_current_actor` and `TOKEN_GRANTABLE_PERMISSIONS`, not flagged per permission; admin-only and token or account routes list the cookie scheme only.
- Swagger's Authorize dialog has a "Browser session" block (Sign in, Set up, Sign out) above the bearer block; the page banner (no sign-in buttons) reports session, token, both, rejected or could-not-check, verifying a pasted token with `GET /api/v1/auth/me/permissions`.
- Rotate: an expired token cannot be rotated (404), grants the owner no longer holds are dropped and none left is a 400, ownership and grant checks run after the password check, and refusals commit so the throttle settles.
- Request validation runs before the throttle reservation, so malformed requests do not burn attempts.
- `api_tokens` is `TableRule.SKIP` in the backup table rules (needed by the backup architecture test).
- The role-flag guard-rail also allow-lists `entrypoints/api/shared/access_policy.py`; no CLI or identity file reads the flags.
- Added beyond the plan: central 401, 403, 404, 422 and 500 `application/problem+json` components with named examples, a sweep fixing about 100 inaccurate examples, and `test_openapi_response_examples.py` enforcing that every example matches its status; `token_id` is also in the access log.
- Token card UX: the sample command uses `/api/v1/auth/me/permissions`, the Name field takes focus on open, and the Advanced trigger has a chevron.


> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A signed-in person can create, list and revoke personal access tokens that act as them with a chosen subset of their permissions, usable from scripts and from Swagger, while sign-in and account management stay session-only.

**Architecture:** Tokens live in the `identity` module (hexagonal: `ApiToken` entity, `ApiTokenRepository` and `ApiTokenGenerator` ports, use cases, SQLAlchemy and in-memory adapters). `Actor` gains `grants`; the existing `RoleAuthorisationAdapter` intersects the owner's permissions with the token's grants, so the access guard and every use case stay unchanged. One dependency, `get_current_actor`, decides the credential: an `Authorization: Bearer` token or the session cookie, never both.

**Tech Stack:** FastAPI, SQLAlchemy with Alembic on Postgres, structlog, SvelteKit 5 runes, shadcn-svelte, Vitest, Playwright.

**Spec:** `docs/superpowers/plans/2026-10-20-api-tokens-and-permissions.md` (Phase 4 and the sections "Token flavours" and "Swagger and `PermissionAwareRoute`"), `docs/DECISIONS.md` ("Content permissions as enums with `implied()`"), `docs/superpowers/plans/2026-10-22-content-permissions.md`. Executors read the Phase 4 section first.

## Global Constraints

- Never create, stage or push commits; the user commits. Work in the repo, leave changes uncommitted.
- British English in code, comments, docs and UI copy. Comments short and factual; Google-style docstrings only where they add value.
- Dependency direction `entrypoints → adapters → application → domain`; `application/` has no ports and no adapter imports; ports in `ports/`; every port ships an in-memory sibling in `adapters/persistence/` (a port that is a pure function of its inputs, such as the generator, has one adapter).
- Every use case sets `access = ...` and implements `_handle`; stance sets are pinned by name in `tests/architecture/test_access_stances.py`.
- Domain errors subclass `shared_kernel.errors` base types; no `try/except` in routers.
- Coverage floors: domain, application, shared_kernel 100%; adapters 80%; platform 70%. `poe coverage` before finishing backend work.
- `.svelte` and `.svelte.ts` files go through the `svelte-file-editor` subagent. Frontend UI follows `frontend/DESIGN_GUIDELINES.md`: no permission strings or graph terms in visible text ("Items", "Item types", "Collections", "Media", "Presets").
- Subagents: no more than Sonnet 5.5 at medium effort; Haiku for mechanical work; always pass `model` and `effort`.
- Token format `mnst_<id>_<secret>`: `id` is the token row's uuid in 32-character hex, `secret` is 64 hex characters (`secrets.token_hex(32)`). Stored: SHA-256 hex of the secret only.
- Never log a token, its secret or the `Authorization` header; log the token id.

## Rulings made while planning

Recorded so executors do not reopen them. Each says what it costs if wrong.

- **R1 (Q5 limits):** default lifetime 90 days, maximum 365, at most 20 active tokens per user, expiry mandatory; `last_used_at` written at most once a minute. Settings `api_token_default_days`, `api_token_max_days`, `api_tokens_per_user` on `IdentitySettings`. Cost: three env values to tune.
- **R2 (grantable set):** v1 grants are the content permissions except `backup:own_data:export` and `backup:own_data:import` (a leaked token must not mass-export or overwrite an account; scripts have the backup CLI). Held as `TOKEN_GRANTABLE_PERMISSIONS` in `entrypoints/api/shared/authorisation.py`. No admin permission is grantable. Cost: widen the set later with a one-line edit and a changed pin.
- **R3 (revoke deletes):** revoking deletes the row (as sessions do). A revoked and an unknown token are both a 401. No `revoked` field. Cost: no audit trail beyond the log lines.
- **R4 (password events):** `ChangePassword` and `ResetPassword` also delete the user's tokens, so a password change is "sign out everywhere", tokens included. Cost: scripts need a new token after a password change.
- **R5 (non-Bearer schemes):** only `Authorization: Bearer` is a token credential. Any other scheme (a proxy's `Basic`) is ignored and the cookie path runs as before. An empty or malformed bearer value is a 401.
- **R6 (bearer is authoritative):** when a Bearer header is present the cookie is never read: an invalid, expired or unknown token is a 401 and never falls back to the cookie. This is implemented once, in `get_session_token` (returns `None` beside a bearer header), so every cookie-only route also refuses such a request, which makes skipping CSRF for bearer requests safe.
- **R7 (password expired, disabled):** a token request is refused when its owner is disabled (401) or must change their password (`PasswordExpiredError`), exactly as for a session.
- **R8 (composites):** a composite use case needs every inner permission, because inner calls hit the guard with the same actor. No new implications are added. Pinned by a table test (Task 3) covering `media.UploadAndAttachMedia`, `graph.PromoteExtraSchemaField` (`graph:type:write` and `graph:item:write`) and `backup.ImportUserArchive`. The "Read and write" preset holds both. Cost: a token with only `graph:type:write` cannot promote a field.
- **R9 (no WWW-Authenticate):** the error handler has no per-exception header support, so the 401 omits `WWW-Authenticate: Bearer`. Cost: strict RFC 6750 clients may not show a hint; add when the handler supports headers.
- **R10 (no admin view):** administrators cannot list or revoke other people's tokens in v1; disabling the user stops them. Cost: a later `identity:token:*` permission.
- **R12 (rotation, no extension):** expiry is never extended in place. `RotateApiToken` keeps the name and grants, issues a new secret and expiry (same limits as create, password required, throttled like create) and deletes the old row at once; it does not count against the per-user limit because it replaces a token. Cost: scripts need the new secret, as they would after any expiry.
- **R11 (CORS):** `Authorization` is not added to `CORS_REQUEST_HEADERS`; there is no cross-origin browser client. Cost: one list entry when one exists.

## Review Focus

Inputs and conditions the spec implies but the feature tasks do not obviously exercise; each has its test in the named task.

1. A request with both a valid session cookie and a bearer token for a *different* user is that token's user, and a bad bearer beside a valid cookie is 401, not the cookie's user (Task 5).
2. `Authorization: Basic …` from a reverse proxy leaves cookie sign-in working (Task 5).
3. A token request with no `Origin` or `Sec-Fetch-Site` passes CSRF, while a cookie-only unsafe request with none still fails (Task 5).
4. The owner losing the role that held a permission, being disabled, locked out by a password reset or having the password changed takes effect on the next request (Tasks 3, 4, 5).
5. Expired and unknown tokens are indistinguishable from the outside, and an unknown id costs the same hash and comparison as a wrong secret (Tasks 1, 4).

---

## File Structure

Backend, under `backend/src/app/`:

- `modules/identity/domain/api_token.py` (new): `ApiToken`, name and grant rules.
- `modules/identity/domain/errors.py`: four new errors.
- `modules/identity/ports/api_token_repository.py`, `api_token_generator.py` (new); `ports/unit_of_work.py` gains `tokens`.
- `modules/identity/application/`: `create_api_token.py`, `list_own_api_tokens.py`, `revoke_own_api_token.py`, `authenticate_api_token.py`, `rotate_api_token.py`, `list_grantable_permissions.py` (new); `change_password.py` and `reset_password.py` edited.
- `modules/identity/adapters/persistence/`: `models.py` (+`ApiTokenModel`), `api_token_repository.py`, `in_memory_api_token_repository.py` (new), `unit_of_work.py`; migration `alembic/versions/w4f5a6b7c8d9_api_tokens.py`.
- `modules/identity/adapters/security/secrets_api_token_generator.py` (new).
- `modules/identity/adapters/api/`: `token_router.py`, `dependencies.py`, `schemas.py` additions.
- `shared_kernel/actor.py`: `grants`.
- `entrypoints/api/shared/authorisation.py`, `access_guard.py`, `dependencies.py`, `permission_aware_route.py`, `http/csrf.py`, `http/bearer.py` (new).
- `platform/config/identity.py`: three settings.
- `entrypoints/api/docs/` (templates, static) for Swagger; `entrypoints/api/__init__.py` mounts the router.

Frontend: `src/routes/settings/account/+page.svelte` gains a Tokens card (Task 8), with logic in a plain `src/lib/api-tokens.ts`; `tests/e2e/swagger.spec.ts` and a new `tests/e2e/api-tokens.spec.ts`.

---

### Task 1: Domain, errors, generator port and settings

**Files:**
- Create: `modules/identity/domain/api_token.py`, `modules/identity/ports/api_token_generator.py`, `modules/identity/adapters/security/secrets_api_token_generator.py`
- Modify: `modules/identity/domain/errors.py`, `platform/config/identity.py`
- Test: `tests/modules/identity/domain/test_api_token.py`, `tests/modules/identity/adapters/test_secrets_api_token_generator.py`, `tests/platform/test_identity_settings.py`

**Interfaces:**
- Produces:
  - `ApiToken(Identifiable)` dataclass `kw_only=True, eq=False`: `user_id: uuid.UUID`, `name: str`, `secret_hash: str`, `grants: frozenset[str]`, `created_at: datetime`, `expires_at: datetime`, `last_used_at: datetime | None = None`. `ApiToken.create(*, token_id: uuid.UUID, user_id, name: str, secret_hash: str, grants: Iterable[str], now: datetime, expires_at: datetime) -> ApiToken` strips the name, requires 1 to `MAX_TOKEN_NAME_LENGTH = 64` characters and at least one grant, and requires `expires_at > now`; otherwise raises `InvalidApiTokenRequestError`. Methods `is_expired(now) -> bool` (at or past expiry), `used(now) -> None`.
  - Errors in `domain/errors.py`: `InvalidApiTokenError(UnauthenticatedError)` with `problem_type = "invalid_token"`; `InvalidApiTokenRequestError(ValidationError)`; `ApiTokenLimitError(ConflictError)`; `ApiTokenNotFoundError(NotFoundError)`.
  - `ApiTokenGenerator` Protocol: `new_token() -> NewApiToken`, `parse(value: str) -> ParsedApiToken | None`, `hash(secret: str) -> str`, `matches(secret: str, stored_hash: str) -> bool`; frozen dataclasses `NewApiToken(token_id: uuid.UUID, secret: str, plaintext: str)` and `ParsedApiToken(token_id: uuid.UUID, secret: str)` live in the port module.
  - `SecretsApiTokenGenerator` implementing it; `matches` uses `hmac.compare_digest` on the hashes.
  - `IdentitySettings`: `api_token_default_days: int = 90 (ge=1)`, `api_token_max_days: int = 365 (ge=1)`, `api_tokens_per_user: int = 20 (ge=1)`, each with a description; a model validator rejects default greater than max.

- [ ] **Step 1: Write the failing tests.** Domain: create strips and stores; empty or 65-character name, no grants, and past or equal expiry each raise `InvalidApiTokenRequestError`; `is_expired` is true exactly at `expires_at`; `used` sets `last_used_at`. Generator: `new_token().plaintext == f"mnst_{token_id.hex}_{secret}"` with a 64-hex secret; `parse(plaintext)` round-trips; `parse` returns `None` for wrong prefix, a non-hex id, a short or non-hex secret, extra segments, and empty string; `hash` is the SHA-256 hex of the secret; `matches` is true only for the right pair. Settings: defaults, and default above max fails validation.
- [ ] **Step 2: Run them, expect failures** (`cd backend && uv run pytest <files> -q --no-cov`).
- [ ] **Step 3: Implement** the entity, errors, port, adapter and settings as specified above.
- [ ] **Step 4: Run** `poe lint-backend`, `poe typecheck-backend`, the new tests; domain 100%.

---

### Task 2: Repository port, adapters, migration and unit of work

**Files:**
- Create: `modules/identity/ports/api_token_repository.py`, `modules/identity/adapters/persistence/api_token_repository.py`, `modules/identity/adapters/persistence/in_memory_api_token_repository.py`, `alembic/versions/w4f5a6b7c8d9_api_tokens.py`
- Modify: `modules/identity/ports/unit_of_work.py`, `modules/identity/adapters/persistence/models.py`, `modules/identity/adapters/persistence/unit_of_work.py`
- Test: `tests/modules/identity/adapters/test_api_token_repository.py` (a shared table of cases run against the in-memory adapter, and against SQLAlchemy marked `integration`), `tests/platform/test_migrations.py` (pattern as the existing migration tests)

**Interfaces:**
- Consumes: `ApiToken` (Task 1).
- Produces: `ApiTokenRepository` Protocol with `add(token)`, `save(token)`, `get(token_id) -> ApiToken | None`, `list_for_user(user_id, *, now) -> list[ApiToken]` (unexpired, newest `created_at` first), `count_active(user_id, *, now) -> int`, `delete(token_id) -> None` (unknown ignored), `delete_for_user(user_id) -> int`, `delete_expired(now) -> int`. `IdentityRepos` gains `tokens: ApiTokenRepository`; `build_identity_repos` builds it; `ApiTokenModel` table `api_tokens` (columns as the entity, `grants` as JSONB list of strings, `user_id` FK to `users.id` with `ON DELETE CASCADE` and an index, `expires_at` indexed, `secret_hash` not unique).

- [ ] **Step 1: Failing tests** over the shared case table: add then get round-trips every field including `grants`; `list_for_user` hides expired, orders newest first, never returns another user's; `count_active` agrees; `delete` of an unknown id is a no-op; `delete_for_user` returns the count and spares others; `delete_expired` removes only expired; `save` persists `last_used_at`. Migration: upgrade creates the table, downgrade drops it, and the cascade removes tokens with their user.
- [ ] **Step 2: Run, expect failure.**
- [ ] **Step 3: Implement** port, both adapters, model, migration (revision after `v3e4f5a6b7c8`) and the unit-of-work wiring; update every place that builds `IdentityRepos` by hand (grep `IdentityRepos(` in `src` and `tests`; test fixtures gain `tokens=InMemoryApiTokenRepository()`).
- [ ] **Step 4: Run** lint, mypy, `poe test-backend`, the Postgres tests for the repository and migration, architecture and cqrs tests.

---

### Task 3: Actor grants, the intersection and the grantable catalogue

**Files:**
- Modify: `shared_kernel/actor.py`, `entrypoints/api/shared/authorisation.py`, `entrypoints/api/shared/access_guard.py`
- Test: `tests/shared_kernel/test_actor.py`, `tests/entrypoints/api/shared/test_authorisation.py`, `tests/entrypoints/api/shared/test_role_access_guard.py`, `tests/architecture/test_token_grants.py` (new), `tests/architecture/test_no_direct_ownership_checks.py` (extend)

**Interfaces:**
- Produces: `Actor.grants: frozenset[str] | None = None` (`None` means a session: no ceiling); `TOKEN_GRANTABLE_PERMISSIONS: frozenset[Permission]` per R2; `RoleAuthorisationAdapter.effective_permissions(actor)` returns the owner's expanded permissions, intersected with the expanded grants when `actor.grants is not None` (grant strings that name no catalogue permission are dropped, so they deny); `RoleAccessGuard.check` refuses `OwnAccount` when `actor.grants is not None` (`ForbiddenError`, same message), leaves `Public` and `System` as they are. `check` keeps calling the authorisation port for `Requires` and `Content`, so no use case changes.

- [ ] **Step 1: Failing tests.** Adapter: member with grants `{graph:item:write}` holds `graph:item:write` and the implied `graph:item:read` and nothing else; admin with the same grants holds exactly those two (never admin permissions); a grant outside the owner's role is not added (member with `identity:user:list`); unknown grant strings add nothing; `grants=None` is unchanged from today; `GET`-style `get_my_permissions` therefore returns the intersection (assert through `effective_permissions`). Guard: token actor refused on `OwnAccount`, allowed on `Public`, refused for `System`; session actor unchanged. Architecture: `TOKEN_GRANTABLE_PERMISSIONS` is a subset of `MEMBER_PERMISSIONS`, contains no `ADMIN_ONLY_ACTIONS` member and no `BackupPermission`; every grantable permission's implications are grantable too; a `COMPOSITES` table (R8: `UploadAndAttachMedia` needs `{media:item:write}`, `PromoteExtraSchemaField` needs `{graph:type:write, graph:item:write}`, `ImportUserArchive` needs `{backup:own_data:import}`) agrees with the use cases' declared stances plus their inner use cases' stances (read the inner classes in the test, do not retype them); `actor.is_admin` and `actor.is_system` appear in `src/` only in `authorisation.py`, `access_guard.py` and `shared_kernel/` (extend the existing ast guard-rail; allow-list the CLI and identity files it currently allows, and record why in the test).
- [ ] **Step 2: Run, expect failure.**
- [ ] **Step 3: Implement.** One line on the grantable set: the content permissions minus the two backup permissions.
- [ ] **Step 4: Run** lint, mypy, `poe test-backend`, architecture tests; shared_kernel 100%.

---

### Task 4: Use cases

**Files:**
- Create: the six use case files under `modules/identity/application/`
- Modify: `change_password.py`, `reset_password.py`, `tests/architecture/test_access_stances.py`
- Test: `tests/modules/identity/application/test_create_api_token.py`, `test_list_own_api_tokens.py`, `test_revoke_own_api_token.py`, `test_authenticate_api_token.py`, `test_rotate_api_token.py`, `test_list_grantable_permissions.py`, plus additions to the change-password and reset-password tests

**Interfaces:**
- Consumes: `ApiToken`, `ApiTokenGenerator`, `IdentityRepos.tokens`, `AuthorisationPort`, `PasswordHasher`, `SignInThrottle`, `user_id_key`, `ip_key` (as `ChangePassword` uses them).
- Produces (all in `identity.application`):
  - `CreateApiToken(CommandHandler[IdentityUnitOfWork, CreateApiTokenCommand, CreatedApiToken])`, `access = OwnAccount()`. `__init__(uow, guard, hasher, tokens: ApiTokenGenerator, throttle, authorisation: AuthorisationPort, *, grantable: frozenset[str], default_days: int, max_days: int, max_tokens: int)`. `CreateApiTokenCommand(name, password, grants: frozenset[str], expires_in_days: int | None, client_ip: str | None = None)` with a `__repr__` that hides the password. `CreatedApiToken(token: ApiToken, plaintext: str)`.
  - `ListOwnApiTokens(QueryHandler[IdentityRepos, ListOwnApiTokensQuery, list[ApiToken]])`, `OwnAccount`.
  - `RevokeOwnApiToken(CommandHandler[..., RevokeOwnApiTokenCommand(token_id), None])`, `OwnAccount`; another user's id raises `ApiTokenNotFoundError`.
  - `RotateApiToken(CommandHandler[IdentityUnitOfWork, RotateApiTokenCommand, CreatedApiToken])`, `OwnAccount`, same constructor dependencies as `CreateApiToken` except `grantable` and `max_tokens`. `RotateApiTokenCommand(token_id, password, expires_in_days: int | None, client_ip: str | None = None)` with a `__repr__` that hides the password. Re-validates the stored grants against what the owner holds now (a grant the owner has since lost is dropped; if none remain, `InvalidApiTokenRequestError`), keeps `name`, gets a new id, secret and expiry, and deletes the old row in the same transaction.
  - `AuthenticateApiToken(CommandHandler[IdentityUnitOfWork, AuthenticateApiTokenCommand(value: str), ResolvedApiToken | None])`, `access = Public()`, `__repr__` hides the value; `ResolvedApiToken(user: User, token_id: uuid.UUID, grants: frozenset[str])` frozen.
  - `ListGrantablePermissions(QueryHandler[IdentityRepos, ListGrantablePermissionsQuery, list[str]])`, `OwnAccount`, `__init__(repos, guard, authorisation, *, grantable)`: returns the sorted grantable permissions the acting owner holds.

- [ ] **Step 1: Failing tests.**
  - Create: wrong password raises `CurrentPasswordIncorrectError` and counts as a throttled failure, a locked user is `SignInThrottledError`; a grant outside `grantable`, one the owner does not hold (checked with `authorisation.check`), an empty set, a lifetime above `max_days` or below 1 each raise `InvalidApiTokenRequestError`; `expires_in_days=None` uses `default_days`; the 21st active token raises `ApiTokenLimitError`; expired rows are purged on create; the plaintext is returned once and only its hash is stored; the log line carries the token id and no secret.
  - List: own, unexpired, newest first, nothing of another user.
  - Rotate: wrong password is `CurrentPasswordIncorrectError` and throttled; another user's or unknown id is `ApiTokenNotFoundError`; the old plaintext no longer authenticates and the new one does, with the same name and grants and the new expiry; the lifetime rules match create; rotating at the per-user limit succeeds; a grant the owner has lost is dropped (and all lost is refused); logs old and new ids, no secret.
  - Revoke: deletes, unknown or foreign id is `ApiTokenNotFoundError`, logs the id.
  - Authenticate: valid value resolves user and grants; unparseable, unknown id, wrong secret, expired (row deleted) and disabled owner each return `None`; an unknown id still performs one `hash` and one `matches` against a decoy (assert via a spy generator); `last_used_at` is written when `None` or older than one minute and not otherwise.
  - Grantable: a member sees the 12 grantable content permissions; an admin sees the same (no admin permission); a removed role permission disappears from the list.
  - Password events: `ChangePassword` and `ResetPassword` delete the user's tokens (R4) and log the count.
  - Stances: add `identity.CreateApiToken`, `ListOwnApiTokens`, `RevokeOwnApiToken`, `RotateApiToken`, `ListGrantablePermissions` to `EXPECTED_OWN_ACCOUNT` and `identity.AuthenticateApiToken` to `EXPECTED_PUBLIC`.
- [ ] **Step 2: Run, expect failure.**
- [ ] **Step 3: Implement.** `CreateApiToken` follows `ChangePassword`'s throttle reserve/settle flow and `asyncio.to_thread` for the hash check.
- [ ] **Step 4: Run** lint, mypy, `poe test-backend`, architecture and cqrs tests; application 100%.

---

### Task 5: Authenticating requests: bearer or cookie

**Files:**
- Create: `entrypoints/api/shared/http/bearer.py`
- Modify: `modules/identity/adapters/api/dependencies.py`, `entrypoints/api/shared/dependencies.py`, `entrypoints/api/shared/http/csrf.py`
- Test: `tests/entrypoints/api/shared/http/test_bearer.py`, `tests/entrypoints/api/shared/http/test_csrf.py`, `tests/modules/identity/adapters/test_current_actor.py` (extend), `tests/entrypoints/api/shared/test_authenticated_routes.py` (extend)

**Interfaces:**
- Consumes: `AuthenticateApiToken`, `ApiTokenGenerator` provider.
- Produces: `bearer_token(request: Request) -> str | None` (the value after `Bearer ` for a case-insensitive `Bearer` scheme; `None` for no header or another scheme; empty value returns `""` so it is rejected, R5); `get_session_token` returns `None` whenever `bearer_token(request) is not None` (R6); `get_current_actor` resolves a bearer first: invalid raises `InvalidApiTokenError("The access token is not valid.")`, otherwise it applies R7, binds `token_id` (never the secret) into the log context and `request.state.token_id`, and returns `Actor(id=user.id, roles=frozenset({user.role.value}), grants=resolved.grants)`; with no bearer it behaves as today. `verify_csrf` returns early when `bearer_token(request) is not None`. `get_current_actor` gains the `AuthenticateApiToken` dependency through a provider `get_authenticate_api_token_use_case` in identity's dependencies.

- [ ] **Step 1: Failing tests.**
  - Bearer parsing: `Bearer x`, `bearer x`, `Basic abc` (None), no header, `Bearer ` (empty string).
  - Actor: a valid token gives its owner with exactly its grants; a bad, unknown or expired token is 401 `invalid_token`; **bad bearer plus valid cookie is 401** and **a valid bearer plus another user's cookie is the token's owner** (Review Focus 1); `Authorization: Basic …` plus a valid cookie is the cookie user (Review Focus 2); disabled owner is 401, password-expired owner raises `PasswordExpiredError` (R7); a token request to an `OwnAccount` route (for example `GET /api/v1/session`, `POST /api/v1/auth/password`) is 401 because those routes read only the cookie.
  - CSRF: an unsafe request with a bearer and no `Origin` or `Sec-Fetch-Site` passes; an unsafe cookie request with none still fails with `csrf_failed`; a cross-site unsafe request carrying a cookie *and* a bearer is not refused by CSRF but is authenticated by the token alone and cannot use the cookie (Review Focus 3).
  - Logging: capture logs for a token request and assert the secret and the header never appear and `token_id` does.
- [ ] **Step 2: Run, expect failure.**
- [ ] **Step 3: Implement.**
- [ ] **Step 4: Run** lint, mypy, `poe test-backend`, architecture tests.

---

### Task 6: Token endpoints and client

**Files:**
- Create: `modules/identity/adapters/api/token_router.py`
- Modify: `modules/identity/adapters/api/schemas.py` (token schemas), `modules/identity/adapters/api/dependencies.py` (providers), `entrypoints/api/__init__.py` (mount on `api_v1_router`), `tests/entrypoints/api/shared/test_openapi_permissions_pinned.py`, `tests/entrypoints/test_cross_user_isolation.py`
- Test: `tests/modules/identity/adapters/test_token_router.py`

**Interfaces:**
- Produces, all session-only through `get_active_identity_actor` (cookie dependencies, so a token cannot call them):
  - `POST /api/v1/tokens` (`operation_id` `create_api_token`) body `{name, password, grants: [Permission], expiresInDays?}` → 201 `{id, name, grants, createdAt, expiresAt, lastUsedAt, token}` where `token` is the plaintext, present only here; `Cache-Control: no-store`.
  - `GET /api/v1/tokens` (`list_api_tokens`) → list of the same without `token`.
  - `DELETE /api/v1/tokens/{token_id}` (`revoke_api_token`) → 204.
  - `POST /api/v1/tokens/{token_id}/rotate` (`rotate_api_token`) body `{password, expiresInDays?}` → 201 with the same body as create (new id, plaintext once, `Cache-Control: no-store`); 404 for another user's id.
  - `GET /api/v1/tokens/grants` (`list_grantable_permissions`) → `{permissions: [Permission]}` the acting account may grant.
  - Router `tags=["API tokens"]`, built with `PermissionAwareRoute`; error responses documented for 400, 401, 404 and 409 with `error_response`, in the style of `session_router.py`.

- [ ] **Step 1: Failing tests.** Create returns 201 with a `mnst_` token that then authenticates `GET /api/v1/node-type` via `Authorization: Bearer`; wrong password 400; bad grant 400; limit 409; the secret is absent from list and from logs; list shows only own; revoke then the token is 401; another user's id is 404; a request with a bearer token to any `/tokens` route is 401; CSRF is required for the unsafe routes; rotate returns a new working token and the old one is 401, another user's id is 404, wrong password 400; OpenAPI operations for the five routes carry no `x-required-permission` and appear in the pin test as `OwnAccount`; the isolation test covers the new routes (another user's token id is 404).
- [ ] **Step 2: Run, expect failure.**
- [ ] **Step 3: Implement the router and providers; mount; run `uv run poe generate-frontend-client`** (the client is git-ignored, so there is nothing to commit).
- [ ] **Step 4: Run** lint, mypy, `poe test-backend`, relevant Postgres tests, architecture tests; `poe typecheck-frontend`.

---

### Task 7: Swagger and `PermissionAwareRoute`

**Files:**
- Modify: `entrypoints/api/shared/permission_aware_route.py`, `entrypoints/api/docs/templates/swagger.html`, `entrypoints/api/docs/static/swagger-init.js`, `entrypoints/api/docs/templates/api-description.md`, `frontend/tests/e2e/swagger.spec.ts`
- Test: `tests/entrypoints/api/shared/test_permission_aware_route.py`, `tests/entrypoints/api/docs/test_docs.py`, `frontend/tests/e2e/swagger.spec.ts`, `frontend/tests/e2e/api-tokens.spec.ts`

**Interfaces:**
- Produces: `bearer_scheme = HTTPBearer(auto_error=False, description=...)` beside `cookie_scheme`; for routes whose use case declares `Requires` or `Content`, `PermissionAwareRoute` appends `Security(bearer_scheme)` after the cookie security (documentation only, as today); `OwnAccount`, `Public`, `System` routes get no bearer. Grants are documented only through `x-required-permission` (no OAuth scopes).

- [ ] **Step 1: Failing tests.** Schema: a content route's `security` lists cookie and bearer as **alternatives** (two separate requirement objects, not one object with both; if FastAPI merges them, change the approach until the test passes), a `/tokens` route lists only the cookie, `/auth/login` has none; `components.securitySchemes` contains the cookie apiKey and an `http` `bearer` scheme; `test_swagger_security_is_unchanged` becomes `test_swagger_security_schemes` asserting both; `api-description.md` has a "Using a token" section (mind the single `$` placeholder test) that shows `Authorization: Bearer mnst_…`, says tokens are created under Settings, Account, and that account and token management need the browser session. Playwright (isolated stack): the Authorize button is visible and its dialog lists the bearer scheme only (the cookie scheme is hidden); pasting a token created through the API and calling `GET /api/v1/node-type` from Swagger returns 200; the session lock logic still follows sign-in; `persistAuthorization` stays false so a reload forgets the token; `prepareRequest` still sends `Authorization`.
- [ ] **Step 2: Run, expect failure.**
- [ ] **Step 3: Implement.** Remove the `.auth-wrapper { display: none }` rule; hide the cookie scheme's block in the Authorize dialog from `swagger-init.js` by scheme name, inside the existing observer; keep `cookieSchemes()` ignoring `http` schemes; update the two `toBeHidden` assertions at `swagger.spec.ts:115` and `:191` and the locks test comment at `:205`.
- [ ] **Step 4: Run** lint-backend, mypy, the docs tests, `poe lint-frontend`; run the Swagger Playwright spec three times (known flake: the locks test passes alone).

---

### Task 8: Frontend: Tokens card on the account page

**Files:**
- Create: `frontend/src/lib/api-tokens.ts`, `frontend/src/lib/api-tokens.test.ts`
- Modify: `frontend/src/routes/settings/account/+page.svelte` (via the `svelte-file-editor` subagent)
- Test: `frontend/tests/e2e/api-tokens.spec.ts` (extends Task 7's file)

**Interfaces:**
- Produces in `api-tokens.ts` (plain TypeScript): `TOKEN_PRESETS` (`read`: "Read only" = every granted `*:read`; `readWrite`: "Read and write" = every granted permission), `grantLabels(permissions: string[]): string[]` mapping permission strings to "Items", "Item types", "Collections", "Media", "Presets", "Example packs" (never the raw string), `expiryOptions` (30, 90, 365 days, default 90), `describeExpiry(expiresAt, now)` (plus `expiresSoon`, true within 14 days), `describeLastUsed(lastUsedAt, now)` ("Never used", "Used today"…).
- The card, under the sessions card: a list (name, what it can do in words, expiry, last used, Regenerate and Revoke with confirmations; a token expiring within 14 days is flagged "Expires in N days"), "New token" opening a dialog (name, password, preset choice with an "Advanced" expander of per-area checkboxes, expiry select), and on success (create or Regenerate, which asks for the password and an expiry) a one-time panel showing the token with a Copy button, a warning that it will not be shown again, and a link to the API docs. Buttons and targets meet the 44 px rule from `DESIGN_GUIDELINES.md`; errors map `InvalidApiTokenRequestError`, wrong password and the limit to plain sentences.

- [ ] **Step 1: Failing tests** for each helper (presets over a sample grant list, labels never contain a colon, expiry and last-used wording at boundaries); e2e: create a token on the isolated stack, see it once, copy it, use it against the API with `request`, regenerate it and see the old secret fail and the new one work, revoke it and see a 401, and see the list update without a reload.
- [ ] **Step 2: Implement** the helpers, then dispatch `svelte-file-editor` (Sonnet, medium) for the card with the helper tests green.
- [ ] **Step 3: Run** `poe lint-frontend`, `poe typecheck-frontend`, `poe test-frontend`; run the e2e spec three times; check the card at desktop and phone width in light and dark.

---

### Task 9: Documentation and full gates

**Files:**
- Modify: `docs/DECISIONS.md`, `docs/ARCHITECTURE.md`, `backend/README.md`, `README.md` (user-facing section on tokens), `docs/superpowers/plans/2026-10-20-api-tokens-and-permissions.md`, `AGENTS.md` (one line on bearer-authoritative and session-only stances if the access paragraph needs it)

- [ ] **Step 1:** Add a DECISIONS entry "Personal access tokens (2026-10-23)" with R1 to R12 and their costs, superseding the Phase 4 sketch; mark Phase 4 done in the tokens plan and record Q5 as settled by R1; list the follow-ups (admin token view R10, `WWW-Authenticate` R9, OAuth only if third-party apps appear).
- [ ] **Step 2:** Update ARCHITECTURE (credential flow, the `grants` intersection) and backend README (new module pieces, the session-only rule, how to add a grantable permission).
- [ ] **Step 3: Full gates:** `poe lint`, `poe typecheck`, `poe test-frontend`, `poe coverage`, and the Swagger and token Playwright specs. Revert formatter changes to unrelated docs.
- [ ] **Step 4: Stop for review**, then a whole-feature review with the Review Focus list as its checklist and security as the lens (credential handling, logging, CSRF, fallbacks).

---

## Self-Review

- **Spec coverage:** model (T1, T2), actor grants and intersection (T3), grantable catalogue and no admin grants (T3), session-only stances (T3, T5, T6), creation needing the password, mandatory expiry and limits (T4), revoke and live effects (T4, T5), bearer authoritative and CSRF (T5), never logging the header (T5), CORS (R11), the admin-flag guard (T3), Swagger and `PermissionAwareRoute` (T7), `me/permissions` intersection (T3), UI with human labels (T8), composites (T3, R8), docs (T9).
- **Types:** `ApiToken`, `NewApiToken`, `ParsedApiToken`, `CreatedApiToken`, `ResolvedApiToken` and the four errors are named identically in every task that uses them; `grants` is `frozenset[str]` throughout; `bearer_token` is the one parser used by `get_session_token`, `get_current_actor` and `verify_csrf`.
- **Placement check:** entities, ports and use cases sit in `identity`; only the grantable set, the intersection and the HTTP credential decision sit in `entrypoints`, next to the code that already owns them.
- **Proportion:** each task lists signatures, rules and test assertions; no function bodies except where the rule is the spec.
