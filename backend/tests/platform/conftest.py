import pytest

_PROXY_VARIABLES = ("HTTP_PROXY", "HTTPS_PROXY", "NO_PROXY")


@pytest.fixture(autouse=True)
def _no_proxy_in_the_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    """Outbound settings read the standard proxy names; keep a machine's own out."""
    for name in _PROXY_VARIABLES:
        monkeypatch.delenv(name, raising=False)
        monkeypatch.delenv(name.lower(), raising=False)
