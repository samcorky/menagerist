from dataclasses import dataclass

from app.modules.system.domain.readiness import CheckStatus


@dataclass(frozen=True, kw_only=True)
class BrowserRequest:
    """What reached the app on a request sent by an administrator's browser."""

    sec_fetch_site: str | None
    origin: str | None
    seen_origin: str


@dataclass(frozen=True, kw_only=True)
class BrowserCheckResult:
    """Whether the browser's own headers arrived intact."""

    status: CheckStatus
    sec_fetch_site: str | None
    origin: str | None
    seen_origin: str
    output: str | None = None


def assess(request: BrowserRequest) -> BrowserCheckResult:
    """Judge a browser request by the headers that reached the app.

    `same-origin` with a matching (or absent) `Origin` is intact. A differing
    `Origin` means the proxy changes the scheme or host. `Origin` alone is
    accepted, and expected only over plain HTTP, where browsers send no
    `Sec-Fetch-*`, so there it passes; over HTTPS it is a warning. Neither is a
    failure: the app would refuse the request.
    """
    origin = request.origin
    matches = origin == request.seen_origin
    output: str | None
    if request.sec_fetch_site == "same-origin" and (origin is None or matches):
        status, output = CheckStatus.PASS, None
    elif request.sec_fetch_site == "same-origin":
        status = CheckStatus.WARN
        output = (
            "The browser's origin differs from the one the app rebuilt; check "
            + "MENAGERIST_API_TRUSTED_PROXIES and the proxy's Host header."
        )
    elif matches and request.seen_origin.startswith("http://"):
        status = CheckStatus.PASS
        output = (
            "Browsers send no Sec-Fetch-Site over plain HTTP, so the Origin "
            + "header was used instead. This is normal."
        )
    elif matches:
        status = CheckStatus.WARN
        output = (
            "Sec-Fetch-Site did not arrive over HTTPS; the Origin header was "
            + "used instead. A proxy may be removing it."
        )
    else:
        status = CheckStatus.FAIL
        output = (
            "Neither Sec-Fetch-Site nor a matching Origin arrived; a proxy may "
            + "be removing them."
        )
    return BrowserCheckResult(
        status=status,
        sec_fetch_site=request.sec_fetch_site,
        origin=origin,
        seen_origin=request.seen_origin,
        output=output,
    )
