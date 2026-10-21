# CSRF protection from browser request headers: implementation plan

Status: PRs 1 to 3 implemented and committed on 2026-10-21 (8ac9881; 89f6382 and 60ab2cb; 5301512). Only the follow-ups at the end remain. Written 2026-10-19 and revised the same day after discussion. Replaces an earlier plan that used a session-bound token (see Decision 4). Follow-up PR 2 covers the `__Host-Http-` session cookie, a strict cookie reader and WebKit/Firefox e2e tests; follow-up PR 3 tightens CORS and adds an open-CORS warning. Based on reading `entrypoints/api/shared/http/csrf.py` and `cross_site.py`, `entrypoints/api/__init__.py`, `entrypoints/api/startup.py`, `modules/identity/adapters/api/{auth_router,cookies,dependencies}.py`, `modules/system/adapters/platform/checks/*`, `platform/{proxy_signals.py, config/api.py, config/identity.py}`, `frontend/src/lib/{auth.ts,api/auth-interceptor.ts}`, `frontend/playwright.config.ts`, `frontend/tests/e2e/{auth.spec.ts,fixtures.ts}`, `entrypoints/api/docs/static/swagger-init.js`, `tests/conftest.py`, `tests/modules/identity/adapters/test_auth_router.py`, Starlette's `cookie_parser`, MDN's CSRF and Set-Cookie pages, OWASP's CSRF cheat sheet, caniuse and PortSwigger's "Cookie Chaos" research.

Working rules (`AGENTS.md` / `CLAUDE.md`): never create, stage or push commits; British English; `.svelte` and `.svelte.ts` files go through the `svelte-file-editor` subagent; run only the relevant `poe` checks (`lint-backend`, `typecheck-backend`, `test-backend`, `coverage` before calling backend work done; frontend equivalents); coverage floors: domain/application/shared_kernel 100%, adapters 80%, platform 70%; no try/except in routers; every port has an in-memory sibling.

## Why

A cookie-name mismatch (frontend `menagerist_csrf`, backend `menagerist-csrf`) makes every signed-in unsafe request fail with 403 `csrf_failed`. Rather than aligning the names or exposing the name at runtime, replace the double-submit cookie with checks on headers that browsers set themselves (`Sec-Fetch-Site`, `Origin`) plus `SameSite=Strict`. The frontend then has nothing to read, store or send, and there is no cookie name to configure.

## How it works

**The attack.** A page on another site makes the victim's browser send a request to Menagerist, and the browser attaches the victim's session cookie. The defence has to show that an unsafe request (POST, PUT, PATCH, DELETE) came from Menagerist's own pages.

**Four layers, each enforced by the browser or the server without any token:**
1. **`SameSite=Strict` session cookie.** The browser does not attach the cookie to a request started from another site.
2. **`Sec-Fetch-Site` header.** The browser sets it on every request (`same-origin`, `same-site`, `cross-site` or `none`); page script cannot set or change it. Browsers send it only to secure contexts (HTTPS and localhost), so plain-HTTP LAN installs do not get it.
3. **`Origin` header.** Browsers add it to unsafe requests (cross-origin ones always, and same-origin `fetch`/XHR ones too). The server compares it with its own origin. This is the fallback when `Sec-Fetch-Site` is missing (plain HTTP, older browsers). A sibling subdomain such as `grafana.example.com` has a different origin, so it is refused even though it is "same-site".
4. **CORS with credentials off.** A script on another origin cannot send the cookie or read the response.

**The server check** (`verify_csrf`, on every `/api/v1` route) applies only to an unsafe request that carries the session cookie:

| `Sec-Fetch-Site` | `Origin` | Result |
|---|---|---|
| `same-origin` | anything | allow (a differing `Origin` is logged as a probable proxy misconfiguration, as `refuse_cross_site` does today) |
| `cross-site` | anything | refuse 403 `csrf_failed` |
| `same-site`, `none` or missing | equals the app's own origin | allow |
| `same-site`, `none` or missing | any other value, including `null`, or malformed | refuse |
| missing | missing | refuse (fail closed: every browser sends at least `Origin` on unsafe requests) |

Safe methods (GET, HEAD, OPTIONS) and requests with no session cookie are not checked: with no cookie there is nothing to forge, and authentication answers 401. `cors_origins` plays no part: CORS never supports credentials here, so a listed origin gets no extra trust for cookie requests. The public sign-in and setup routes keep their existing `refuse_cross_site` behaviour (requests with neither header, such as curl and the CLI, pass there).

