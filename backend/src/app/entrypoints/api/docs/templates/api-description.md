## About

Menagerist is a self-hostable collection manager. Keep track of the things you care about as items, group them into collections and connect related items to each other.

## Signing in

Run `POST /api/v1/auth/login` with "Try it out" on this page, or use the "Sign in" button in the banner under the title. The banner shows who is signed in.

- The session is the HttpOnly `$session_cookie_name` cookie, which scripts cannot read. Over HTTPS the browser stores it as `__Host-Http-$session_cookie_name` (Secure, no `Domain`), so a cookie planted by a sibling site or a script is not accepted; scripts and curl must send that name. It ends when you sign out with `POST /api/v1/auth/logout`.
- The cookie is `SameSite=Strict`. Every POST, PUT, PATCH and DELETE request that carries it must come from this site's own pages, which browsers (including this page) arrange by themselves. Scripts and tools such as curl must send `Origin: <this server's origin>` with the session cookie (for example `curl -b cookies.txt -H 'Origin: https://menagerist.example.com' -X POST ...`); pasting a curl command from this page needs `-b` with your session cookie added.
- Other requests are refused with `403 csrf_failed`.

ReDoc (`/api/redoc`) is read-only.

## Permissions

Operations that change the shared structure (item types and relationship types) are for administrators and carry a "Requires permission" line. `GET /api/v1/auth/me/permissions` lists the permissions of the signed-in account.

## Errors

Errors are RFC 9457 `application/problem+json` documents. Expect `401` when you are not signed in (or `setup_required` before the first administrator exists), `403` for `csrf_failed` (a cookie-authenticated change not sent from this site) or `password_expired`, `404` for content you do not own, and `429` with a `Retry-After` header after too many sign-in attempts.
