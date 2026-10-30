# Passkeys: opt-in sign-in without a password

**Status:** Draft for review. Nothing is implemented.
**Scope:** Let a person add passkeys to their account and sign in with one instead of typing a password. The password stays; a passkey is a second way in, not a replacement.

"Passkey" is the user-facing word and appears in the UI as is. In code it is a WebAuthn credential.

Prompted by aft's v2026.10.1, which ships passkeys off by default and turns them on only when a domain is configured. The idea fits Menagerist because the `identity` module already has the pieces a new credential type plugs into: sessions, sign-in throttling, device details, scoped API tokens and the access stances.

---

## 1. Background (verified in code)

- `SignIn` (`application/sign_in.py`) is `Public`. It reserves throttle counters, calls the `Authenticator` port with `PasswordCredentials`, then `start_session(...)` stores the session and returns the secret token. The cookie is set in `auth_router.py`.
- `Authenticator.authenticate` is password-shaped: `PasswordCredentials` in, `VerifiedIdentity` out, with `credential_hash` so a later step refuses if the password changed meanwhile. A passkey cannot reuse it unchanged.
- Throttling is keyed on a SHA-256 of the lower-cased username and of the client address (`sign_in_throttle.py`), in the `sign_in_attempts` table, so it works across several workers.
- Several server workers can run (`MENAGERIST_SERVER_WORKERS`), so nothing that must survive between two requests may live in process memory.
- State-changing browser requests are checked by `verify_csrf` (Fetch Metadata and `Origin`); public sign-in routes use `refuse_cross_site`.
- Over HTTPS the session cookie is `__Host-Http-menagerist-session`, `SameSite=Strict`.
- `GET /api/v1/auth/status` already tells the login page whether the instance is set up; a `passkeys` flag can join it.
- Creating an API token asks for the person's password (README, API tokens). The same re-check suits adding a passkey.
- The registry has no WebAuthn library. `cryptography` is already in the lock file transitively.

## 2. Goals and non-goals

**Goals**

1. A signed-in person adds, names, renames and removes their own passkeys under Settings > Account.
2. The sign-in page offers "Sign in with a passkey" when the instance has passkeys enabled. No username is typed (discoverable credentials).
3. A passkey sign-in starts the same kind of session as a password sign-in, so devices, revocation, idle timeout and permissions behave identically.
4. Off by default. An operator turns it on by setting the relying-party domain, because a passkey is bound to a domain and needs a browser-trusted HTTPS origin (`localhost` also works).
5. An administrator can see how many passkeys a person has and remove them (for a lost device).

**Non-goals**

- Replacing passwords, or accounts with no password. A password always exists in v1.
- Passkeys for API tokens or the CLI. Tokens stay the way scripts authenticate.
- Making a passkey count as a second factor on top of a password (no two-step sign-in). Passkeys here are a complete sign-in by themselves.
- Attestation checking or restricting authenticator makes. Registration uses attestation `none`.
- A "trust this device" feature or step-up prompts for sensitive actions.

## 3. Design

### 3.1 Settings

**One public address, with derived defaults.** There is no app-address setting today: `cors_origins`, `cookie_secure` (auto-detected) and the CSRF `Origin` comparison (taken from the request after the proxy wrapper) each work it out separately. Add one value to `ApiSettings`:

- `public_origin: Origin | None = None` (`MENAGERIST_API_PUBLIC_ORIGIN`, for example `https://menagerist.example.com`). It reuses the existing `Origin` type in `platform/config/_types.py`, which already normalises to `scheme://host[:port]`, drops default ports and rejects a path, query or user. It is an origin, not a URL, because serving under a sub-path is not supported.
- `platform/config/public_origin.py` holds pure resolver functions, not cross-settings validators: `public_host(api) -> str | None` and `public_is_https(api) -> bool | None`. Settings groups stay independent classes; each consumer asks the resolver at the point of use. Precedence is always: the setting's own explicit value, then the value derived from `public_origin`, then today's behaviour. Start-up logs which one applied.

Derived defaults in this slice:

| Setting | Explicit value wins; otherwise |
| --- | --- |
| `identity.webauthn_rp_id` | the host of `public_origin` |
| `identity.webauthn_origins` | `[public_origin]` |
| `identity.cookie_secure` (existing; now `auto`, `origin`, `always` or `never`) | nothing implicit: `origin` follows the scheme of `public_origin`, and refuses to start without one. Default stays `auto`. |

Not derived: `api.cors_origins` (the app is same-origin with its API, so widening CORS would add trust for nothing) and the CSRF check (it keeps comparing against the origin the server sees; a mismatch with `public_origin` is a candidate warning for the existing proxy-configuration check, not a rule change).

On `IdentitySettings` (`MENAGERIST_IDENTITY_` prefix):

