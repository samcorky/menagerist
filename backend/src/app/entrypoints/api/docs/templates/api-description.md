## About

Menagerist is a self-hostable collection manager. Keep track of the things you care about as items, group them into collections and connect related items to each other.

## Signing in

Run `POST /api/v1/auth/login` with "Try it out" on this page, or use the "Sign in" button in the banner under the title. The banner shows who is signed in.

- The session is the HttpOnly `$session_cookie_name` cookie, which scripts cannot read. Over HTTPS the browser stores it as `__Host-Http-$session_cookie_name` (Secure, no `Domain`), so a cookie planted by a sibling site or a script is not accepted; scripts and curl must send that name. It ends when you sign out with `POST /api/v1/auth/logout`.
- The cookie is `SameSite=Strict`. Every POST, PUT, PATCH and DELETE request that carries it must come from this site's own pages, which browsers (including this page) arrange by themselves. Scripts and tools such as curl must send `Origin: <this server's origin>` with the session cookie (for example `curl -b cookies.txt -H 'Origin: https://menagerist.example.com' -X POST ...`); pasting a curl command from this page needs `-b` with your session cookie added.
- Other requests are refused with `403 csrf_failed`.

ReDoc (`/api/redoc`) is read-only.

## Using a token

Scripts and tools can use a personal access token instead of a session. Create one under Settings, Account, then send it with every request:

```
curl -H 'Authorization: Bearer mnst_<id>_<secret>' https://menagerist.example.com/api/v1/collection
```

- The token acts as you, but only with the permissions you gave it. It needs no `Origin` header. It is shown once, when it is created, and expires on the date shown beside it.
- On this page, use "Authorize" to paste a token. Reloading the page forgets it.
- A request that carries a token is only ever judged on the token: a wrong or expired one is `401`, even if a session cookie is sent too.
- Signing in, your account, managing tokens and administration always need the browser session; a token is refused there. Some operations call others, so they may need more permissions than the one listed.

## Permissions

Every operation that needs a permission names it in a "Requires permission" line. Members hold the content permissions (items, collections, media and the like); administrators hold every permission, including those for shared structure such as item types and relationship types, accounts and backups. `GET /api/v1/auth/me/permissions` lists the permissions of the signed-in account.

## Errors

Errors are RFC 9457 `application/problem+json` documents. Expect `401` when you are not signed in (or `setup_required` before the first administrator exists), `403` for `csrf_failed` (a cookie-authenticated change not sent from this site) or `password_expired`, `404` for content you do not own, and `429` with a `Retry-After` header after too many sign-in attempts.
