"""The router-test fixtures: default member, explicit `as_user`."""

import uuid
from typing import TYPE_CHECKING, Annotated

from fastapi import Depends
from starlette.testclient import TestClient

from app.entrypoints.api import create_app
from app.entrypoints.api.shared.dependencies import get_current_actor
from app.shared_kernel.actor import Actor  # noqa: TC001

if TYPE_CHECKING:
    from collections.abc import Callable

    from fastapi import FastAPI


def _app() -> FastAPI:
    app = create_app()

    @app.get("/api/v1/_probe")
    async def probe(
        actor: Annotated[Actor, Depends(get_current_actor)],
    ) -> dict[str, object]:
        return {"id": str(actor.id), "roles": sorted(actor.roles)}

    return app


def test_clients_default_to_member_one() -> None:
    """Clients default to member one."""
    body = TestClient(_app()).get("/api/v1/_probe").json()
    assert body == {"id": str(uuid.UUID(int=1)), "roles": ["member"]}


def test_as_user_switches_the_actor(as_user: Callable[..., None]) -> None:
    """As user switches the actor."""
    app = _app()
    user_id = uuid.uuid4()
    as_user(app, user_id, "admin")
    body = TestClient(app).get("/api/v1/_probe").json()
    assert body == {"id": str(user_id), "roles": ["admin"]}
