## About

Menagerist is a self-hostable collection manager. Keep track of the things you care about as items, group them into collections and connect related items to each other.

## Signing in

Run `POST /api/v1/auth/login` with "Try it out" on this page, or use the "Sign in" button in the banner under the title. The banner shows who is signed in.

- The session is the HttpOnly `$session_cookie_name` cookie, which scripts cannot read. It ends when you sign out with `POST /api/v1/auth/logout`.
- A second, readable cookie, `$csrf_cookie_name`, holds a CSRF token. Send its value in the `X-CSRF-Token` header on every POST, PUT, PATCH and DELETE request. This page does that for you; other clients must do it themselves.
- Requests without a matching token are refused with `403 csrf_failed`.

ReDoc (`/api/redoc`) is read-only.

## Permissions

Operations that change the shared structure (item types and relationship types) are for administrators and carry a "Requires permission" line. `GET /api/v1/auth/me/permissions` lists the permissions of the signed-in account.

## Errors

Errors are RFC 9457 `application/problem+json` documents. Expect `401` when you are not signed in (or `setup_required` before the first administrator exists), `403` for `csrf_failed` or `password_expired`, `404` for content you do not own, and `429` with a `Retry-After` header after too many sign-in attempts.