**The `CSRF-Token` / `X-CSRF-Token` header.** There is no CSRF header in this design. The existing `X-CSRF-Token` header and `menagerist-csrf` cookie are removed with no replacement, so the earlier idea of renaming the header to `CSRF-Token` no longer applies. Nothing in the frontend, the Swagger page or the API needs to send anything special: the browser's own headers do the work. The only visible effect is for non-browser clients that use the session cookie, which must send `Origin: <the server's origin>` themselves (for example `curl -b cookies.txt -H "Origin: https://menagerist.example.com" -X POST ...`); API tokens (future) avoid the cookie altogether.

## What the code does today

1. `cookies.py` sets a random, script-readable `menagerist-csrf` cookie (unrelated to the session) beside the HttpOnly session cookie at login, setup and password change; `csrf.py` requires the `X-CSRF-Token` header to equal the cookie on POST/PUT/PATCH/DELETE. Plain double-submit: an attacker who can plant cookies (sibling subdomain, plain HTTP) can pass it.
2. `verify_csrf` is a dependency on `api_v1_router`. It passes when no session cookie is present.
3. `refuse_cross_site` (Sec-Fetch-Site, then Origin) guards only `/auth/login` and `/auth/setup`. It does not look at the HTTP method, accepts listed `cors_origins`, and lets requests with neither header through.
4. Session cookies are `samesite="lax"` in `cookies.py`.
5. CORS (`entrypoints/api/__init__.py`) uses `allow_origins=cors_origins` (default empty = same-origin only; `*` accepted), `allow_credentials=False`, `allow_methods=["*"]`, `allow_headers=["*"]` and `expose_headers=["App-Version", "Total-Count", "Link"]`. The wildcards are looser than needed and `ETag` is not exposed (see PR 3).
6. The frontend `auth-interceptor.ts` copies the CSRF cookie into the header on unsafe requests; `auth.ts` has `CSRF_COOKIE`, `CSRF_HEADER`, `csrfToken()`, `readCookie` and `isUnsafeMethod` (only the interceptor uses `isUnsafeMethod` in `src`).
7. The Swagger docs page gets the cookie name via `data-csrf-cookie` and reads the cookie in `swagger-init.js` (`readCookie`, `needsCsrf`, `applyCsrf`). `applyCsrf` also does two things unrelated to CSRF that must survive the change: it forces `credentials: 'same-origin'` on every request, and it strips the placeholder `Cookie` header Swagger adds for the lock so it does not appear in the generated curl snippet. The banner's sign-out also goes through `applyCsrf`.
8. Playwright runs three Chromium-based projects (`chromium`, `mobile`, `auth`) against plain `http://localhost` backends; no WebKit or Firefox project and no HTTPS. Its API request context sends no `Origin`. The `auth` project runs serially against a dedicated empty database. `tests/e2e/auth.spec.ts` (line 133) looks for a cookie named `menagerist_session` (underscore) while the backend default is `menagerist-session`, and `tests/e2e/fixtures.ts` uses `menagerist_csrf`; both are stale.
9. Backend tests: `tests/conftest.py` patches every `TestClient` with the CSRF cookie and header; `test_auth_router.py`'s `Api.new_client` removes them again for the tests that need a bare client.
10. Custom headers in use: `X-CSRF-Token` (request, being removed), `App-Version`, `Total-Count` (responses, exposed via CORS) and `Request-Id` (request and response). Proxy-set `X-Forwarded-For` and `X-Forwarded-Proto`, and browser-defined `X-Content-Type-Options` and `X-Frame-Options`, keep their names.
11. Start-up warnings live in `entrypoints/api/startup.py` (`lifespan` runs `warn_if_storage_not_writable` and `warn_if_no_administrator`, tested in `tests/entrypoints/api/test_startup.py`). Warn-only readiness checks live in `modules/system/adapters/platform/checks/` and are wired in `modules/system/adapters/api/dependencies.py` (`StorageCheck` for static config; `ProxyConfigurationCheck` reads runtime `ProxySignal`s from `platform/proxy_signals.py`).

## Design

**`verify_csrf` rewritten in place** (`entrypoints/api/shared/http/csrf.py`; the `CsrfError` class and the `csrf_failed` problem type stay, so the API contract and existing error handling do not change). New message: "This request was not sent from this site's own pages." (the old "Reload the page" no longer helps).

```python
_SAFE_METHODS = frozenset({"GET", "HEAD", "OPTIONS"})


async def verify_csrf(request: Request) -> None:
    """Refuse an unsafe, cookie-authenticated request not sent by this app's own pages.

    Raises:
        CsrfError: If `Sec-Fetch-Site` says cross-site, or `Origin` is not the
            app's own origin, or neither header is present.
    """
    if request.method in _SAFE_METHODS:
        return
    if not request.cookies.get(get_identity_settings().cookie_name):
        return
    site = request.headers.get("Sec-Fetch-Site")
    origin = request.headers.get("Origin")
    own = origin_of(request.url.scheme, request.url.netloc)
    if site == "same-origin":
        note_origin_mismatch(origin, own)  # warning and ProxySignal, as today
        return
    if site != "cross-site" and origin is not None and claimed_origin(origin) == own:
        return
    log_refusal(request, site, origin, own)  # reasons and origins only, never cookies
    raise CsrfError("This request was not sent from this site's own pages.")
```

- `origin_of`, the mismatch note and the refusal logging move out of `cross_site.py` into helpers both functions import; `refuse_cross_site` keeps its behaviour. `claimed_origin` parses `Origin` with `urlsplit`; `Origin: null`, a malformed value or a different scheme, host or port gives a non-matching origin (default ports normalised, host lower-cased, as `origin_of` does today).
- `Sec-Fetch-Site: none` (user-initiated navigation) cannot occur on an unsafe request; it falls through to the `Origin` comparison.
- When API tokens land, skip the check for requests authenticated by a bearer token (the cookie is ignored for them).

