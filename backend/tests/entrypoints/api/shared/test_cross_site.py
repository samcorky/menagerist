"""The cross-site guard on the public sign-in and setup routes."""

import pytest
import structlog
from fastapi import Depends, FastAPI
from starlette.testclient import TestClient
from structlog.testing import capture_logs

from app.entrypoints.api.shared import cross_site
from app.entrypoints.api.shared.cross_site import refuse_cross_site
from app.entrypoints.api.shared.problem_response import register_exception_handlers
from app.platform import proxy_signals
from app.platform.config.api import ApiSettings
from app.platform.proxy_signals import ProxySignal


@pytest.fixture(autouse=True)
def _clean_signals() -> None:
    proxy_signals.reset()


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
        # The browser's word beats a proxy that hides the scheme from the app.
        (
            {"Sec-Fetch-Site": "same-origin", "Origin": "https://testserver"},
            [],
            "http://testserver",
            True,
        ),
        (
            {"Sec-Fetch-Site": "same-origin", "Origin": "null"},
            [],
            "http://testserver",
            True,
        ),
        # Without that word the Origin must match, as before.
        (
            {"Sec-Fetch-Site": "same-site", "Origin": "http://testserver"},
            [],
            "http://testserver",
            True,
        ),
        (
            {"Sec-Fetch-Site": "same-site", "Origin": "https://sibling.example"},
            [],
            "http://testserver",
            False,
        ),
        (
            {"Sec-Fetch-Site": "none", "Origin": "https://testserver"},
            [],
            "http://testserver",
            False,
        ),
        # An unparseable Origin is refused, not a server error.
        ({"Origin": "http://["}, [], "http://testserver", False),
        (
            {"Sec-Fetch-Site": "same-origin", "Origin": "http://["},
            [],
            "http://testserver",
            False,
        ),
        (
            {"Sec-Fetch-Site": "bogus", "Origin": "https://evil.example"},
            [],
            "http://testserver",
            False,
        ),
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


def test_a_same_origin_request_with_another_origin_is_noted(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The proxy's scheme is not reaching the app: let it through, but say so."""
    headers = {"Sec-Fetch-Site": "same-origin", "Origin": "https://testserver"}

    response = _client(monkeypatch, [], "http://testserver").post(
        "/guarded", headers=headers
    )

    assert response.status_code == 200
    assert proxy_signals.counts()[ProxySignal.ORIGIN_MISMATCH] == 1


@pytest.mark.parametrize(
    "headers",
    [
        {"Sec-Fetch-Site": "same-origin", "Origin": "http://testserver"},
        {"Sec-Fetch-Site": "same-origin"},
        {"Origin": "http://testserver"},
        {"Sec-Fetch-Site": "cross-site", "Origin": "https://evil.example"},
    ],
)
def test_other_requests_are_not_noted(
    monkeypatch: pytest.MonkeyPatch, headers: dict[str, str]
) -> None:
    """Only a same-origin browser with a different origin counts as a signal."""
    _client(monkeypatch, [], "http://testserver").post("/guarded", headers=headers)

    assert proxy_signals.counts()[ProxySignal.ORIGIN_MISMATCH] == 0


def test_a_refusal_is_logged_with_the_origins_involved(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The log names the claimed and seen origins, with control codes escaped."""
    monkeypatch.setattr(cross_site, "logger", structlog.get_logger())
    headers = {"Sec-Fetch-Site": "same-site", "Origin": "https://evil.example\x1bX"}

    with capture_logs() as logs:
        response = _client(monkeypatch, [], "http://testserver").post(
            "/guarded", headers=headers
        )

    assert response.status_code == 403
    [entry] = [e for e in logs if e["event"] == "cross-site request refused"]
    assert entry["seen_origin"] == "http://testserver"
    assert entry["sec_fetch_site"] == "same-site"
    assert "\x1b" not in entry["claimed_origin"]
