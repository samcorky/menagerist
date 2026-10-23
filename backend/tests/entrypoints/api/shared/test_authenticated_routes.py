"""Every /api/v1 route needs a session unless it is explicitly allowlisted."""

from typing import TYPE_CHECKING

from fastapi.dependencies.utils import get_dependant
from fastapi.routing import APIRoute

from app.entrypoints.api import api_v1_router, public_v1_router
from app.entrypoints.api.shared.dependencies import get_current_actor
from app.entrypoints.api.shared.http.cross_site import refuse_cross_site
from app.modules.identity.adapters.api.dependencies import (
    get_active_identity_actor,
    get_identity_actor,
    get_session_token,
    get_signed_in_user,
)

if TYPE_CHECKING:
    from collections.abc import Callable, Iterator

    from fastapi import APIRouter
    from fastapi.dependencies.models import Dependant

# Paths below are relative to /api. These routes sit on the public router.
PUBLIC_ROUTES = {
    ("GET", "/v1/auth/status"),
    ("POST", "/v1/auth/setup"),
    ("POST", "/v1/auth/login"),
    # The backup restorer rechecks setup under the shared identity lock.
    ("POST", "/v1/backup/first-run-restore"),
    # Name and version only; the build detail is on the authenticated router.
    ("GET", "/v1/system/version"),
}
# Unauthenticated POSTs have no session cookie to check, so they refuse
# cross-site calls.
CROSS_SITE_GUARDED_ROUTES = {
    ("POST", "/v1/auth/setup"),
    ("POST", "/v1/auth/login"),
    ("POST", "/v1/backup/first-run-restore"),
}
# On the same-origin-checked router but deliberately tolerant of a missing session.
NO_ACTOR_ROUTES = {("POST", "/v1/auth/logout")}
# Identity routes resolve the session through the identity dependencies.
# Identity-prefixed paths that live in entrypoints and use the content actor.
CONTENT_ACTOR_ROUTES = {("GET", "/v1/auth/me/permissions")}
IDENTITY_PREFIXES = ("/v1/auth/", "/v1/user", "/v1/session")
IDENTITY_ACTORS = {
    get_identity_actor,
    get_active_identity_actor,
    get_signed_in_user,
}


def _routes(router: APIRouter, prefix: str = "") -> Iterator[tuple[str, APIRoute]]:
    for route in router.routes:
        if isinstance(route, APIRoute):
            yield prefix + route.path, route
        elif hasattr(route, "original_router"):
            yield from _routes(route.original_router, prefix)


def _calls(dependant: Dependant) -> set[Callable[..., object]]:
    found: set[Callable[..., object]] = set()
    for sub in dependant.dependencies:
        if sub.call is not None:
            found.add(sub.call)
        found |= _calls(sub)
    return found


def _all(router: APIRouter) -> list[tuple[str, str, APIRoute]]:
    return [
        (method, path, route)
        for path, route in _routes(router, router.prefix)
        for method in sorted(route.methods or ())
    ]


def test_public_router_holds_exactly_the_allowlisted_routes() -> None:
    """Nothing else may be added to the unauthenticated router."""
    assert {(m, p) for m, p, _ in _all(public_v1_router)} == PUBLIC_ROUTES


def test_every_other_v1_route_resolves_a_session_actor() -> None:
    """A route without the actor dependency (and not allowlisted) fails here."""
    routes = _all(api_v1_router)
    assert routes
    missing = []
    for method, path, route in routes:
        if (method, path) in NO_ACTOR_ROUTES:
            continue
        calls = _calls(route.dependant)
        if (method, path) in CONTENT_ACTOR_ROUTES:
            ok = get_current_actor in calls
        elif path.startswith(IDENTITY_PREFIXES):
            ok = bool(calls & IDENTITY_ACTORS)
        else:
            ok = get_current_actor in calls
        if not ok:
            missing.append(f"{method} {path}")
    assert missing == []


def test_unauthenticated_posts_refuse_cross_site_requests() -> None:
    """Every public POST carries the cross-site guard, and nothing else needs it."""
    guarded = {
        (method, path)
        for method, path, route in _all(public_v1_router)
        if refuse_cross_site in _calls(route.dependant)
    }
    public_posts = {(m, p) for m, p in PUBLIC_ROUTES if m == "POST"}
    assert guarded == CROSS_SITE_GUARDED_ROUTES == public_posts


def test_identity_actors_read_only_the_cookie_reader() -> None:
    """Account routes resolve through `get_session_token`, which ignores a bearer."""
    for call in (get_identity_actor, get_active_identity_actor, get_signed_in_user):
        dependant = get_dependant(path="/", call=call)
        assert get_session_token in _calls(dependant)