**Cookies.** Session cookie `SameSite=Strict` (was `Lax`) in `set_session_cookies` and `clear_session_cookies`. Safe for an SPA: the shell is static and does not need the cookie, and the app's own `fetch()` calls are same-site, so a link from elsewhere just loads the page and the first `/auth/me` call carries the cookie. Re-test with the OIDC callback when it exists (the callback is a GET, so the check does not apply to it, and `Strict` allows the cookie to be set on its response).

**Remove.** CSRF cookie set/clear in `cookies.py`; `csrf_cookie_name` and the distinct-names validator in `platform/config/identity.py`; `MENAGERIST_CSRF_COOKIE_NAME`; `data-csrf-cookie` in the docs template.

**Frontend.** Remove the request interceptor in `auth-interceptor.ts` (keep the response interceptor and its `handleAuthResponse` call, drop the unused `carryStamp` import if nothing else there uses it); remove `CSRF_COOKIE`, `CSRF_HEADER`, `csrfToken()`, `readCookie` and `isUnsafeMethod` from `auth.ts` if nothing else uses them; update the comment at the top of `client.ts`. Nothing new is added, no API response changes, and the generated client needs no regeneration.

**Swagger docs page.** In `swagger-init.js`, remove the CSRF parts only: `CSRF_HEADER`, `UNSAFE_METHODS`, `readCookie`, `needsCsrf`, the header logic in `applyCsrf`, the `data-csrf-cookie` read, and their exports. Keep the rest of `applyCsrf` as a smaller `prepareRequest(req)` that still sets `credentials: 'same-origin'` and deletes the placeholder `Cookie` header, and use it as the `requestInterceptor`. The banner's sign-out becomes a plain `fetch(API_PREFIX + '/auth/logout', { method: 'POST', credentials: 'same-origin' })`. "Try it out" and sign-out run in the same origin as `fetch`, so the browser sends `Sec-Fetch-Site: same-origin` and `Origin` itself and the check passes with no script help. One side effect: Swagger's generated curl snippets for unsafe operations no longer carry a CSRF header, and they carry no cookie, so anyone pasting one with their own cookie must add `-H 'Origin: <this server's origin>'`; the text below says so. Do not try to add `Origin` from the interceptor: it is a forbidden header name and browsers drop it. Update `api-description.md` (it currently says requests without a matching token get `403 csrf_failed`): cookie-authenticated unsafe requests must come from this site; browsers do this automatically; scripts send `Origin: <this server's origin>`, or use an API token once those exist. The `403 csrf_failed` description in the errors paragraph stays.

**Tests and tooling.** `TestClient` gets a default `Origin: http://testserver` instead of the CSRF cookie and header; the Playwright fixtures send `Origin: <baseURL>` on their API request contexts (browser `page` requests send their own).

## Future auth methods

- **OIDC** (Authorization Code + PKCE, backend-terminated): it ends in the same cookie session, so nothing here changes. The callback is a GET and is not checked; confirm the `Strict` flow once it exists.
- **API tokens**: bearer tokens sent in an `Authorization` header are not ambient credentials, so they are not CSRF-vulnerable; skip the check for requests a bearer token authenticates. Rule to keep: if a bearer token authenticates the request, the cookie is ignored and the check is not needed; if the cookie authenticates it, the check applies. When API tokens land, add `Authorization` to the CORS allowed request headers (PR 3 leaves it out until then).

## Phases, PR 1 (one PR; backend and frontend ship together in the single image, so no dual-accept period)

1. Backend: rewrite `verify_csrf`, share the origin helpers with `cross_site.py`, `Strict` cookies, remove the CSRF cookie and the setting.
2. Backend tests: `conftest.py` default `Origin`, `Api` helpers, new decision-table tests, updated assertions (listed below).
3. Frontend: remove the interceptor and cookie helpers, update their tests.
4. e2e: fixtures send `Origin`, remove the CSRF cookie lookups, fix the stale `menagerist_session` name in `auth.spec.ts` line 133, add a cross-site mutation spec.
5. Swagger docs script (keeping the same-origin credentials and `Cookie`-stripping behaviour), template and text. The session cookie security scheme (`APIKeyCookie` in `permission_aware_route.py`) and line 9 of `api-description.md` stay as they are. Specifically:
   - `api-description.md`: replace lines 10-11 (readable CSRF cookie, `X-CSRF-Token`, "matching token") with the same-origin rule and the `Origin: <server origin>` note for non-browser clients; reword the `csrf_failed` mention on line 21; drop `$csrf_cookie_name`.
   - `openapi.py` `api_description()`: stop passing `csrf_cookie_name` (the setting no longer exists).
   - `docs/templates/swagger.html`: remove `data-csrf-cookie`. `docs/router.py`: remove the `csrf_cookie_name` parameter and context value (lines ~56-98) and fix the docstring at ~132 ("CSRF header and sign-in banner").
   - Comments and docstrings: `entrypoints/api/__init__.py` lines 56-57 ("matching CSRF header and cookie") and `cross_site.py` line 33 ("the CSRF token").
   - Curl snippets: have `prepareRequest` set `req.headers['Origin'] = window.location.origin` (Swagger UI builds the curl text from the request after the request interceptor, which is why the `Cookie` stripping already works). `Origin` is a forbidden header name, so the browser silently drops it from the real `fetch` and sends its own, identical value; only the snippet shows it. Verify both halves in Playwright: the snippet contains `-H 'Origin: <baseURL>'` and "Try it out" still succeeds. Fallback if Swagger UI builds snippets before the interceptor: a `requestSnippets` generator override that appends the header. Add a unit test for the header in `swagger-init.test.ts`. The snippet still has no cookie, so the docs text says to add `-b` with the session cookie.
