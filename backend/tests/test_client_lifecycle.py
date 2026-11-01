import asyncio
from contextlib import asynccontextmanager
from typing import TYPE_CHECKING

from fastapi import FastAPI
from starlette.testclient import TestClient

if TYPE_CHECKING:
    from collections.abc import AsyncIterator


def test_unmanaged_clients_share_a_live_loop_between_requests() -> None:
    """Ordinary router clients must not open an event loop for each request."""
    app = FastAPI()
    loops: list[asyncio.AbstractEventLoop] = []

    @app.get("/")
    async def record_loop() -> None:
        loops.append(asyncio.get_running_loop())

    first = TestClient(app)
    second = TestClient(app)
    for client in (first, second, first):
        assert client.get("/").status_code == 200
    assert all(loop is loops[0] for loop in loops)
    assert not loops[0].is_closed()


def test_explicit_client_context_preserves_lifespan_and_loop_cleanup() -> None:
    """Managed clients still own their startup, shutdown and event loop."""
    events: list[str] = []
    loops: list[asyncio.AbstractEventLoop] = []

    @asynccontextmanager
    async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
        events.append("startup")
        yield
        events.append("shutdown")

    app = FastAPI(lifespan=lifespan)

    @app.get("/")
    async def record_loop() -> None:
        loops.append(asyncio.get_running_loop())

    unmanaged = TestClient(app)
    assert unmanaged.get("/").status_code == 200
    assert events == []
    with TestClient(app) as managed:
        assert events == ["startup"]
        for _ in range(2):
            assert managed.get("/").status_code == 200
        assert loops[1] is loops[2]
        assert loops[1] is not loops[0]
        assert not loops[1].is_closed()
    assert events == ["startup", "shutdown"]
    assert loops[1].is_closed()
    assert unmanaged.get("/").status_code == 200
    assert loops[3] is loops[0]
