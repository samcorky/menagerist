# Devices: spec and plan

**Status:** Proposed. Only the header diagnostics slice (4.7) has been tried; nothing else is implemented.
**Scope:** Let people see and end their own signed-in devices, give administrators a view of every active device, and move administrator screens under `/admin/`.

"Device" is the user-facing word. In code and the API a device is a `Session` (the `sessions` table in the `identity` module). The UI must not say "session"; see `frontend/DESIGN_GUIDELINES.md`.

---

## 1. Background

The `identity` module already has sessions: a row per sign-in holding the user, a token hash, `created_at`, `expires_at` and `last_seen_at`. Sign-in, sign-out, the idle timeout and revocation on password change, password reset and account disable all work. `ChangePassword`, `ResetPassword` and `UpdateUser` (on disable) already call `sessions.delete_for_user`.

What is missing:

- Sessions carry no device information, so two sessions cannot be told apart.
- Nobody can list sessions or end one without ending all of them.
- Administrator screens live under `/settings/*` beside personal settings. There is no `/admin/` area.

## 2. Goals and non-goals

**Goals**

1. A signed-in person sees their active devices and can sign out any other device, or all other devices at once.
2. An administrator sees every active device, can filter by user, and can sign any of them out.
3. An administrator sees a user's devices from the user list.
4. Administrator screens live under `/admin/`.

**Non-goals**

- Fingerprinting (canvas, fonts, hardware) and high-entropy Client Hints such as device model, which would need an `Accept-CH` opt-in.
- Tracking the latest IP address. Only the address at sign-in is kept (a write per request and a privacy cost).
- Geolocation, "new device" notifications, trusted-device lists.
- Renaming devices.
- Revoking tokens other than the session cookie.
- Redirects from old `/settings/users` URLs.

## 3. Decisions

| # | Decision | Reason |
|---|---|---|
| D1 | Record `user_agent` (cut to 256 characters) and `client_ip` once, when the session is created. | No extra writes on the request path. |
| D2 | The API returns the raw user agent plus the Client Hints captured at sign-in. The frontend derives the label ("Firefox on Linux") with `bowser`. | No parsing dependency in the backend image. |
| D11 | Use `bowser` (MIT) for user agent parsing. Do not use `ua-parser-js`: its 2.x releases are AGPL-3.0-or-later, which does not fit Menagerist's Apache 2.0 licence, and its MIT 1.x line is the superseded branch. | Licence compatibility. |
| D12 | Capture the low-entropy Client Hints `Sec-CH-UA-Platform` and `Sec-CH-UA-Mobile` at sign-in, and prefer them over the user agent for the system and phone-or-desktop part of the label. Browsers that send none (Firefox, Safari) fall back to the user agent. | Chromium freezes the user agent's OS details; the hints are the accurate source. They are sent by default over HTTPS and on localhost, so no `Accept-CH` opt-in is needed. |
| D3 | A device is "active" when it is neither expired nor idle (`Session.is_expired` / `is_idle`, using `MENAGERIST_IDENTITY_SESSION_IDLE_HOURS`). | Matches what `GetCurrentUser` accepts. |
| D4 | Responses expose the session row id only. Never the token or its hash. | The row id cannot authenticate (README, "Request log context"). |
| D5 | Ending your own current device through the devices API is refused with 409. Use sign-out. The same applies to administrators ending their own current device. | Sign-out also clears cookies; one path for that. |
| D6 | Ending another person's device as a non-administrator, or an unknown id, is 404. | Existence must not leak ("Access scope"). |
| D7 | Own-device actions need no permission. Admin actions use `identity:session:list` and `identity:session:revoke` (revoke implies list), admin-only. | Follows "Adding an admin-only permission". |
| D8 | One admin list endpoint with an optional `user_id` filter serves both the all-devices page and the per-user view. | One query, one schema. |
| D9 | Administrator screens move to `/admin/*`: `/settings/users` becomes `/admin/users`, and a new `/admin/devices` is added. No redirects. | Requested. |
| D10 | Ending a device by an administrator is logged at `info` with `revoked_by`. | Matches `user unlocked` logging. |

## 4. Backend specification

### 4.1 Domain (`modules/identity/domain/session.py`)