6. Docs: new `DECISIONS.md` entry superseding the double-submit parts of the identity section; update `ARCHITECTURE.md`, `backend/README.md` (cookies/CSRF paragraph), `frontend/README.md`, `CONTRIBUTING.md`. Leave the historical plans under `docs/superpowers/` alone.

## Tests, PR 1

Backend `verify_csrf` (parametrised against a v1 mutation route, session cookie present unless stated):
- Safe methods pass whatever the headers say, including `Sec-Fetch-Site: cross-site`.
- No session cookie passes (and then answers 401 from authentication).
- `Sec-Fetch-Site: same-origin` passes with no `Origin`, with the right `Origin` and with a different `Origin` (the last also records the `ORIGIN_MISMATCH` proxy signal).
- `Sec-Fetch-Site: cross-site` is refused with 403 `csrf_failed`, even with the app's own `Origin`.
- `same-site` or no `Sec-Fetch-Site` with `Origin` equal to the app's own origin passes: including plain `http://` origins, an explicit default port (`https://host:443` equals `https://host`) and different letter case.
- `Origin` for another host, another port, another scheme, `null` or malformed is refused.
- Neither header present is refused.
- A `cors_origins`-listed origin is refused for a cookie-authenticated unsafe request and still passes `refuse_cross_site` on login (the two checks differ on purpose).
- The check covers other v1 routes, not just identity ones; `/api/health` and the SPA are untouched.
- The refusal body is `type: csrf_failed` with the new message; the log line names the reason and origins, never cookie values.

Backend cookies and settings: login, setup, password change and logout set no CSRF cookie and clear none; the session cookie is `SameSite=Strict` when set and when cleared; remove `csrf_cookie_name` cases from `test_identity_settings.py`; update `test_docs.py` (line 324 still expects `csrf_failed` in the description) and the template text assertions; update the `test_current_actor.py` cases (lines 272-306) from "wrong token" to "cross-site `Origin`"; replace cookie and header lookups in `test_auth_router`, `test_devices_router`, `test_logging_context`, `test_auth_postgres`, `test_claim_existing_data_postgres` and `test_authenticated_routes`; keep the `refuse_cross_site` tests for login and setup; run the ArchUnit tests (entrypoints importing identity adapters).

Frontend: delete the "CSRF header" and "follows a changed CSRF cookie" cases in `auth-client.test.ts` (keep "ignores a 403 that is not password_expired"); delete the `readCookie` and `isUnsafeMethod` cases in `auth.test.ts`; in `swagger-init.test.ts` delete the `readCookie`, `needsCsrf`, typed-header and empty-header cases (and the two `readCookie` edge cases), and keep the behaviour that stays under new names: `prepareRequest` sets `credentials: 'same-origin'` and drops the placeholder `Cookie` header (the existing "cookie header" test, calling `prepareRequest`), leaves other headers alone, and sends no `X-CSRF-Token`. In `tests/e2e/swagger.spec.ts` update the comments at lines 39 and 191 (they mention the CSRF header); its Try-it-out create call, sign-out and the "curl has no cookie" assertions stay as they are and now also prove the same-origin path works from the docs page.

e2e (Chromium in PR 1, all engines in PR 2): after sign-in, a page on another origin (served with `page.route`) with an auto-submitting form POST and a credentialed `fetch` to a v1 mutation route changes nothing, while the same call from the app's own page succeeds. A manual check on a plain-HTTP LAN address covers the `Origin`-only path (no `Sec-Fetch-Site` there), which `http://localhost` cannot exercise because browsers treat it as a secure context.

## Relationship to `settings-handoff-plan.md`

- Phase 0 there (fix the cookie name) is superseded: the cookie goes away. If a stop-gap is needed first, change the frontend to the hyphen.
- Phase 3 there (public config) no longer needs `identity.csrf_cookie_name`; its other fields (e.g. `media.max_upload_size`) still justify it.
- Its Phase 2 route moves do not conflict.

## Decisions (Sam, 2026-10-19)

1. Removing `MENAGERIST_CSRF_COOKIE_NAME`: accepted (single user so far; still check that `MenageristBaseSettings` does not reject the leftover variable at startup if it is set in an existing deployment).
2. Session cookie over HTTPS: `__Host-Http-menagerist-session`, with a strict cookie reader, in a separate PR 2 (below). Add WebKit (Safari-engine) and Firefox e2e tests there.
3. CI time for the extra browsers: acceptable. e2e only runs ad hoc and on PRs, and Playwright runs projects in parallel, so the new projects run alongside the existing ones; only the one-off browser download adds time (cache `~/.cache/ms-playwright`).
4. No CSRF token, header or cookie. Protection is `SameSite=Strict` plus the `Sec-Fetch-Site` / `Origin` check on unsafe cookie-authenticated requests, own origin only, failing closed when neither header is present. Reasons: Go 1.25's `http.CrossOriginProtection` and Datasette take the same approach, OWASP calls Fetch Metadata the primary signal, it removes about a third of PR 1 and the failure class that started this. A session-bound token in the `/auth/me` response (with per-response masking against BREACH) was designed and reviewed, and can be added later as an additive layer if OIDC with `SameSite=Lax` or a cross-origin cookie SPA ever needs it.
5. CORS tightened and an open-CORS (`*`) warning added, as a separate PR 3 (below). Sam asked for the warning to work like the proxy-configuration warning; the code has two fitting patterns (start-up log, warn-only readiness check) and PR 3 uses both. The tighter lists themselves are a recommendation Sam has not yet confirmed (see PR 3 open points).

