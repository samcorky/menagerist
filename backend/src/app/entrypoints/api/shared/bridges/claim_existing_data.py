"""Hands content that predates accounts to the first administrator.

Implements identity's `ExistingDataClaim` by calling one claim use case per
module, each over its own tables. All of them run on the repositories of one
transaction (the caller's), so the claim commits or rolls back with the setup.
"""

from typing import TYPE_CHECKING, Annotated

from fastapi import Depends

from app.modules.collections.adapters.persistence.unit_of_work import (
    build_collections_repos,
)
from app.modules.collections.application.claim_legacy_collections import (
    ClaimLegacyCollections,
    ClaimLegacyCollectionsCommand,
)
from app.modules.examples.adapters.persistence.unit_of_work import build_example_repos
from app.modules.examples.application.claim_orphaned_installations import (
    ClaimOrphanedInstallations,
    ClaimOrphanedInstallationsCommand,
)
from app.modules.graph.adapters.persistence.unit_of_work import build_graph_repos
from app.modules.graph.application.claim_orphaned_items import (
    ClaimOrphanedItems,
    ClaimOrphanedItemsCommand,
)
from app.modules.identity.adapters.api.dependencies import get_setup_session
from app.modules.identity.ports.existing_data_claim import ClaimReport
from app.modules.media.adapters.persistence.unit_of_work import build_media_repos
from app.modules.media.application.claim_orphaned_media import (
    ClaimOrphanedMedia,
    ClaimOrphanedMediaCommand,
)
from app.shared_kernel.actor import SYSTEM_ACTOR
from app.shared_kernel.unit_of_work import AmbientUnitOfWork

if TYPE_CHECKING:
    import uuid

    from sqlalchemy.ext.asyncio import AsyncSession

    from app.modules.collections.ports.unit_of_work import CollectionsRepos
    from app.modules.examples.ports.unit_of_work import ExampleRepos
    from app.modules.graph.ports.unit_of_work import GraphRepos
    from app.modules.media.ports.unit_of_work import MediaRepos


class ClaimExistingData:
    """`ExistingDataClaim` over the graph, collections, media and examples modules."""

    def __init__(
        self,
        items: ClaimOrphanedItems,
        collections: ClaimLegacyCollections,
        media: ClaimOrphanedMedia,
        installations: ClaimOrphanedInstallations,
    ) -> None:
        self._items = items
        self._collections = collections
        self._media = media
        self._installations = installations

    async def claim(self, owner_id: uuid.UUID) -> ClaimReport:
        """Make `owner_id` the owner of all unowned and legacy-owned content."""
        items = await self._items.handle(
            ClaimOrphanedItemsCommand(owner_id=owner_id), SYSTEM_ACTOR
        )
        collections = await self._collections.handle(
            ClaimLegacyCollectionsCommand(owner_id=owner_id), SYSTEM_ACTOR
        )
        files = await self._media.handle(
            ClaimOrphanedMediaCommand(owner_id=owner_id), SYSTEM_ACTOR
        )
        examples = await self._installations.handle(
            ClaimOrphanedInstallationsCommand(owner_id=owner_id), SYSTEM_ACTOR
        )
        return ClaimReport(
            counts={
                "items": items.items,
                "connections": items.connections,
                "collections": collections,
                "files": files,
                "examples": examples,
            }
        )


def build_claim_existing_data(
    *,
    graph: GraphRepos,
    collections: CollectionsRepos,
    media: MediaRepos,
    examples: ExampleRepos,
) -> ClaimExistingData:
    """Wire the claim over ready repositories, which any storage may back.

    The use cases never commit: the owner of the transaction does.
    """
    return ClaimExistingData(
        ClaimOrphanedItems(AmbientUnitOfWork(graph)),
        ClaimLegacyCollections(AmbientUnitOfWork(collections)),
        ClaimOrphanedMedia(AmbientUnitOfWork(media)),
        ClaimOrphanedInstallations(AmbientUnitOfWork(examples)),
    )


def build_sql_claim_existing_data(session: AsyncSession) -> ClaimExistingData:
    """Wire the claim over SQL repositories on `session`."""
    return build_claim_existing_data(
        graph=build_graph_repos(session),
        collections=build_collections_repos(session),
        media=build_media_repos(session),
        examples=build_example_repos(session),
    )


def get_claim_existing_data(
    session: Annotated[AsyncSession, Depends(get_setup_session)],
) -> ClaimExistingData:
    """Return the claim on the session that first-run setup shares."""
    return build_sql_claim_existing_data(session)
