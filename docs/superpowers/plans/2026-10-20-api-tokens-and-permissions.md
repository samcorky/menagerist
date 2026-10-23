# API tokens, content permissions and data-driven roles: plan

Status: Phases 1 and 2 done (2026-10-22); Phase 4 has its task plan (`2026-10-23-api-tokens.md`) and is the next build, Phase 3 needs its own plan, Phases 5 and 6 need separate plans. Written 2026-10-20 from a design discussion; updated 2026-10-22. Facts about the code come from reading `shared_kernel/cqrs.py`, `shared_kernel/actor.py`, `entrypoints/api/shared/{authorization,permissions,dependencies,access_policy,permission_aware_route}.py`, the module `application/permissions.py` files and `tests/architecture/test_permission_catalogue.py`. Not read: the identity routers and the auth port implementation beyond `RoleAuthorizationAdapter`, so route names here are indicative.

What Sam has said (2026-10-20): roles will become data-driven soon, and that roles design does not exist yet; resource-level permissions are wanted later; tokens should be considered with refresh tokens and a client id and secret (answered below: personal access tokens first, OAuth later if third-party apps need it).

Related plans: `2026-10-20-access-model-refactor.md` (the foundation: declared access stances and one guard), `2026-10-22-content-permissions.md` (Phase 2, implemented: content permissions as enums with `implied()`) and `2026-10-20-csrf-origin-protection.md` (the token-free CSRF design is assumed).

Working rules (from `AGENTS.md` / `CLAUDE.md`): never create, stage or push commits (ask Sam to commit); British English; `.svelte` and `.svelte.ts` files go through the `svelte-file-editor` subagent; run only the relevant `poe` checks for touched code; coverage floors (domain, application, shared_kernel 100%, adapters 80%, platform 70%); every port ships an in-memory sibling; domain errors subclass `shared_kernel.errors`; no try/except in routers; the clone is read-only here, so deliver complete files for Sam to commit.

## Goal

Let people create API tokens that act as them with fewer rights than their browser session, keep sign-in and account management session-only, and prepare for roles stored as data and resource-level access. One authorisation vocabulary, enforced in the application layer like today.

## Terms used here (keep them distinct)

| Term | Meaning | Where it lives |
|---|---|---|
| Role | A named set of permissions given to a user. Today `admin` or member; becomes data. | user; later a roles table |
| Permission | An action the system defines, `<module>:<resource>:<action>`, checked by the access guard in a use case | `modules/*/application/permissions.py` |
| Grants (token scopes) | The ceiling a token carries: a subset of permissions. Never adds rights. | the token |
| Content filter (today `AccessScope`) | Which rows an actor may see, decided by the policy (today owner-only) | `shared_kernel/access_scope.py` |
| Access stance | A use case's declared rule: `Public`, `OwnAccount`, `Requires(permission)`, `Content(permission)` | the use case class (see the access plan) |

Effective rights of a token request = permissions the owner's roles give **AND** permissions the token grants. Session requests have no ceiling.

In the UI and API docs, say "scopes" (industry word); in code, say `grants`, because `Scoped*Handler` and `AccessScope` currently mean something else (the access plan renames them).

## Token flavours (answer to "refresh tokens, client id and secret?")

- **Personal access token (PAT), recommended now.** The user creates it in the UI, picks grants and an optional expiry, and can revoke it. Format `mnst_<id>_<secret>`: the `id` part is a public lookup key (this is the "client id" role), the `secret` part is stored only as a hash (the "client secret" role) and compared in constant time. The prefix helps secret scanners. No refresh token is needed: revocation and expiry do the job.
- **OAuth2 client credentials (client id and secret exchanged for a short-lived access token):** for service accounts and integrations with no user. For a single-instance self-hosted app the secret is as sensitive as a PAT, so it adds a token endpoint and expiry handling for little gain. Not now.
- **OAuth2 authorisation code with PKCE and refresh tokens:** only worthwhile when third-party apps (a mobile app, other tools) act on behalf of users with a consent screen. It needs a client registry, redirect URI validation, a consent page, short access tokens and rotating refresh tokens with reuse detection. That makes Menagerist an OAuth server, which is a different thing from OIDC sign-in (see "Separate plans needed"), where Menagerist is an OIDC client of an external identity provider. Not now.
- Design so the PAT table does not block that later: the grants model is the same, and a nullable `client_id` can be added when OAuth clients exist. If short-lived credentials are wanted for scripts, a CLI can mint a short-lived token from a PAT.

## Findings that shape the plan

