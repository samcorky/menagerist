"""The same-origin check on cookie-authenticated unsafe requests."""

import pytest
from fastapi import Depends, FastAPI
from starlette.testclient import TestClient
from structlog.testing import capture_logs

from app.entrypoints.api.shared.http import cross_site
from app.entrypoints.api.shared.http.cross_site import refuse_cross_site
from app.entrypoints.api.shared.http.csrf import verify_csrf
from app.entrypoints.api.shared.http.problem_response import register_exception_handlers
from app.platform import proxy_signals
from app.platform.config import get_identity_settings
from app.platform.config.api import ApiSettings
from app.platform.proxy_signals import ProxySignal

BASE = "http://testserver"
SESSION = {"Cookie": f"{get_identity_settings().cookie_name}=secret-session-value"}


@pytest.fixture(autouse=True)
def _clean_signals() -> None:
    proxy_signals.reset()


def _client(base_url: str = BASE) -> TestClient:
    app = FastAPI()

    @app.api_route(
        "/change",
        methods=["GET", "HEAD", "OPTIONS", "POST", "PUT", "PATCH", "DELETE"],
        dependencies=[Depends(verify_csrf)],
    )
    async def change() -> dict[str, bool]:
        return {"ok": True}

    register_exception_handlers(app)
    client = TestClient(app, base_url=base_url)
    client.headers.pop("Origin", None)
    return client


def _send(
    method: str,
    headers: dict[str, str],
    *,
    base_url: str = BASE,
    session: bool = True,
) -> int:
    client = _client(base_url)
    sent = {**(SESSION if session else {}), **headers}
    return client.request(method, "/change", headers=sent).status_code


@pytest.mark.parametrize("method", ["GET", "HEAD", "OPTIONS"])
def test_safe_methods_pass_whatever_the_headers_say(method: str) -> None:
    """Nothing is changed by a safe request, so nothing is checked."""
    headers = {"Sec-Fetch-Site": "cross-site", "Origin": "https://evil.example"}

    assert _send(method, headers) == 200


@pytest.mark.parametrize("method", ["POST", "PUT", "PATCH", "DELETE"])
def test_a_request_without_a_session_cookie_passes(method: str) -> None:
    """With no cookie there is nothing to forge; authentication answers 401."""
    headers = {"Sec-Fetch-Site": "cross-site", "Origin": "https://evil.example"}

    assert _send(method, headers, session=False) == 200


@pytest.mark.parametrize("method", ["POST", "PUT", "PATCH", "DELETE"])
@pytest.mark.parametrize(
    ("headers", "base_url", "allowed"),
    [
        ({"Sec-Fetch-Site": "same-origin"}, BASE, True),
        ({"Sec-Fetch-Site": "same-origin", "Origin": BASE}, BASE, True),
        ({"Sec-Fetch-Site": "same-origin", "Origin": "https://other"}, BASE, True),
        ({"Sec-Fetch-Site": "cross-site"}, BASE, False),
        ({"Sec-Fetch-Site": "cross-site", "Origin": BASE}, BASE, False),
        ({"Sec-Fetch-Site": "same-site", "Origin": BASE}, BASE, True),
        ({"Sec-Fetch-Site": "none", "Origin": BASE}, BASE, True),
        ({"Origin": BASE}, BASE, True),
        ({"Origin": "HTTP://TestServer:80"}, BASE, True),
        ({"Origin": "https://app.example"}, "https://app.example", True),
        ({"Origin": "https://app.example:443"}, "https://app.example", True),
        ({"Origin": "https://App.Example"}, "https://app.example", True),
        ({"Origin": "https://app.example:8443"}, "https://app.example:8443", True),
        ({"Origin": "https://evil.example"}, BASE, False),
        ({"Origin": "http://testserver:8000"}, BASE, False),
        ({"Origin": "https://testserver"}, BASE, False),
        ({"Origin": "http://sub.testserver"}, BASE, False),
        (
            {"Sec-Fetch-Site": "same-site", "Origin": "https://evil.example"},
            BASE,
            False,
        ),
        ({"Sec-Fetch-Site": "none"}, BASE, False),
        ({"Origin": "null"}, BASE, False),
        ({"Origin": "not a url"}, BASE, False),
        ({"Origin": "http://[bad"}, BASE, False),
        ({"Origin": ""}, BASE, False),
        ({}, BASE, False),
    ],
)
def test_unsafe_cookie_requests_follow_the_decision_table(
    method: str, headers: dict[str, str], base_url: str, allowed: bool
) -> None:
    """Sec-Fetch-Site decides first; otherwise Origin must be the app's own."""
    assert _send(method, headers, base_url=base_url) == (200 if allowed else 403)