## Open points (PR 1)

1. Check the app's `Referrer-Policy` value. With `no-referrer`, a same-origin request that is not in `cors` mode (a native form post) is sent with `Origin: null`; the SPA, hey-api client and Swagger UI use `fetch`/XHR in `cors` mode and send the real origin, and secure contexts also send `Sec-Fetch-Site`, but confirm before relying on the fallback.
2. Confirm in real browsers that same-origin PUT, PATCH and DELETE from `fetch` carry `Origin` (the e2e runs on Chromium; PR 2 adds WebKit and Firefox).
3. Decide whether a bare `curl -b` with no `Origin` being refused is acceptable until API tokens exist (this plan says yes; the old design needed a matching CSRF header, so scripts were already burdened).

## PR 2: `__Host-Http-` session cookie, strict reader and WebKit tests

### Why both a prefix and a strict reader

| Attack | Browser prefix | Strict reader |
|---|---|---|
| Sibling subdomain or plain-HTTP page sets a cookie with the exact name | blocked by the browser | not needed |
| Page script (XSS) sets or overwrites the cookie via `document.cookie` | blocked by `__Host-Http-` (HttpOnly rule) | not needed |
| Disguised name (leading Unicode space, e.g. U+2000, U+0085, U+00A0) from PortSwigger's "Cookie Chaos" | not stopped: the browser sees an unprefixed name | blocked |
| Duplicate cookie names, last wins | not stopped | blocked |

Starlette's `cookie_parser` (read in 1.9.0; the lockfile pins 1.6.0, which I did not read) calls `.strip()` on cookie names, which removes Unicode spaces in Python, and keeps the last duplicate. So a disguised cookie is read as the real name and can win. The attack needs control of a sibling subdomain or the network path, so for a self-hosted single-user app this is defence in depth.

### Prefix choice

`__Host-Http-` (Secure, HttpOnly, no `Domain`, `Path=/`). `__Http-` alone would allow a `Domain` attribute, so a malicious HTTPS sibling could still toss a cookie; it has the same browser support, so it gains nothing. Support (caniuse): Chrome and Edge 140+, Firefox 143+ (partial in 142), Safari none. Browsers without support accept the name as an ordinary cookie, so over HTTPS only the prefixed name is ever read and the strict reader is the protection there. If Safari coverage ever matters more, drop to plain `__Host-` by changing one constant.

### Backend

```python
# modules/identity/adapters/api/cookies.py
_SESSION_PREFIX = "__Host-Http-"


def session_cookie_name(request: Request, settings: IdentitySettings) -> str:
    """`__Host-Http-menagerist-session` over HTTPS, plain `menagerist-session` otherwise."""
    if _secure(request, settings):
        return _SESSION_PREFIX + settings.cookie_name
    return settings.cookie_name


def set_session_cookies(request, response, token, settings) -> None:
    response.set_cookie(
        session_cookie_name(request, settings),
        token,
        max_age=settings.session_ttl_hours * 3600,
        path="/",            # required by __Host-
        secure=_secure(request, settings),  # required by the prefix (True when prefixed)
        httponly=True,       # required by __Http-
        samesite="strict",
        # no domain=: required by __Host-, and Starlette sets none by default
    )
```

```python
def session_cookie_value(request: Request, name: str) -> str | None:
    """Exactly one cookie named `name`, or None if absent, duplicated or disguised."""
    found: list[str] = []
    for header in request.headers.getlist("cookie"):
        for chunk in header.split(";"):
            key, _, value = chunk.partition("=")
            key = key.strip(" \t")          # ASCII only, unlike str.strip()
            if key == name:
                found.append(value.strip(" \t"))
            elif key.strip() == name:        # same name once Unicode spaces are trimmed
                return None
    return found[0] if len(found) == 1 else None
```

- `clear_session_cookies` uses `session_cookie_name`; the readers (`dependencies.get_session_token`, `entrypoints/api/shared/http/csrf.py`) call `session_cookie_value(request, session_cookie_name(request, settings))`.
- The name follows the same `_secure()` detection as the `Secure` flag: behind a TLS proxy it needs `MENAGERIST_TRUSTED_PROXIES` (or `MENAGERIST_COOKIE_SECURE=true`) so the app sees HTTPS; otherwise it stays plain, as today.
- `APIKeyCookie(name=settings.cookie_name)` in `permission_aware_route.py` only feeds the OpenAPI document and can keep the plain name (mention the prefix in the docs text).
- A disguised or duplicate cookie means "no session": a tossed cookie can log someone out (cookie tossing can always do that) but cannot give the attacker a session.
- Someone switching between HTTP and HTTPS has to sign in again.

