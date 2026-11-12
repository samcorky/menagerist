import json

from pydantic import SecretStr

from app.modules.system.adapters.platform.checks.outbound_proxy_check import (
    OutboundProxyCheck,
)
from app.modules.system.domain.readiness import CheckStatus

HTTP = "configuration:outboundHttpProxy"
HTTPS = "configuration:outboundHttpsProxy"
EXEMPT = "configuration:outboundProxyExemptions"


def _check(
    http: str | None = None, https: str | None = None, no_proxy: str = ""
) -> OutboundProxyCheck:
    return OutboundProxyCheck(
        http_proxy=SecretStr(http) if http else None,
        https_proxy=SecretStr(https) if https else None,
        no_proxy=no_proxy,
    )


async def test_no_proxy_reports_nothing_at_all() -> None:
    """No proxy is the normal case: the rows are left out, exemptions included."""
    assert await _check().run() == {}
    assert await _check(no_proxy="localhost, .internal").run() == {}


async def test_a_proxy_shows_its_host_and_port_and_still_passes() -> None:
    """A configured proxy is informational, with the note about local checks."""
    result = await _check(
        http="http://proxy.example:3128", https="http://other.example"
    ).run()

    assert {o.status for o in result.values()} == {CheckStatus.PASS}
    assert result[HTTP].observed_value == "proxy.example:3128"
    assert result[HTTPS].observed_value == "other.example"
    assert all(o.output is None for o in result.values())


async def test_one_scheme_alone_is_reported_on_its_own() -> None:
    """Only the scheme that has a proxy shows one."""
    result = await _check(https="http://[::1]:8080").run()

    assert set(result) == {HTTP, HTTPS, EXEMPT}
    assert result[HTTP].observed_value is None
    assert result[HTTPS].observed_value == "[::1]:8080"


async def test_credentials_in_the_proxy_url_never_appear() -> None:
    """A user name and password are secrets: neither may reach the report."""
    result = await _check(
        http="http://alice:hunter2@proxy.example:3128",
        https="http://bob:s3cret@proxy.example:3128/path?token=abc",
    ).run()

    text = json.dumps(
        [(k, o.observed_value, o.output) for k, o in result.items()],
    )
    for secret in ("alice", "hunter2", "bob", "s3cret", "token", "/path"):
        assert secret not in text
    assert result[HTTP].observed_value == "proxy.example:3128"


async def test_no_proxy_counts_its_entries() -> None:
    """Blank entries are ignored, as when the exemptions are applied."""
    result = await _check(
        http="http://proxy.example:3128", no_proxy="localhost, .internal,, 10.0.0.0/8 "
    ).run()

    assert result[EXEMPT].observed_value == 3
    assert result[EXEMPT].output is None