- Add `user_agent`, `client_ip`, `client_platform: str | None` and `client_mobile: bool | None`, all defaulting to `None`, to `Session`.
- `Session.create(..., user_agent=None, client_ip=None, client_platform=None, client_mobile=None)`: cut `user_agent` to `MAX_USER_AGENT_LENGTH = 256` and `client_platform` to 64; blank values become `None`.
- New errors in `domain/errors.py`:
  - `SessionNotFoundError(NotFoundError)`
  - `CurrentSessionError(ConflictError)` for D5

### 4.2 Persistence

- `SessionModel`: add nullable `user_agent`, `client_ip`, `client_platform` and `client_mobile`.
- Migration `t1c2d3e4f5a6_session_device_info.py`, `down_revision = "s0b1c2d3e4f5"`: add the four nullable columns. Existing rows stay `NULL` and display as "Unknown device".
- `SessionRepository` port, SQL and in-memory twin gain:

| Method | Behaviour |
|---|---|
| `get(session_id) -> Session \| None` | By row id. |
| `list_for_user(user_id, *, now) -> list[Session]` | Non-expired, newest `last_seen_at` first. |
| `list_active(*, now, user_id=None) -> list[Session]` | Non-expired, optional user filter, newest first. |
| `delete_all_except(user_id, keep_id) -> int` | Returns the count removed. |

Idle filtering happens in the use case (D3), so repositories stay free of the idle setting. Sessions are not content, so these methods take no `AccessScope`; the architecture rule covers content repositories, and the generated isolation test is checked in 7.3.

### 4.3 Capturing device info

- `start_session(..., user_agent=None, client_ip=None)`.
- `SignInCommand`, `ChangePasswordCommand` and `SetupFirstAdminCommand` gain `user_agent`; `SetupFirstAdminCommand` also gains `client_ip` (the other two have it).
- A `get_client_device(request) -> ClientDevice` dependency next to `get_client_ip`, where `ClientDevice(user_agent, platform, mobile)` is a small frozen dataclass. `platform` is `Sec-CH-UA-Platform` with its quotes removed (`"Linux"` becomes `Linux`); `mobile` is `True` for `?1`, `False` for `?0`, `None` when absent.
- The commands carry `client_ip` and a `device: ClientDevice | None` (replacing the separate `user_agent` field); the request schemas' `to_command(client_ip, device)` pass them through. The values are not added to the ordinary `signed in` line.
- **Header diagnostics (debug only):** see section 4.7.

### 4.4 Use cases (`modules/identity/application/`)

Own devices (plain `CommandHandler` / `QueryHandler`; the actor is the owner):

| Use case | Input | Result |
|---|---|---|
| `ListOwnSessions` (query) | `current_session_id` | Active sessions of `actor.id`, each marked `current`. |
| `RevokeOwnSession` (command) | `session_id`, `current_session_id` | Ends it. 404 if not the actor's (D6), 409 if current (D5). |
| `RevokeOtherSessions` (command) | `current_session_id` | Ends all the actor's other sessions; returns the count. |

Administrator (Authorised handlers):

| Use case | Permission | Behaviour |
|---|---|---|
| `ListSessions` (query) | `identity:session:list` | Active sessions with the owner's username and display name; optional `user_id`. |
| `RevokeSession` (command) | `identity:session:revoke` | Ends any session by id. 404 if unknown, 409 if it is the actor's current one. |

`ListSessions` returns a `SessionListing(session, username, display_name)` value object (like `UserListing`). Commands log `info` after commit.

### 4.5 Permissions

- `IdentityPermission.LIST_SESSIONS = "identity:session:list"` and `REVOKE_SESSION = "identity:session:revoke"`.
- `IMPLIES[REVOKE_SESSION] = {LIST_SESSIONS}`.
- Both stay out of `MEMBER_PERMISSIONS`.

### 4.6 API

All routes use `PermissionAwareRoute` and declare their error responses.

| Route | operation_id | Notes |
|---|---|---|
| `GET /auth/sessions` | `list_own_sessions` | Active devices; `current` flag. |
| `DELETE /auth/sessions/{session_id}` | `revoke_own_session` | 204; 404; 409. |
| `DELETE /auth/sessions` | `revoke_other_sessions` | 200 with `{ended: int}`. |
| `GET /session?user_id=` | `list_sessions` | Admin. |
| `DELETE /session/{session_id}` | `revoke_session` | Admin; 204. |