| Setting | Default | Meaning |
| --- | --- | --- |
| `webauthn_rp_id` | derived from `public_origin`, else unset | The relying-party ID: the site's domain. **Unset after derivation means passkeys are off.** |
| `webauthn_rp_name` | `Menagerist` | Name the authenticator shows. |
| `webauthn_origins` | `[public_origin]` | Origins allowed to use the ID, as a comma-separated list like `cors_origins` (use `StarOrCSV`-style `CSV[Origin]`, no `*`). |
| `passkeys_per_user` | `10` | Most passkeys one person may register (1 to 50). |

So the operator normally sets one variable, `MENAGERIST_API_PUBLIC_ORIGIN`, and passkeys turn on. A model validator on the resolved values requires every origin to be `https://` (or `http://localhost`) and its host to equal the ID or end in `.<id>`, and refuses `webauthn_origins` without an ID. A wrong shape stops start-up with a message naming the variable. These are fixed settings, not runtime-tunable: changing the ID invalidates every registered passkey, which must not happen by accident.

### 3.2 Domain and persistence

- `Passkey` entity in `identity/domain/passkey.py`: `id` (uuid7), `user_id`, `credential_id` (bytes, unique), `public_key` (bytes, COSE), `sign_count`, `transports`, `backed_up`, `name`, `created_at`, `last_used_at`. `kw_only=True, eq=False`; timestamps set in domain methods.
- `PasskeyRepository` port with in-memory twin and SQL adapter; Alembic migration for a `passkeys` table (`user_id` foreign key, delete cascades with the user).
- `WebAuthnChallenge`: a short-lived row (`id`, `purpose` registration or sign-in, `user_id` or null, `challenge`, `expires_at`). Stored in the database, not memory, because requests may reach different workers. Single use: deleting it is part of verifying. Five-minute lifetime. The existing purge job (`purge_expired_credentials`) removes expired rows.
- `WebAuthnVerifier` port: `registration_options`, `verify_registration`, `authentication_options`, `verify_authentication`. The adapter wraps the chosen library; an in-memory twin accepts credentials built by a software authenticator helper in tests.

The `WebAuthnVerifier` port exchanges plain frozen dataclasses (`RegistrationChallenge`, `VerifiedRegistration`, `VerifiedAssertion`) holding bytes and ints, never library types, and raises a domain `InvalidPasskeyError`; the adapter converts every library exception into it, so a bad assertion cannot become a 500.

### 3.3 Use cases and access

| Use case | Stance | Notes |
| --- | --- | --- |
| `BeginPasskeyRegistration` | `OwnAccount` | Needs the current password. Excludes the person's existing credential IDs. |
| `FinishPasskeyRegistration` | `OwnAccount` | Consumes the challenge, stores the passkey. Refuses a duplicate credential ID. |
| `ListOwnPasskeys` | `OwnAccount` | |
| `RenameOwnPasskey` / `RevokeOwnPasskey` | `OwnAccount` | Only the person's own. |
| `BeginPasskeySignIn` | `Public` | Usernameless: `allowCredentials` empty, user verification required. Creates a challenge row. |
| `FinishPasskeySignIn` | `Public` | Verifies the assertion, finds the passkey by credential ID, checks the user handle, bumps `sign_count`, refuses a disabled account, then `start_session(...)`. |
| `AdminRevokePasskeys` | `Requires(...)` | New permission under the users area; removes all of a person's passkeys. |

`OwnAccount` already refuses token actors, so an API token cannot manage passkeys. The new `Public` and `Requires` use cases are added to the pins in `tests/architecture/test_access_stances.py` and `test_permission_mapping.py`.

### 3.4 Sign-in rules

- **Usernameless.** Users are identified by the credential, so there is no username lookup and no existence oracle. The user handle stored in the credential is the user's id; the server confirms it matches the passkey's owner.
- **User verification required.** The authenticator proves the person (PIN, biometric), so a passkey is genuinely something-you-have plus something-you-are or know.
- **Throttling.** Failed assertions and refused challenges count against the client address through the existing `ip_key` counters and limits, with the same 429 and `Retry-After`. Begin requests are also counted, so a flood of challenge rows cannot fill the table.
- **Disabled accounts** get `AccountDisabledError` as with passwords, and a failed attempt is not counted for them.
- **Sign count.** A non-zero count that does not increase is logged and refused (a cloned authenticator). Synced passkeys often report zero, which is accepted.
- **Session.** `start_session` is reused unchanged; the device details and address are captured the same way.

### 3.5 API

All under `/api/v1/auth/` with operation IDs in the generated client:

- `POST /passkeys/registration/options`, `POST /passkeys/registration` (signed in; password in the first body).
- `GET /passkeys`, `PATCH /passkeys/{id}`, `DELETE /passkeys/{id}` (signed in).
- `POST /passkeys/sign-in/options`, `POST /passkeys/sign-in` (public, `refuse_cross_site`).
- `DELETE /users/{id}/passkeys` (administrator).
- `GET /status` gains `passkeys: bool`.