### Backend tests

`https://` base-URL case: name is `__Host-Http-menagerist-session` with `Secure`, `HttpOnly`, `Path=/`, `SameSite=Strict` and no `Domain`; a plain-named cookie sent over HTTPS is ignored; a cookie whose name starts with U+2000, U+0085 or U+00A0 followed by `__Host-Http-menagerist-session` gives no session; a duplicate exact name gives no session; the real cookie plus a disguised copy gives no session; plain HTTP still uses `menagerist-session`.

### Playwright: WebKit (Safari engine) and Firefox

Today there are only Chromium projects over plain HTTP, so none of this would run. Layout:

- **New backend and database.** A `cookies` backend (own database, e.g. `menagerist_cookies`) started with `MENAGERIST_COOKIE_SECURE=true`, fronted by a small dependency-free TLS proxy (a Node script using `node:https` and `node:http`, self-signed certificate generated at start-up) added to `webServer`; projects use `ignoreHTTPSErrors: true`. The backend is also reachable over plain HTTP on its own port for the HTTP-fallback test. `auth.spec.ts` stays Chromium-only on its existing serial `auth` project: it shares the empty auth database, so adding engines there would collide.
- **Projects.** A `cookies-setup` project (`cookies.setup.ts`) creates the first admin once. Three projects depend on it and run `cookies.spec.ts` only: `cookies-chromium`, `cookies-webkit` (`devices['Desktop Safari']`) and `cookies-firefox` (`devices['Desktop Firefox']`). Each engine creates its own user through the admin API with the project name in the username (the existing `createUserViaApi` helper), so the three run concurrently on the shared backend and in parallel with the rest of the suite.
- **CI.** Install with `npx playwright install --with-deps webkit firefox` and cache `~/.cache/ms-playwright`.
- **Tests in `cookies.spec.ts`** (all three engines unless noted):
  1. Sign-in sets exactly one session cookie named `__Host-Http-menagerist-session` with `secure`, `httpOnly`, `path=/`, `sameSite=Strict`, host-only; `document.cookie` does not show it; the account menu is visible and a PATCH (display name) succeeds, proving the same-origin check passes in that engine.
  2. Disguised names: use `context.addCookies` (or `document.cookie` from the page) to add cookies whose names start with U+2000, U+0085 or U+00A0 followed by `__Host-Http-menagerist-session`, next to the real cookie; assert the server treats the request as signed out (401 or redirect to sign-in). If an engine refuses to store a name, mark that case `test.fixme` for that engine with a comment, rather than deleting it. PortSwigger reports Safari accepts the single-byte variants.
  3. Prefix enforcement (Chromium and Firefox only): a page script cannot create `__Host-Http-menagerist-session` through `document.cookie`; skip on WebKit and record that Safari does not enforce this prefix.
  4. Strict navigation (all engines): from a page on another origin (served with `page.route`, with a link to the app), click through; the app loads without the cookie on the first request and is signed in after `/auth/me`. This also pins the behaviour OIDC will rely on.
  5. Plain-HTTP fallback (all engines): sign-in over the backend's plain HTTP port uses the plain `menagerist-session` name and works.
  6. Cross-site mutation refused (all engines): from a page on another origin (served with `page.route`), an auto-submitting form POST and a `fetch(..., { credentials: 'include' })` to a v1 mutation route change nothing (under `SameSite=Strict` the cookie is not sent, so the answer is 401, or the request is refused); the same call from the app's own page succeeds. Engines differ in what they send (`Sec-Fetch-Site`, `Origin`), which is why this runs on all three.
- **Caveat:** Playwright's WebKit is an engine build, not Safari itself; cookie handling (ITP, storage and prefix rules) can differ, especially on Linux. Treat these tests as an engine regression guard and still check once by hand in real Safari on macOS and iOS before release.

### Open points

0. Disguise characters. Headers are decoded as latin-1, so only single-byte spaces (`\x85`, `\xa0`, `\x0b`, `\x0c`, `\x1c` to `\x1f`) can disguise a name; a UTF-8 U+2000 stays a different name. Backend tests use the single-byte set. In Playwright, U+2000 case 2 is still worth one engine run, but expect it to behave as an unrelated cookie.
1. Does the e2e TLS proxy script live under `frontend/tests/e2e/` or `shared/` (it is test infrastructure only)? Default: `frontend/tests/e2e/`.
2. Does the e2e Postgres container create `menagerist_cookies` automatically like the existing `menagerist_w{n}` and `menagerist_auth` databases, or does something need adding? Check before PR 2.

## PR 3: tighter CORS and an open-CORS warning

Independent of PR 1 and PR 2: it touches the CORS middleware block, `startup.py` and the system checks, none of which the other PRs change, so the three can merge in any order. Small enough to review on its own.

### Why

With `allow_credentials=False` a cross-origin page can never send the session cookie, so today's wildcards (`allow_methods=["*"]`, `allow_headers=["*"]`) add little real risk. They are still looser than the API needs (Starlette echoes back whatever headers a preflight asks for), and one header is missing from the exposed list: `ETag` is not CORS-safelisted, so a cross-origin client cannot read it even though the API and the ETag interceptor rely on it. `Link` and `Total-Count` are already exposed; `Last-Modified` is safelisted.

