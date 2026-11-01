from typing import TYPE_CHECKING

import pytest
from starlette.testclient import TestClient

from app.entrypoints.api.application import create_app
from app.platform import proxy_signals
from app.platform.config import get_api_settings
from app.platform.proxy_signals import ProxySignal

if TYPE_CHECKING:
    from collections.abc import Iterator


@pytest.fixture(autouse=True)
def _clean() -> Iterator[None]:
    proxy_signals.reset()
    get_api_settings.cache_clear()
    yield
    get_api_settings.cache_clear()


def test_a_configured_public_origin_watches_requests(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """With the setting present, a request at another address is flagged."""
    monkeypatch.setenv("MENAGERIST_API_PUBLIC_ORIGIN", "https://menagerist.example.com")

    TestClient(create_app()).get("/api/v1/no-such-route")

    assert proxy_signals.counts()[ProxySignal.INSECURE_ORIGIN] == 1


def test_without_a_public_origin_nothing_is_watched(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The default install records nothing about addresses."""
    monkeypatch.delenv("MENAGERIST_API_PUBLIC_ORIGIN", raising=False)

    TestClient(create_app()).get("/api/v1/no-such-route")

    assert not any(proxy_signals.counts().values())
