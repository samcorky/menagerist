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
        """Report the signals seen in the last hour."""
        now = datetime.now(UTC)
        seen = proxy_signals.counts(now=now)
        total = sum(seen.values())
        output = (
            " ".join(
                proxy_signals.HINTS[signal] for signal, count in seen.items() if count
            )
            or None
        )
        return {
            "proxy:configuration": observation(
                total,
                "flagged requests",
                now=now,
                status=CheckStatus.WARN if total else CheckStatus.PASS,
                output=output,
            )
        }