### CORS configuration

Constants in one small module (e.g. `entrypoints/api/shared/http/cors.py`) so the middleware and the tests share them:

```python
CORS_METHODS = ["GET", "POST", "PUT", "PATCH", "DELETE"]
CORS_REQUEST_HEADERS = [
    "Content-Type",        # JSON bodies need a preflight
    "If-Match",            # optimistic concurrency
    "If-None-Match",       # ETag revalidation
    "If-Modified-Since",
    "Request-Id",
]
CORS_RESPONSE_HEADERS = [
    "App-Version", "Total-Count", "Link",
    "ETag",                # not CORS-safelisted; cross-origin clients cannot read it today
    "Request-Id",
    "Retry-After",         # rate-limit and lockout responses
]
```

```python
fastapi_app.add_middleware(
    CORSMiddleware,
    allow_origins=get_api_settings().cors_origins,
    allow_credentials=False,
    allow_methods=CORS_METHODS,
    allow_headers=CORS_REQUEST_HEADERS,
    expose_headers=CORS_RESPONSE_HEADERS,
    max_age=600,           # Starlette's default, made explicit
)
```

- Starlette adds the safelisted request headers (`Accept`, `Accept-Language`, `Content-Language`, `Content-Type`) itself; listing `Content-Type` is for clarity. A preflight asking for another method or header is refused with 400 instead of being waved through.
- **No CSRF header exists to allow.** Cross-origin pages cannot send cookies (credentials off), and `verify_csrf` ignores `cors_origins` for cookie-authenticated requests, so CORS never invites a cross-origin cookie flow. If a cross-origin cookie SPA is ever wanted, that is a deliberate change: `allow_credentials=True`, explicit origins and a matching change to `verify_csrf`.
- **`Authorization` is not allowed yet.** Add it in the PR that introduces API tokens.
- `refuse_cross_site` (the public sign-in and setup routes) is unaffected: it still ignores `*` and uses listed origins as its allowlist.

### Warning when `MENAGERIST_CORS_ORIGINS` contains `*`

`*` is safe with credentials off, so the wording is "any website can call the API without cookies", not "vulnerable". Both patterns from "What the code does today", item 11:

1. **Start-up log warning.** `warn_if_cors_open()` in `entrypoints/api/startup.py`, called from `lifespan` beside the storage and administrator checks (it runs once per worker, like them). It logs one warning when `"*"` is in `get_api_settings().cors_origins`.
2. **Warn-only readiness check.** `CorsConfigurationCheck` in `modules/system/adapters/platform/checks/cors_configuration_check.py`, wired next to `ProxyConfigurationCheck` in `modules/system/adapters/api/dependencies.py`. It takes the origins in its constructor (like `StorageCheck` takes directories, so it is easy to test and the system module does not import entrypoints), returns `cors:configuration` with `CheckStatus.WARN` and the same text, or PASS. No I/O. It only ever warns: a configuration choice must not take the instance out of rotation.

The runtime `ProxySignal` mechanism is not used: it records things observed on requests, and a fixed setting has nothing to observe.

One constant holds the text so the log line and the check output match (e.g. `CORS_OPEN_HINT` under `platform/`, beside `ApiSettings`):

> CORS allows any origin: any website can call this API from a visitor's browser, without their cookies. Set MENAGERIST_CORS_ORIGINS to the origins that need it, or leave it empty for same-origin only.

### Tests

- **CORS (new file beside `test_cross_site.py`):** an allowed preflight (listed origin, allowed method and headers) returns the allow headers and `max-age`; a disallowed method and a disallowed header (including `Authorization`) each get 400; a disallowed origin gets 400; an actual cross-origin response exposes `ETag`, `Total-Count`, `Link`, `Request-Id` and `App-Version`; same-origin requests (no `Origin`) are unaffected. Keep the existing cases in `test_api_settings.py` and `test_auth_router.py` green.
- **Warning (`test_startup.py`):** `warn_if_cors_open` logs one warning when `*` is present, stays quiet for an empty list and for explicit origins; extend the lifespan test to expect the extra call and its order.
- **Check (beside `test_proxy_configuration_check.py`):** WARN with the hint for `*`, PASS otherwise, including explicit origins.

### Open points

1. Confirm no route uses a method outside the five listed (none seen, but not every router was checked).
2. Confirm the dev frontend on :5173 reaches the backend through the Vite proxy and not cross-origin. If it is cross-origin today, cookie auth is already broken there (credentials off), so this change would not make it worse.
3. Whether to log the start-up warning at all when running under tests or the CLI; default is the same as the other start-up warnings (lifespan only).

## PR 4: browser self-check on the status page

### Why

If a reverse proxy strips `Origin` and `Sec-Fetch-Site`, every sign-in and change from the SPA fails with `403 csrf_failed`. The server cannot tell a stripped browser request from a script, so it cannot warn by itself (see the rejected `MISSING_ORIGIN_HEADERS` signal). An administrator's own browser is certainly a browser, so it can ask the backend what arrived.

### Shape (same layering as the other system use cases)

