from dataclasses import dataclass
from typing import TYPE_CHECKING, ClassVar

from app.modules.system.domain.web_app_manifest import WebAppManifest
from app.shared_kernel.access import Access, Public
from app.shared_kernel.access_guard import AccessGuard  # noqa: TC001
from app.shared_kernel.cqrs import UseCase

if TYPE_CHECKING:
    from app.shared_kernel.actor import Actor


@dataclass(kw_only=True)
class GetWebAppManifestQuery:
    """Request for the manifest that lets browsers install the instance as an app."""


class GetWebAppManifest(UseCase[GetWebAppManifestQuery, WebAppManifest]):
    """Describe the instance for installation; it must hold nothing private."""

    access: ClassVar[Access] = Public()

    def __init__(self, guard: AccessGuard, *, public_origin: str | None) -> None:
        self._guard = guard
        self._public_origin = public_origin

    async def _handle(
        self, query: GetWebAppManifestQuery, actor: Actor
    ) -> WebAppManifest:
        """Return the manifest, with URLs on the public origin when one is set."""
        return WebAppManifest(origin=self._public_origin)
