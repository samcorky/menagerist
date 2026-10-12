"""The cross-site guard on the public sign-in and setup routes."""

import pytest
from fastapi import Depends, FastAPI
from starlette.testclient import TestClient

from app.entrypoints.api.shared import cross_site
from app.entrypoints.api.shared.cross_site import refuse_cross_site
from app.entrypoints.api.shared.problem_response import register_exception_handlers
from app.platform.config.api import ApiSettings


def _client(
    monkeypatch: pytest.MonkeyPatch, cors: list[str], base_url: str
) -> TestClient:
    app = FastAPI()

    @app.post("/guarded", dependencies=[Depends(refuse_cross_site)])
    async def guarded() -> dict[str, bool]:
        return {"ok": True}

    register_exception_handlers(app)
    monkeypatch.setattr(
        cross_site, "get_api_settings", lambda: ApiSettings(cors_origins=cors)
    )
    return TestClient(app, base_url=base_url)


@pytest.mark.parametrize(
    ("headers", "cors", "base_url", "allowed"),
    [
        ({}, ["*"], "http://testserver", True),
        ({"Origin": "http://testserver"}, [], "http://testserver", True),
        ({"Origin": "HTTP://TestServer:80"}, [], "http://testserver", True),
        ({"Origin": "https://app.example:8443"}, [], "https://app.example:8443", True),
        ({"Origin": "https://evil.example"}, ["*"], "http://testserver", False),
        ({"Origin": "https://evil.example"}, [], "http://testserver", False),
        (
            {"Origin": "https://ui.example"},
            ["https://ui.example"],
            "http://testserver",
            True,
        ),
        ({"Origin": "null"}, ["*"], "http://testserver", False),
        ({"Origin": "https://testserver"}, [], "http://testserver", False),
        ({"Sec-Fetch-Site": "cross-site"}, ["*"], "http://testserver", False),
        (
            {"Sec-Fetch-Site": "cross-site", "Origin": "http://testserver"},
            [],
            "http://testserver",
            False,
        ),
        ({"Sec-Fetch-Site": "same-origin"}, [], "http://testserver", True),
        ({"Sec-Fetch-Site": "same-site"}, [], "http://testserver", True),
        ({"Sec-Fetch-Site": "none"}, [], "http://testserver", True),
    ],
)
def test_guard_decisions(
    monkeypatch: pytest.MonkeyPatch,
    headers: dict[str, str],
    cors: list[str],
    base_url: str,
    allowed: bool,
) -> None:
    """Cross-site requests are refused; own-origin, listed and header-less pass."""
    response = _client(monkeypatch, cors, base_url).post("/guarded", headers=headers)

    if allowed:
        assert response.status_code == 200
    else:
        assert response.status_code == 403
        assert response.headers["content-type"].startswith("application/problem+json")
        body = response.json()
        assert body["type"] == "cross_site_refused"
        assert body["detail"] == "This request was sent from another site."
