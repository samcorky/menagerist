from dataclasses import dataclass
from typing import TYPE_CHECKING, ClassVar

from app.modules.system.application.permissions import SystemPermission
from app.modules.system.domain.browser_check import (
    BrowserCheckResult,
    BrowserRequest,
    assess,
)
from app.shared_kernel.access import Access, Requires
from app.shared_kernel.access_guard import AccessGuard  # noqa: TC001
from app.shared_kernel.guarded import GuardedUseCase

if TYPE_CHECKING:
    from app.shared_kernel.actor import Actor


@dataclass(kw_only=True)
class RunBrowserCheckQuery:
    """The headers an administrator's browser sent to the check."""

    request: BrowserRequest


class RunBrowserCheck(GuardedUseCase[RunBrowserCheckQuery, BrowserCheckResult]):
    """Report whether the browser's origin headers reach the app, for administrators."""

    access: ClassVar[Access] = Requires(SystemPermission.READ_DIAGNOSTICS)

    def __init__(self, guard: AccessGuard) -> None:
        self._guard = guard

    async def _handle(
        self, query: RunBrowserCheckQuery, actor: Actor
    ) -> BrowserCheckResult:
        """Assess the headers; nothing is stored."""
        return assess(query.request)
