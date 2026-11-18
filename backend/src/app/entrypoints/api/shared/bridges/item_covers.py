"""The graph module's view of covers: thumbnail URLs for a page of items."""

from typing import TYPE_CHECKING, Annotated

from fastapi import Depends

from app.entrypoints.api.shared.access_guard import get_access_guard
from app.modules.media.adapters.api.dependencies import get_media_repos
from app.modules.media.adapters.api.media.schemas import MediaAssetResponse
from app.modules.media.application.list_node_covers import (
    ListNodeCovers,
    ListNodeCoversQuery,
)
from app.modules.media.ports.unit_of_work import MediaRepos  # noqa: TC001
from app.shared_kernel.access_guard import AccessGuard  # noqa: TC001

if TYPE_CHECKING:
    import uuid
    from collections.abc import Sequence

    from app.shared_kernel.actor import Actor


class MediaItemCovers:
    """Finds each item's cover through the media use case, in one lookup."""

    def __init__(self, repos: MediaRepos, guard: AccessGuard) -> None:
        self._covers = ListNodeCovers(repos, guard)

    async def thumbnails(
        self, item_ids: Sequence[uuid.UUID], actor: Actor
    ) -> dict[uuid.UUID, str]:
        """Return where each item's cover thumbnail is served.

        The URL comes from the media API's own response, so it is built in one place.
        """
        covers = await self._covers.handle(
            ListNodeCoversQuery(node_ids=list(item_ids)), actor
        )
        urls = {
            item_id: MediaAssetResponse.from_domain(asset).thumbnail_url
            for item_id, asset in covers.items()
        }
        return {item_id: url for item_id, url in urls.items() if url is not None}


def get_item_covers(
    repos: Annotated[MediaRepos, Depends(get_media_repos)],
    guard: Annotated[AccessGuard, Depends(get_access_guard)],
) -> MediaItemCovers:
    """Provide the cover source for a request."""
    return MediaItemCovers(repos, guard)