def test_a_refusal_is_a_csrf_failed_problem() -> None:
    """The problem type and message are stable."""
    response = _client().post("/change", headers={**SESSION, "Origin": "null"})

    assert response.status_code == 403
    body = response.json()
    assert body["type"] == "csrf_failed"
    assert body["detail"] == "This request was not sent from this site's own pages."


def test_a_same_origin_request_with_another_origin_is_noted() -> None:
    """A proxy hiding the scheme or host is recorded, but the request passes."""
    headers = {"Sec-Fetch-Site": "same-origin", "Origin": "https://testserver"}

    assert _send("POST", headers) == 200
    assert proxy_signals.counts()[ProxySignal.ORIGIN_MISMATCH] == 1


def test_a_matching_origin_is_not_noted() -> None:
    """Nothing is recorded when the origins agree."""
    headers = {"Sec-Fetch-Site": "same-origin", "Origin": BASE}

    assert _send("POST", headers) == 200
    assert proxy_signals.counts()[ProxySignal.ORIGIN_MISMATCH] == 0


def test_a_refusal_is_logged_without_cookie_values() -> None:
    """The log names the reason and origins, never the session cookie."""
    with capture_logs() as events:
        _send("POST", {"Origin": "https://evil.example"})

    (event,) = [e for e in events if e["event"] == "cross-site request refused"]
    assert event["reason"] == "origin differs"
    assert event["claimed_origin"] == "https://evil.example"
    assert event["seen_origin"] == BASE
    assert "secret-session-value" not in repr(events)


@pytest.mark.parametrize(
    ("headers", "reason"),
    [
        ({"Sec-Fetch-Site": "cross-site"}, "browser reports cross-site"),
        ({}, "no Sec-Fetch-Site or Origin"),
    ],
)
def test_refusal_reasons_are_logged(headers: dict[str, str], reason: str) -> None:
    """Each refusal path logs its own reason."""
    with capture_logs() as events:
        _send("POST", headers)

    (event,) = [e for e in events if e["event"] == "cross-site request refused"]
    assert event["reason"] == reason


def test_a_listed_cors_origin_is_refused_here_but_passes_sign_in(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The two checks differ on purpose: CORS never carries the session cookie."""
    monkeypatch.setattr(
        cross_site,
        "get_api_settings",
        lambda: ApiSettings(cors_origins=["https://ui.example"]),
    )
    app = FastAPI()

    @app.post("/login", dependencies=[Depends(refuse_cross_site)])
    async def login() -> dict[str, bool]:
        return {"ok": True}

    @app.post("/change", dependencies=[Depends(verify_csrf)])
    async def change() -> dict[str, bool]:
        return {"ok": True}

    register_exception_handlers(app)
    client = TestClient(app, base_url=BASE)
    headers = {"Origin": "https://ui.example"}

    assert client.post("/login", headers=headers).status_code == 200
    assert client.post("/change", headers={**SESSION, **headers}).status_code == 403


def test_over_https_the_prefixed_session_cookie_is_checked() -> None:
    """The check looks for the cookie under the name the session reader uses."""
    prefixed = {"Cookie": f"__Host-Http-{get_identity_settings().cookie_name}=secret"}
    headers = {**prefixed, "Sec-Fetch-Site": "cross-site"}
    client = _client("https://testserver")

    assert client.post("/change", headers=headers).status_code == 403


def test_over_https_a_plain_named_cookie_is_no_session() -> None:
    """A plain-named cookie is never read over HTTPS, so there is nothing to forge."""
    headers = {**SESSION, "Sec-Fetch-Site": "cross-site"}
    client = _client("https://testserver")

    assert client.post("/change", headers=headers).status_code == 200