1. (Before Phase 2) every permission guarded an admin action and `MEMBER_PERMISSIONS` was empty. Now there are 30 permissions: 16 admin and 14 member content permissions, and `MEMBER_PERMISSIONS` is the content set. Ownership is still the row-level rule, held by `AccessGuard`.
2. The permission strings match the intended format, and each enum's `implied()` method (on `PermissionEnum`) does implication; a write or install permission implies its read counterpart.
3. `check()` denies any permission outside the catalogue, for everyone. That gives deny-by-default once permissions are declared.
4. `Actor` is built in `get_current_actor` and in identity's dependencies (lines ~418 and ~431 of `modules/identity/adapters/api/dependencies.py`: confirm what each is for) and is the only thing a use case sees. It currently holds `id` and `roles`.
5. `PermissionAwareRoute` only documents (adds the cookie `Security` scheme and `x-required-permission`); it does not enforce. `api_v1_router` already carries `Security(cookie_scheme)` for every route.
6. `tests/architecture/test_permission_catalogue.py` already walks every use case and checks declared permissions against the catalogue. It is the model for the new guard tests.
7. Rejected: coarse method-based scopes (`read`/`write`/`admin`) enforced by a router guard. It creates a second authorisation mechanism in `entrypoints`, cannot express custom roles, and needs GET to be side-effect free.
8. Rejected: scopes through FastAPI `Security(..., scopes=...)` in endpoint signatures. FastAPI caches dependencies per `(call, scopes)`, so a router-level scope and an endpoint-level `Depends` are separate calls; easy to get wrong.
9. Session-only comes from the access stances: `Public` and `OwnAccount` are never granted to tokens, so no router guard or per-route marker is needed.

## Decisions to confirm

- **D1** (recommended): permissions are the single primitive; token grants and roles are both sets of permissions. Needs Sam's confirmation.
- **D2:** do the access model refactor (`access-model-refactor-plan.md`) before content permissions and tokens.
- **D3:** staged delivery, below.

## Phases (each shippable on its own; stop at the checkpoints)

### Phase 1: access model refactor
Done (2026-10-22): see `2026-10-20-access-model-refactor.md` and `specs/2026-10-21-access-model-refactor-design.md`. Every use case declares an `access` stance behind one `AccessGuard`. `Shared` and `Content` carried no permission at that point; Phase 2 (done) gave every one of them a permission. Names in this plan that predate the refactor (`AccessScope`, `Scoped*Handler`, `AuthorizationPort`) are now `ContentFilter`, `Content`/`Shared` stances and `AuthorisationPort`.

### Phase 2: content permissions
Done (2026-10-22): see `2026-10-22-content-permissions.md` and the decision entry in `docs/DECISIONS.md`. Permissions are enums deriving `PermissionEnum`, which owns `implied()` (the per-module `IMPLIES` dicts are gone). `Content(permission)` and `Requires(permission)` carry a permission; `Shared` is removed. 14 member permissions were added (`graph:item:read|write`, `graph:type:read|write`, `media:item:read|write`, `collections:collection:read|write`, `presets:preset:read|write`, `examples:pack:read|install`, `backup:own_data:export|import`) and `MEMBER_PERMISSIONS` is that set, so members behave exactly as before. Q3 was settled as coarse-first with item/type vocabulary. Pins: `test_permission_mapping.py` (use case to permission, the catalogue of 30, every non-admin permission is a member permission) and `test_no_direct_ownership_checks.py`.

### Phase 3: roles as data
- **No design exists yet (Sam, 2026-10-20), so this needs its own full plan before any work.** Questions that plan must answer: schema (`roles` table with name and permission set, user to role relation), built-in `admin` and `member` rows seeded by a migration and whether they are editable, one role per user or several, how `is_admin` and `is_system` stop being the authorisation source (they may remain for non-authorisation uses such as the system actor and UI hints), caching of role permissions in `check()` (it becomes a storage read), what happens to unknown permission names in a role row (`check()` already denies unknowns), the admin UI and who can edit roles, protection against removing the last administrator, and migration of existing users.
- Outline only: a `RoleRepository` port with an in-memory sibling; the access guard reads the role's permissions instead of the `MEMBER_PERMISSIONS` constant.
- Tokens (Phase 4) work with the constants for now; Phase 3 can land later without changing token design, because `check()` already intersects "role permissions" with "token grants".

### Phase 4: API tokens (personal access tokens)
Review decisions (2026-10-22). The task plan is `2026-10-23-api-tokens.md` (rulings R1 to R12 settle Q5 and refine the sketch below; where they differ, the task plan wins).