`SessionResponse`: `id`, `user_agent`, `client_platform`, `client_mobile`, `client_ip`, `created_at`, `last_seen_at`, `expires_at`, `current`. `AdminSessionResponse` adds `user_id`, `username`, `display_name`. The own-device routes use `get_active_identity_actor`. The current session id comes from a `get_current_session_id` dependency reading `request.state.session_id`, set by `bind_session_context`.

New `session_router.py` is registered in `entrypoints/api/__init__.py` beside `user_router`. Regenerate the client with `poe generate-frontend-client`.

### 4.7 Header diagnostics (first slice)

Show what the app actually receives on sign-in after the reverse proxy, so we can check that the user agent, Client Hints and client address survive before relying on them. This slice is independent of the rest and ships first. **Status:** verified on a live deployment: Windows and Android Chrome requests showed the user agent, `Sec-CH-UA-Platform` and `Sec-CH-UA-Mobile` intact, `X-Forwarded-Proto: https`, and the correct public client address through the proxy.

On `POST /api/v1/auth/login`, after the body validates and before the use case runs, log one event:

- Logger: structlog, in `auth_router.py`. Level `debug`, so silent unless `MENAGERIST_LOG_LEVEL=DEBUG`; no new setting. Event `sign_in_device_headers`.
- Fields: `user_agent` (cut to 256), `sec_ch_ua`, `sec_ch_ua_mobile`, `sec_ch_ua_platform`, `x_forwarded_for`, `x_forwarded_proto`, `forwarded`, and `client_ip` (from `get_client_ip`, after trusted-proxy handling). An absent header is logged as `None`. The username is not logged.
- **Allowlist only.** Built from the fields above, never by iterating `request.headers`, so `Cookie`, `Authorization`, `X-CSRF-Token` and `Set-Cookie` cannot appear. Values are cut to 256 characters and control characters escaped, so a hostile header cannot forge log lines. Logged once, before authentication, with no effect on the response.
- Implementation: a pure `device_header_fields(headers, client_ip) -> dict[str, str | None]` in `modules/identity/adapters/api/`, called from the `sign_in` route. No domain, application, port, schema, migration or API changes.
- Amend `backend/README.md` ("Access log": headers are never logged) to name this single allowlisted debug exception.
- Tests: exactly the allowlisted keys with `None` for absent headers; truncation and escaping; a login carrying `Cookie` and `X-CSRF-Token` logs neither secret; nothing is emitted at the default level.

## 5. Frontend specification

All Svelte work goes through the `svelte-file-editor` subagent.

### 5.1 Admin area (D9)

- Move `routes/settings/users/` to `routes/admin/users/`.
- New `routes/admin/devices/+page.svelte`.
- New `routes/admin/+page.svelte` index listing Users and Devices, shown only to those holding the relevant permissions (same card style as the settings index).
- Update every reference to `/settings/users`: `settings/+page.svelte` (remove the Users card, add one "Administration" card to `/admin` for administrators), `user-menu.svelte`, `tests/auth.test.ts`, and the e2e specs (`identity`, `auth`, `users.mobile`, `isolation`). No redirects.
- Guard: a non-administrator reaching `/admin/*` is handled the way `/settings/users` is today (the page checks `auth.can(...)`; the API enforces regardless). Confirm against `guardDecision` in `src/lib/auth.ts`.

### 5.2 Own devices

- "Devices" section on `settings/account`: one row per device with label, address, last active (relative), and a "Sign out" button; the current device is marked "This device" and has no button. "Sign out all other devices" with a confirmation dialog.

### 5.3 Administrator devices

- `/admin/devices`: table (stacked cards on mobile) with person, device, address, signed in, last active, and "Sign out" gated on `auth.can('identity:session:revoke')`. A filter by person.
- `/admin/users`: a "Devices" action per user opening a dialog that lists that user's devices (`user_id` filter) with per-device "Sign out". The existing reset and disable flows get a line of help text that they also sign the person out everywhere.

### 5.4 Helpers

