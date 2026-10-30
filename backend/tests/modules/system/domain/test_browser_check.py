import pytest

from app.modules.system.domain.browser_check import BrowserRequest, assess
from app.modules.system.domain.readiness import CheckStatus

SEEN = "https://menagerist.example"


@pytest.mark.parametrize("origin", [SEEN, None])
def test_same_origin_with_matching_or_no_origin_passes(origin: str | None) -> None:
    """A browser reaching the app with its headers intact is fine."""
    result = assess(
        BrowserRequest(sec_fetch_site="same-origin", origin=origin, seen_origin=SEEN)
    )

    assert result.status is CheckStatus.PASS
    assert result.output is None
    assert (result.sec_fetch_site, result.origin) == ("same-origin", origin)
    assert result.seen_origin == SEEN


def test_same_origin_with_a_different_origin_warns_about_the_proxy() -> None:
    """The proxy changes the scheme or host the app rebuilds."""
    result = assess(
        BrowserRequest(
            sec_fetch_site="same-origin",
            origin=SEEN,
            seen_origin="http://10.0.0.5:8000",
        )
    )

    assert result.status is CheckStatus.WARN
    assert result.output is not None
    assert "MENAGERIST_API_TRUSTED_PROXIES" in result.output


@pytest.mark.parametrize(
    "seen", ["http://192.168.1.198:8080", "http://nas.local", "http://localhost:8000"]
)
def test_origin_alone_over_plain_http_passes(seen: str) -> None:
    """Browsers send no Sec-Fetch-Site over plain HTTP, so Origin alone is normal."""
    result = assess(BrowserRequest(sec_fetch_site=None, origin=seen, seen_origin=seen))

    assert result.status is CheckStatus.PASS
    assert result.output is not None
    assert "plain HTTP" in result.output
    assert "Origin" in result.output


def test_origin_alone_over_https_warns() -> None:
    """Over HTTPS the header should arrive, so a proxy may be removing it."""
    result = assess(BrowserRequest(sec_fetch_site=None, origin=SEEN, seen_origin=SEEN))

    assert result.status is CheckStatus.WARN
    assert result.output is not None
    assert "Sec-Fetch-Site did not arrive" in result.output
    assert "proxy" in result.output


@pytest.mark.parametrize(
    ("site", "origin"), [(None, None), (None, "https://other.example"), ("none", None)]
)
def test_no_usable_header_fails(site: str | None, origin: str | None) -> None:
    """The app would refuse this request."""
    result = assess(
        BrowserRequest(sec_fetch_site=site, origin=origin, seen_origin=SEEN)
    )

    assert result.status is CheckStatus.FAIL
    assert result.output is not None