- **Domain** (`modules/system/domain/browser_check.py`). Frozen `BrowserRequest(sec_fetch_site, origin, seen_origin)` of plain strings (no Starlette types) and `BrowserCheckResult(status: CheckStatus, sec_fetch_site, origin, seen_origin, output)`. A pure function `assess(request) -> BrowserCheckResult`: `pass` when `Sec-Fetch-Site` is `same-origin`, or `Origin` equals `seen_origin`; `warn` when `Sec-Fetch-Site` is `same-origin` but `Origin` is absent or differs (host or scheme is changed on the way in; `MENAGERIST_TRUSTED_PROXIES` and the proxy's `Host`); `warn` when only `Origin` arrived (plain HTTP to a non-localhost host, where browsers send no `Sec-Fetch-*`; the check still works). `output` is the human hint, set only on `warn`. Neither header present never reaches it: `verify_csrf` refuses first, which is the failure the check exists to expose.
- **Application** (`modules/system/application/run_browser_check.py`). `RunBrowserCheckQuery(request: BrowserRequest)` and `RunBrowserCheck`, an `AuthorisedUseCase` needing `SystemPermission.READ_DIAGNOSTICS` (no new permission). It has no port: it only calls `assess`, so there is nothing to put behind an interface and no in-memory sibling to add. It is a query (no commit), though the route is `POST`.
- **Adapters/API** (`modules/system/adapters/api/router.py`, `dependencies.py`). `POST /api/browser-check`, `operation_id="run_browser_check"`, `Cache-Control: no-store`. The router builds `BrowserRequest` from the headers and `own_origin(request)` (the header reading is HTTP, so it belongs here, as `verify_csrf` does today) and maps the result to a `BrowserCheckResponse` Pydantic model. No `try/except`; `403` documented with `error_response(ForbiddenError, ...)`, covering both the permission and the CSRF refusal. Wired like `get_get_version_detail_use_case`.
- **POST on purpose.** `verify_csrf` ignores safe methods, so a `GET` would pass even with the headers stripped and prove nothing. Because the route is unsafe, a stripped request is refused by the existing dependency with `csrf_failed` and never reaches the use case.
- **No proxy signal.** The route records nothing itself; a script calling it either has no session (401) or no headers (403, already logged by `log_refusal`). The existing `ORIGIN_MISMATCH` note in `verify_csrf` still fires for a genuine browser, which is correct. Nothing a script sends can add a `proxy:configuration` warning.

### Frontend

The status page (administrators only, like the detail cards) gets a "Browser check" card. It calls `runBrowserCheck` on load (the generated client is regenerated with `poe generate-frontend-client`) and shows one of:
- **Pass**: headers arrived intact.
- **Warn**: the response's `output`, plus the origin the page has (`location.origin`) beside the one the server saw.
- **Failed with `403 csrf_failed`**: "Something between your browser and Menagerist removed the browser's `Origin` and `Sec-Fetch-Site` headers, so changes will be refused. Check the proxy passes request headers through." Distinguished from a permission 403 by the problem `type`.
- **Plain HTTP**: the warn text for "only `Origin` arrived" says this is normal for http to a non-localhost host.

Logic (choosing the message from the call result) goes in `frontend/src/lib/status.ts` next to `readinessOf`, with Vitest cases; the card is a `.svelte` change, so it goes through the `svelte-file-editor` subagent. Copy in British English and without graph terms, per `DESIGN_GUIDELINES.md`.

### Tests

- Domain: every branch of `assess`, no I/O (100% floor).
- Application: authorised actor gets the result; an actor without `READ_DIAGNOSTICS` is refused; the result is passed through unchanged (100% floor).
- Router (raw-scope `Request` tests as in PR 1, plus the in-memory wiring): same-origin browser headers give `pass`; same-origin with a differing `Origin` gives `warn` with `seen_origin` filled in; `Origin` only gives `warn`; no headers with a session gives `403 csrf_failed` and the use case is not called; no session gives `401`; a non-admin gives `403` with the permission problem; `Cache-Control: no-store`.
- Guard tests from PR 3 keep passing: `POST` is already a listed CORS method and the response has no new header.
- Frontend: Vitest for the message chooser (pass, warn, csrf 403, permission 403, network error). Playwright: in the cookie project, an admin sees "pass" over both the plain and the TLS URL; one test routes the request through a proxy that deletes `Origin` and `Sec-Fetch-Site` (the TLS proxy script can take a flag for it) and expects the stripped-headers message.

### Open points

1. Whether `CsrfError` should carry `seen_origin` and `claimed_origin` in the problem document so the failed case can show both (they are only in the server log today). They are the server's own origin and the browser's own claim, so nothing secret, but it changes a shared error type; default is to leave them out and rely on the page's `location.origin`.
2. Whether the card runs on load or on a button. Default is on load: it is one cheap authorised request, and the point is that nobody has to remember to run it.
3. Resolved: `AuthorisedUseCase` (no repos) fits a use case with no port.

## Follow-ups (not in a PR yet)

- **No session-bound token.** Decided against (2026-10-21): the remaining gap needs a browser that misreports its headers or a proxy that strips them, which fails closed with a logged reason.
- **No `MISSING_ORIGIN_HEADERS` proxy signal.** Non-browser clients are in scope and would trip it.
