from datetime import UTC, datetime
from typing import TYPE_CHECKING

from app.modules.system.adapters.platform.checks._util import observation
from app.modules.system.domain.readiness import CheckObservation, CheckStatus
from app.platform.config.api import CORS_OPEN_HINT

if TYPE_CHECKING:
    from collections.abc import Mapping, Sequence


class CorsConfigurationCheck:
    """Warns when `MENAGERIST_API_CORS_ORIGINS` allows any origin.

    Pure inspection of a setting, no I/O. It only ever warns: a configuration choice
    must not take the instance out of rotation.
    """

    def __init__(self, origins: Sequence[str]) -> None:
        self._open = "*" in origins

    async def run(self) -> Mapping[str, CheckObservation]:
        """Report whether any origin is allowed."""
        return {
            "configuration:corsOrigins": observation(
                int(self._open),
                "open origins",
                now=datetime.now(UTC),
                status=CheckStatus.WARN if self._open else CheckStatus.PASS,
                output=CORS_OPEN_HINT if self._open else None,
            )
        }