**Why personal access tokens, not OAuth.** A PAT is a user issuing a credential to themselves: a stored hash, a name, the permissions granted and a mandatory expiry. OAuth is delegation to third-party apps and needs an authorisation server, a consent screen, PKCE, refresh tokens and client registration, which is overkill for a self-hosted tool. The permission strings can double as OAuth scopes later. Token verification should sit behind one function that returns an actor plus permissions, so an OAuth access token could become a second Bearer format without touching the guard.

**Model**
- Domain: `ApiToken` entity (id, owner, name, grants, created, last used, expiry, revoked). Format `mnst_<id>_<secret>`. The secret is shown once and stored as SHA-256, compared in constant time.
- `Actor` gains `grants: frozenset[str] | None = None` (`None` = session, no ceiling). `get_current_actor` is the single place credentials are decided.
- The guard's `check()` becomes: permission in the role's effective permissions AND (`actor.grants is None` or permission in the expanded grants). Effective rights are the intersection, so a token never exceeds its owner.
- Session-only: `Public` and `OwnAccount` stances are refused for token actors. Token management, password change, session and device management declare `OwnAccount`.

**Grants**
- Grantability is opt-in: the catalogue gets `token_grantable`, defaulting to false. v1 grants only content permissions; there is no Admin preset.
- Grants are validated against the owner's current permissions at creation.
- UI presets: "Read only" (all grantable `*:read`) and "Read and write" (the member content set), plus an advanced view of individual permissions.
- The token UI shows human labels (Items, Item types, Collections, Media, Presets), never `graph:*` strings, per `frontend/DESIGN_GUIDELINES.md`.

**Creation and lifetime**
- Creating a token requires the password again.
- Expiry is mandatory, with a maximum.
- Endpoints (all session only): create (returns the secret once), list, revoke. Revoking, locking or deactivating the user, or the owner losing a permission, takes effect at once because `check()` reads live data.
- **Checkpoint Q5:** default and maximum lifetime, maximum tokens per user, and whether `last used` is written on every request or at most once a minute.

**Authentication behaviour**
- An `Authorization: Bearer` header is authoritative: an invalid or expired bearer is a 401 and never falls back to the cookie.
- `verify_csrf` skips requests authenticated by a bearer token; the cookie is ignored for them.
- Never log the `Authorization` header. Log the token id on create, use and revoke.
- CORS: add `Authorization` to the allowed request headers only if a cross-origin browser client exists.
- An architecture test keeps `actor.is_admin` out of everything except the authorisation adapter, so a token cannot inherit admin rights by a side door.

**Swagger and `PermissionAwareRoute`**
- Define a bearer scheme, `HTTPBearer(auto_error=False)`, beside `cookie_scheme`.
- Replace the router-wide `Security(cookie_scheme)` with a per-route choice made in `PermissionAwareRoute`: `Requires` and `Content` accept cookie or bearer, `OwnAccount` is cookie only, `Public` has none. A generated-schema test checks that FastAPI emits cookie and bearer as alternatives.
- An HTTP bearer scheme has no OAuth scopes, so grants are documented through `x-required-permission` only (already emitted for `Requires` and `Content`).
- Show the Authorize button for the bearer scheme only. Today `.auth-wrapper` is hidden in `swagger.html` and `swagger.spec.ts` asserts that, so both change. Keep `persistAuthorization: false`.
- `cookieSchemes()` in `swagger-init.js` already ignores `http` schemes, so the session lock logic is untouched. Make sure `prepareRequest` never strips `Authorization`.
- Document "Using a token" in `api-description.md` (mind the single `$` placeholder test).
- `GET /auth/me/permissions` returns the intersection for a token actor.
- Add a Playwright test that authorises a token in Swagger and calls a content route.

**Tests**
- A token cannot exceed its owner (owner loses a permission, token loses it); a token without a grant gets 403; a token request to an `OwnAccount` or `Public` use case is refused; a request with both a token and a cookie is authenticated by the token only; a bad bearer with a valid cookie is 401; hashing and constant-time compare; expiry and revocation; lock or deactivation stops tokens; the route-walking test asserts no admin permission is token-grantable.

Sharing and resource-level access build on this phase: see "Later: sharing and resource-level access" below.

### Later: sharing and resource-level access
Sam wants this later (2026-10-22 discussion). It needs its own plan; this records how it fits so that plan starts from here.

**Two layers stay separate.** Capability (a permission held by the role and granted by the token, checked by `AccessGuard.check`) and resource access (which rows, at what level, decided by the content filter and `assert_can_*`). Sharing changes only the second. Reading a shared collection still needs `collections:collection:read`; editing it still needs `collections:collection:write`. The full rule: permission held by the role AND granted by the token AND (owner OR a share at the required level) AND within any per-token resource limit.

