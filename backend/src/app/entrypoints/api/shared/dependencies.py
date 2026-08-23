import uuid
from typing import TYPE_CHECKING

from app.entrypoints.api.shared.authorization import AllowAllAuthorizationAdapter
from app.shared_kernel.actor import Actor

if TYPE_CHECKING:
    from app.shared_kernel.authorization import AuthorizationPort

_V1_OWNER_ACTOR = Actor(id=uuid.UUID(int=1), roles=frozenset({"owner"}))
_authorization_port = AllowAllAuthorizationAdapter()


def get_current_actor() -> Actor:
    """Resolve the actor driving the current request.

    v1 is single-owner with no authentication, so this always returns a
    fixed owner actor. Once OIDC lands, this decodes the actor from the
    request's token/session instead - every route that already depends on
    `Actor` needs no change.
    """
    return _V1_OWNER_ACTOR


def get_authorization_port() -> AuthorizationPort:
    """Return the process-wide `AuthorizationPort` adapter."""
    return _authorization_port
