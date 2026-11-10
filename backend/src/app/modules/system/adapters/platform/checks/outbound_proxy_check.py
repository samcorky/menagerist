from datetime import UTC, datetime
from typing import TYPE_CHECKING
from urllib.parse import urlsplit

from app.modules.system.adapters.platform.checks._util import observation

if TYPE_CHECKING:
    from collections.abc import Mapping

    from pydantic import SecretStr

    from app.modules.system.domain.readiness import CheckObservation


class OutboundProxyCheck:
    """Reports whether outbound web requests go through a proxy.

    Pure inspection of settings, no I/O. It is informational and always passes: an
    unset proxy is the normal case and reads as a null value. Only the host and port
    of a proxy are shown, never its user name or password. It sends no `output`, which
    is kept for warnings and failures.
    """

    def __init__(
        self,
        *,
        http_proxy: SecretStr | None,
        https_proxy: SecretStr | None,
        no_proxy: str,
    ) -> None:
        self._http = _address(http_proxy)
        self._https = _address(https_proxy)
        self._exempt = len([e for e in no_proxy.split(",") if e.strip()])

    async def run(self) -> Mapping[str, CheckObservation]:
        """Report each proxy, and how many hosts skip it."""
        now = datetime.now(UTC)
        return {
            "configuration:outboundHttpProxy": observation(
                self._http, "proxy", now=now
            ),
            "configuration:outboundHttpsProxy": observation(
                self._https, "proxy", now=now
            ),
            "configuration:outboundNoProxy": observation(
                self._exempt, "exempt hosts", now=now
            ),
        }


def _address(proxy: SecretStr | None) -> str | None:
    """`host:port` of a proxy URL, leaving out any credentials."""
    if proxy is None:
        return None
    parts = urlsplit(proxy.get_secret_value())
    host = parts.hostname or ""
    if ":" in host:
        host = f"[{host}]"
    return f"{host}:{parts.port}" if parts.port else host