- Add `bowser` (MIT) to `frontend` dependencies. Check `.github/renovate.json` (weekly, grouped non-major) and the built bundle size before merging; import only `Bowser.parse`.
- `src/lib/devices.ts`: `describeDevice({ userAgent, platform, mobile }): string`. Browser name comes from `bowser`. The system comes from `platform` when present, else from `bowser`'s OS; `mobile === true` with no recognisable system shows "{browser} on a phone". Fallback "Unknown device". Plus a relative-time formatter if none exists. Pure, unit-tested in `tests/devices.test.ts`.
- `describeDevice` also returns a `kind` (`tool`, `phone`, `tablet`, `desktop` or `unknown`), used by a shared `device-icon.svelte` to pick a Lucide icon (`Terminal`, `Smartphone`, `Tablet`, `Monitor`, a question-mark circle). Order: command-line client, then phone (`mobile` hint true, iPhone, or Android with a `Mobile` token), then tablet (iPad, or Android with `mobile` false and no `Mobile` token), then desktop (Windows, macOS, Linux, ChromeOS), else unknown. The icon is decorative; the text label carries the meaning. Laptop and desktop share one icon, and iPadOS Safari reports as a Mac.
- Copy: British English; "devices", never "sessions".

## 6. Work plan

| Step | Work | Done when |
|---|---|---|
| 1 | Domain fields, errors, migration, ORM, SQL and in-memory repos | Domain and repository tests pass |
| 2 | Capture device info in sign-in, change-password, setup | Router tests show user agent and address stored |
| 3 | Own-device use cases | Application tests, 100% coverage |
| 4 | Permissions and admin use cases | Catalogue test passes |
| 5 | Routers, schemas, wiring, OpenAPI | Router tests; client regenerated |
| 6 | Frontend: move to `/admin/`, update references, add `bowser` | `poe lint-frontend`, typecheck, unit tests pass |
| 7 | Frontend: account devices, admin devices, per-user dialog, helper | Vitest and e2e pass |
| 8 | Docs | README Identity section, `docs/DECISIONS.md` entry |
| 9 | Full checks | `poe check-changed`, `poe coverage` |

Steps 1 to 5 are the backend and can ship before the frontend. Nothing is committed by me; each step is left for review.

## 7. Test plan

### 7.1 Backend

- **Domain:** `Session.create` stores and truncates `user_agent`, blank becomes `None`.
- **Application:** each use case's happy path and 404, 409 and 403 paths; `delete_all_except` keeps the current device; idle and expired sessions are excluded from lists; reset and disable end the user's devices (existing behaviour, new assertions).
- **Two users:** user A cannot list, see or end user B's device (404).
- **Secret hygiene:** extend `test_secret_hygiene.py`: no token or hash in responses, reprs or log output; `user_agent` not logged.
- **Header diagnostics:** a sign-in carrying `Cookie` and `X-CSRF-Token` headers logs the allowlisted headers and neither secret, and logs nothing above `debug`.
- **Router:** each route with `real_actor` where the session lookup matters; CSRF applies to the `DELETE` routes.
- **SQL (integration):** repository round trips and the migration on Postgres.
- **Architecture:** `test_permission_catalogue.py` covers the new permissions.

### 7.2 Frontend

- Vitest: `describeDevice` against common user agents, with and without Client Hints, and `null`.
- Playwright: account page lists and ends a device; admin devices page; per-user dialog; mobile layout; a member cannot see the admin area.

### 7.3 To confirm while implementing

- `tests/entrypoints/test_cross_user_isolation.py` generates cases from the routes. Add the five new routes to its `ALLOWED` map with one-line reasons (the own-device routes act on the actor's own sessions; the admin routes are permission-gated), or the meta test fails.

## 8. Risks

- **Move of `/settings/users`:** bookmarks break by design (no redirects). All in-repo references are listed in 5.1; a grep for `settings/users` must come back empty.
- **Client Hints coverage:** only Chromium browsers send them, and only over HTTPS or on localhost. Elsewhere the label comes from the user agent alone. A proxy that strips `Sec-CH-*` headers has the same effect.
- **Reverse proxies:** `client_ip` is only meaningful with `MENAGERIST_API_TRUSTED_PROXIES` set correctly; the UI should treat it as informational.
- **Old sessions:** pre-existing rows have no device info and show "Unknown device" until they expire.
- **Lock-out:** D5 stops administrators ending their own current device by accident; they can still end their other devices.
