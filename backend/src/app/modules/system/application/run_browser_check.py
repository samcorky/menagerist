from dataclasses import dataclass
from typing import TYPE_CHECKING

from app.modules.system.application.permissions import SystemPermission
from app.modules.system.domain.browser_check import (
    BrowserCheckResult,
    BrowserRequest,
    assess,
)
from app.shared_kernel.cqrs import AuthorisedUseCase

if TYPE_CHECKING:
    from app.shared_kernel.actor import Actor


@dataclass(kw_only=True)
class RunBrowserCheckQuery:
    """The headers an administrator's browser sent to the check."""

    request: BrowserRequest


class RunBrowserCheck(
    AuthorisedUseCase[RunBrowserCheckQuery, BrowserCheckResult, SystemPermission]
):
    """Report whether the browser's origin headers reach the app, for administrators."""

    required_permission = SystemPermission.READ_DIAGNOSTICS

    async def _handle(
        self, query: RunBrowserCheckQuery, actor: Actor
    ) -> BrowserCheckResult:
        """Assess the headers; nothing is stored."""
        return assess(query.request)