**Wire format.** The envelope (`challenge_id`, `name`, `created_at`, ...) is snake_case like every other endpoint. The browser's own objects (`credential`, `options`) keep the WebAuthn standard's camelCase, as the health-check models already do with `alias_generator=to_camel, populate_by_name=True`; Python attributes stay snake_case (Ruff's `N` rules are on). `to_camel` yields `clientDataJson`, so `clientDataJSON` takes an explicit `Field(alias=...)`, as `presets/.../schemas.py` does for `format`. `options` is typed as a plain `dict[str, Any]`: the server builds it and the browser only consumes it.

**Detection.** The login page learns passkeys are on from `GET /auth/status`, not from the options endpoint, which writes a challenge row per call and would make a 404 stand for "off".

When passkeys are off, the registration and sign-in routes answer 404 with a clear problem title rather than 500.

### 3.6 Frontend

- **Sign-in page:** a secondary "Sign in with a passkey" button when `status.passkeys` is true. Errors reuse the throttled and generic failure messages. Cancelling the browser prompt is not an error.
- **Settings > Account:** a "Passkeys" section, shown only when enabled: list (name, added, last used), add (name and password), rename, remove with undo-less confirmation because removal is not recoverable.
- **Admin > Users:** the passkey count in the user detail and a "Remove passkeys" action.
- Copy follows DESIGN_GUIDELINES §24. Browser calls use `navigator.credentials`; the choice of helper library is an open question below.

### 3.7 Operations

- The README gains a "Passkeys" section: set `MENAGERIST_API_PUBLIC_ORIGIN`, serve over HTTPS, (a local trial uses `http://localhost:8080`) and note that changing the ID later invalidates every passkey.
- A warn-only readiness check (`passkeys:configuration`, in the style of the proxy and CORS checks) flags a configured ID that does not match the host the browser used. It never fails readiness.

## 4. Testing

- Domain and application: 100% as usual, using the in-memory twins and a software authenticator helper that builds attestation-`none` registrations and signed assertions (ES256 using `cryptography`). Cases: challenge reuse, expiry, wrong origin, wrong RP ID hash, replayed or lower sign count, wrong user handle, disabled account, throttle, passkey from another user, duplicate credential.
- Adapters: router tests for each route and the off state; SQL repository integration tests including delete-with-user.
- E2E: Chromium only, using the DevTools virtual authenticator (`WebAuthn.addVirtualAuthenticator`) against the e2e stack with the ID set to `localhost`. Register, sign out, sign in with the passkey, rename, remove, admin removal. Firefox and WebKit skip these specs.

## 5. Order of work

1. `public_origin` setting and resolver (with tests), passkey settings, then domain, ports, in-memory twins, migration (tests first).
2. Verifier adapter and the software authenticator test helper.
3. Registration use cases and routes, then list/rename/revoke.
4. Passkey sign-in use cases and routes, throttling, status flag.
5. Frontend: Account section, then the sign-in button; e2e.
6. Admin removal, README, DECISIONS entry, readiness check, full gates.

## 6. Open questions (my defaults in bold)

1. **Library.** Which WebAuthn implementation? **`webauthn` (py-webauthn, the Duo Labs library), pure Python on `cryptography`, small and widely used.** The alternative is hand-rolling verification on `cryptography`, which is more code and more risk. Either way it is a new runtime dependency: check Renovate grouping and image size before adding.
2. **Browser helper.** **Use the platform's `PublicKeyCredential` JSON methods with a small base64url fallback, so no frontend dependency.** The alternative is `@simplewebauthn/browser`, which hides browser differences but adds a package.
3. **Password change and reset.** **A password change keeps passkeys; an administrator reset or disable removes the person's sessions as today and leaves passkeys alone**, since the passkey is separate evidence. The alternative is revoking passkeys on admin reset after suspected compromise. Revisit once the first version is in use.
4. **Backup and restore.** **Exclude passkeys from the user archive in v1** and say so in the README, because a restore onto another domain would make them useless. The cost is that a restore on the same domain loses them, and people sign in with a password.
5. **Show the sign-in method in the devices list** ("Signed in with a passkey")? **No in v1**; it needs a session column.
6. **Conditional UI (autofill) on the username field.** **No in v1**; the explicit button is clearer and works everywhere.
7. **Limit per person.** **10 passkeys** (`passkeys_per_user`), alongside the token limit, to bound the table and the registration exclude list.
8. **Existing settings that follow `public_origin`.** **Only `cookie_secure`, and only when asked for with the `origin` mode (built).** Others (CSRF, the proxy-configuration check) could follow later but change behaviour for current installs, so they are separate decisions.
