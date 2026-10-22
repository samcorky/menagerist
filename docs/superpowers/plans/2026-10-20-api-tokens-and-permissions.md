# API tokens, content permissions and data-driven roles: plan

Status: proposal, nothing implemented. Written 2026-10-20 from a design discussion; updated the same day. Facts about the code come from reading `shared_kernel/cqrs.py`, `shared_kernel/actor.py`, `entrypoints/api/shared/{authorization,permissions,dependencies,access_policy,permission_aware_route}.py`, the module `application/permissions.py` files and `tests/architecture/test_permission_catalogue.py`. Not read: the identity routers and the auth port implementation beyond `RoleAuthorizationAdapter`, so route names here are indicative.

What Sam has said (2026-10-20): roles will become data-driven soon, and that roles design does not exist yet; resource-level permissions are wanted later; tokens should be considered with refresh tokens and a client id and secret (answered below: personal access tokens first, OAuth later if third-party apps need it).

Related plans: `access-model-refactor-plan.md` (the foundation for this plan: declared access stances and one guard; it replaces this plan's old Phase 1 rename and shapes Phase 2), `csrf-header-protection-plan.md` ("Future auth methods" is the short version of this; the token-free CSRF design is assumed) and `settings-handoff-plan.md` (public config would expose the enabled sign-in methods).

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
- **OAuth2 authorisation code with PKCE and refresh tokens:** only worthwhile when third-party apps (a mobile app, other tools) act on behalf of users with a consent screen. It needs a client registry, redirect URI validation, a consent page, short access tokens and rotating refresh tokens with reuse detection. That makes Menagerist an OAuth server, which is a different thing from Phase 6, where Menagerist is an OIDC client of an external identity provider. Not now.
- Design so the PAT table does not block that later: the grants model is the same, and a nullable `client_id` can be added when OAuth clients exist. If short-lived credentials are wanted for scripts, a CLI can mint a short-lived token from a PAT.

## Findings that shape the plan

1. Every permission today guards an admin action (identity user management, sessions, backup, system, four graph schema operations). `MEMBER_PERMISSIONS` is empty. Ordinary content is limited only by ownership through `Scoped*` handlers (43 classes; 20 use the `Authorised*` handlers).
2. The permission strings already match the intended format, and `IMPLIES` plus `expand()` already do implication.
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
Done (2026-10-22): see `2026-10-20-access-model-refactor.md` and `specs/2026-10-21-access-model-refactor-design.md`. Every use case declares an `access` stance behind one `AccessGuard`. `Shared` and `Content` carry no permission yet; Phase 2 gives them one, as a one-line change per use case (`Requires(...)`). Names in this plan that predate the refactor (`AccessScope`, `Scoped*Handler`, `AuthorizationPort`) are now `ContentFilter`, `Content`/`Shared` stances and `AuthorisationPort`.

### Phase 2: content permissions
- Add per module, in the existing format: for graph `graph:node:read|write`, `graph:node_type:read|write`, `graph:edge:read|write`, `graph:edge_type:read|write`; for media `media:item:read|write`, etc. `write` implies `read` in `IMPLIES`. Keep the existing admin permissions.
- Content use cases declare `access = Content(<permission>)`; the shared catalogue use cases declare `Requires(...)` or stay open to members per the access plan's Q2.
- Extend `test_permission_catalogue.py` so every use case declares a stance.
- `MEMBER_PERMISSIONS` gains the whole content set (default-granted to all members). Members behave exactly as now.
- Tests: member can still do everything on own content; admin unchanged; removing a permission from the catalogue denies it.
- **Checkpoint Q3:** granularity (per resource as above, or per module like `graph:read|write`?). Finer is easy to split later; coarser is easier to explain.

### Phase 3: roles as data
- **No design exists yet (Sam, 2026-10-20), so this needs its own full plan before any work.** Questions that plan must answer: schema (`roles` table with name and permission set, user to role relation), built-in `admin` and `member` rows seeded by a migration and whether they are editable, one role per user or several, how `is_admin` and `is_system` stop being the authorisation source (they may remain for non-authorisation uses such as the system actor and UI hints), caching of role permissions in `check()` (it becomes a storage read), what happens to unknown permission names in a role row (`check()` already denies unknowns), the admin UI and who can edit roles, protection against removing the last administrator, and migration of existing users.
- Outline only: a `RoleRepository` port with an in-memory sibling; the access guard reads the role's permissions instead of the `MEMBER_PERMISSIONS` constant.
- Tokens (Phase 4) work with the constants for now; Phase 3 can land later without changing token design, because `check()` already intersects "role permissions" with "token grants".

### Phase 4: API tokens (personal access tokens)
- Domain: `ApiToken` entity (id, owner, name, grants, created, last used, expiry optional, revoked); the secret is shown once and stored as a hash; format `mnst_<id>_<secret>` as above.
- `Actor` gains `grants: frozenset[str] | None = None` (`None` = session, no ceiling). `get_current_actor` resolves a bearer token first (if an `Authorization: Bearer` header is present, ignore the cookie entirely), else the session cookie. This is the single place credentials are decided.
- The guard's `check()` becomes: permission in the role's effective permissions AND (`actor.grants is None` or permission in `expand(actor.grants)`).
- `verify_csrf` skips requests authenticated by a bearer token; the cookie is ignored for them (rule in the CSRF plan).
- CORS: add `Authorization` to allowed request headers (the CSRF plan's PR 3 leaves it out until now).
- Session-only: `Public` and `OwnAccount` stances are refused for token actors by the guard. Token management, password change, session and device management declare `OwnAccount`. Admin-only permissions are grantable only through the explicit "Admin" preset; add a `grantable_to_tokens` flag to the catalogue only for permissions that must never be granted.
- Presets for the UI: "Read only" = all grantable `*:read`; "Read and write" = the member content set; "Admin" additionally lists admin permissions and requires the owner to hold them. Advanced view lists individual permissions.
- OpenAPI: add an HTTP bearer security scheme; `PermissionAwareRoute` already mirrors permissions into `x-required-permission`; document the bearer scheme alongside the cookie scheme.
- Endpoints: create (session only; returns the secret once), list (session only), revoke (session only). Revoking and an owner losing a permission both take effect immediately because `check()` reads live role data.
- Tests: token cannot exceed its owner (owner loses permission, token loses it); token without a grant gets 403; a token request to an `OwnAccount` or `Public` use case is refused; a request with both a token and a cookie is authenticated by the token only; hashing and constant-time compare; expiry and revocation; the route-walking test asserts no identity-management use case is token-grantable.
- **Checkpoint Q5:** token lifetime defaults, maximum tokens per user, whether `last used` is updated on every request (write per request) or at most once a minute.

### Phase 5: restricting password sign-in (needed for OIDC-only deployments)
- A `password_login_enabled` setting (deployment config first, instance setting once the settings module exists). When off, the sign-in use case refuses with a dedicated problem type, for example `password_login_disabled`; first-run setup still creates the first administrator.
- Expose enabled sign-in methods in public config (see `settings-handoff-plan.md`, Phase 3) so the SPA shows only methods that exist.
- Break-glass: a Cyclopts CLI command run on the server to issue a one-time admin sign-in or reset a password, so a down identity provider cannot lock everyone out.
- Per-user later: a nullable password hash makes SSO-only accounts possible.
- It cannot restrict by client type (headers are spoofable); the guidance for scripts is tokens, not a ban on session login.

### Phase 6: OIDC (Authorization Code + PKCE, backend-terminated)
- Out of scope for detailed design here. It ends in the same cookie session. Keep `SameSite=Strict` in mind: after the callback land on a same-site page so the SPA's own requests carry the cookie; add a Playwright test against a fake provider. State, nonce and PKCE on the callback are the login-CSRF defence and are separate from the Origin check.

### Later: resource-level access
Sam wants this later. It is prepared by the access refactor (one guard, one policy) and is detailed in that plan's Phase 6: the content filter becomes a predicate, row checks take a resource reference, shares need a table, inheritance rules and share management need a product decision, and per-token resource limits intersect the filter inside the guard.

## Suggested order
Access refactor -> Phase 2 -> (Phase 3 only after its own plan) -> Phase 4 -> Phase 5 -> Phase 6. Phase 4 does not need Phase 3. The CSRF plan (PR 1) is independent and can go first.

## Risks and things to verify before building
- Phase 2 touches most use cases; a missing permission would fail every member for that route. The extended catalogue test and the member-can-do-everything tests are the safety net.
- Confirm what the two `Actor(...)` constructions in identity's dependencies do, and every other place that builds an actor (CLI, background jobs, the system actor) so `grants=None` is correct for them.
- Confirm FastAPI emits a bearer scheme's per-operation scopes if scopes are shown in the OpenAPI document (a generated-schema test); if not, document grants through `x-required-permission` only.
- Data-driven roles make `check()` hit storage, so decide the caching up front (Phase 3 plan).
- A token with no `Origin` and no cookie must pass CSRF only when authenticated by the bearer token. Test the mixed case explicitly.

## Open questions summary
Q3 permission granularity; Q5 token lifetime, limits and `last used` cost. Withdrawn or moved: Q1 rename and Q2 handler shape (now in the access plan); Q4 roles design (does not exist, needs its own plan); Q6 resource-level grants (yes, later).