**What it adds**
- A share table storing a level, not permissions: `(resource_type, resource_id, grantee_id, level)` with levels `view` and `edit`. The guard maps action to level (read needs `view`, write needs `edit`; delete and re-share stay owner-only), so there is no second permission vocabulary.
- `ContentFilter` becomes a predicate ("owner is me, or a share reaches me"); repositories translate it to SQL with a join on shares. `scope()` and `ContentFilter` are the seam the access refactor built.
- Guard row checks take a resource reference (type, id, owner) instead of `owner_id`.
- A separate `collections:collection:share` permission, kept out of any read or read-and-write token preset, because sharing gives your data to another account.

**Product decisions the plan must settle:** whether sharing a collection exposes its items and media (leaning yes) and connections (only when both ends are visible); how smart collections resolve (under the owner's visibility, shown to the sharee); view-only sharing first, since a sharee adding their own items to your collection raises ownership questions; hidden content keeps returning 404, not 403; "anyone with the link" is a different mechanism (an unguessable capability, closer to `Public`) and a separate plan; a sharee picker needs a member-usable user lookup, not admin `ListUsers`.

**Interactions:** tokens act as their owner and inherit shares for free; a per-token collection allow-list is one more intersection inside the guard; data-driven roles stay consistent (removing `collections:collection:write` from a role also stops it editing shared collections).

**Guard-rail now:** `tests/architecture/test_no_direct_ownership_checks.py` (added in the content permissions plan, Task 6) keeps ownership comparisons inside the guard so sharing has one place to change.

## Separate plans needed
These were Phases 5 and 6 of this plan. Each needs its own plan before work; neither blocks Phase 4.

### Restricting password sign-in (needed for OIDC-only deployments)
- A `password_login_enabled` setting (deployment config first, instance setting once the settings module exists). When off, the sign-in use case refuses with a dedicated problem type, for example `password_login_disabled`; first-run setup still creates the first administrator.
- Expose enabled sign-in methods in public config so the SPA shows only methods that exist.
- Break-glass: a Cyclopts CLI command run on the server to issue a one-time admin sign-in or reset a password, so a down identity provider cannot lock everyone out.
- Per-user later: a nullable password hash makes SSO-only accounts possible.
- It cannot restrict by client type (headers are spoofable); the guidance for scripts is tokens, not a ban on session login.

### OIDC (Authorization Code + PKCE, backend-terminated)
- Out of scope for detailed design here. It ends in the same cookie session. Keep `SameSite=Strict` in mind: after the callback land on a same-site page so the SPA's own requests carry the cookie; add a Playwright test against a fake provider. State, nonce and PKCE on the callback are the login-CSRF defence and are separate from the Origin check.

## Suggested order
Access refactor and Phase 2 (both done), then Phase 4. Phase 3 only after its own plan. Phase 4 does not need Phase 3. The CSRF plan is independent.

## Risks and things to verify before building
- Confirm what the two `Actor(...)` constructions in identity's dependencies do, and every other place that builds an actor (CLI, background jobs, the system actor) so `grants=None` is correct for them.
- Composite use cases call other use cases, and the inner calls hit the guard with the same actor, so a token needs every inner permission. Found in Phase 2: `media.UploadAndAttachMedia` (`media:item:write`) wraps `StageMedia` and `AttachMedia` (both `media:item:write`); `graph.PromoteExtraSchemaField` (`Content` `graph:type:write`) wraps `UpdateNodeType` (`Requires` `graph:type:write`) and `UpdateNode` (`Content` `graph:item:write`), so a token holding only `graph:type:write` would not cover its inner `UpdateNode`; `backup.ImportUserArchive` wraps `ImportUserData` (both `backup:own_data:import`). Decide for each whether the outer permission should imply the inner or the composite should declare both, and add a test that walks composites.
- `examples/application/install_example_pack.py` is allow-listed in `test_no_direct_ownership_checks.py` until sharing lands; tokens inherit that gap.
- Data-driven roles make `check()` hit storage, so decide the caching up front (Phase 3 plan).
- A token with no `Origin` and no cookie must pass CSRF only when authenticated by the bearer token. Test the mixed case explicitly.

## Open questions summary
Q5 token lifetime, limits and `last used` cost. Settled: Q3 granularity (Phase 2). Withdrawn or moved: Q1 rename and Q2 handler shape (now in the access plan); Q4 roles design (does not exist, needs its own plan); Q6 resource-level grants (yes, later).
