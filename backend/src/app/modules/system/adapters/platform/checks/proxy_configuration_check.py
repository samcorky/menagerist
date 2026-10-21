from datetime import UTC, datetime
from typing import TYPE_CHECKING

from app.modules.system.adapters.platform.checks._util import observation
from app.modules.system.domain.readiness import CheckObservation, CheckStatus
from app.platform import proxy_signals

if TYPE_CHECKING:
    from collections.abc import Mapping


class ProxyConfigurationCheck:
    """Warns when recent requests suggest the reverse-proxy setup is wrong.

    Pure in-process introspection, no I/O. It only ever warns: a configuration
    problem must not take the instance out of rotation.
    """

    async def run(self) -> Mapping[str, CheckObservation]:
        """Report each signal seen in the last hour as its own observation."""
        now = datetime.now(UTC)
        return {
            f"configuration:proxy{_camel(signal)}": observation(
                count,
                "flagged requests",
                now=now,
                status=CheckStatus.WARN if count else CheckStatus.PASS,
                output=proxy_signals.HINTS[signal] if count else None,
            )
            for signal, count in proxy_signals.counts(now=now).items()
        }


def _camel(signal: proxy_signals.ProxySignal) -> str:
    """`untrusted_forwarding` -> `UntrustedForwarding`."""
    return signal.value.title().replace("_", "")
