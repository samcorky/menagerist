"""Graph search conditions over other modules' data: media and collections.

Graph defines the questions (`ExternalConditions`, `CollectionDefinitions`);
this bridge answers them from the media and collections tables. Both are
correlated `EXISTS` subqueries, so they use the attachment `target_id` and
membership `item_id` indexes and never ship item ids around.
"""

from typing import TYPE_CHECKING, Literal

from sqlalchemy import ColumnElement, exists, not_, select

from app.modules.collections.adapters.persistence.models import (
    CollectionMemberModel,
    CollectionModel,
)
from app.modules.collections.adapters.persistence.unit_of_work import (
    build_collections_repos,
)
from app.modules.collections.domain.collection import CollectionKind
from app.modules.graph.adapters.persistence.models import NodeModel
from app.modules.graph.adapters.persistence.unit_of_work import build_graph_repos
from app.modules.graph.ports.collection_definitions import CollectionDefinition
from app.modules.media.adapters.persistence.models import (
    MediaAssetModel,
    MediaAttachmentModel,
)
from app.modules.media.domain.media_asset import MediaStatus
from app.modules.media.domain.media_attachment import AttachmentTarget
from app.platform.orm_mixins import owned_by

if TYPE_CHECKING:
    import uuid
    from collections.abc import Sequence

    from sqlalchemy.ext.asyncio import AsyncSession

    from app.modules.collections.ports.unit_of_work import CollectionsRepos
    from app.modules.graph.ports.unit_of_work import GraphRepos
    from app.shared_kernel.content_filter import ContentFilter

_IMAGE = "image/%"


class SqlExternalConditions:
    """SQL predicates for the media and manual-collection search conditions.

    Only the SQL side lives here: Postgres is the only SQL engine, and the
    in-memory evaluator uses `InMemoryExternalConditions` instead.
    """

    def media_predicate(
        self,
        mode: Literal["has", "none"],
        type: Literal["image", "document"] | None,
        scope: ContentFilter,
    ) -> ColumnElement[bool]:
        """The item has (or has no) attached, ready media owned inside `scope`.

        Any attribute key counts. Thumbnails are not separate assets, and staged
        or orphaned assets are not ready, so none of them count.
        """
        conditions = [
            MediaAssetModel.id == MediaAttachmentModel.asset_id,
            MediaAttachmentModel.target_type == AttachmentTarget.NODE.value,
            MediaAttachmentModel.target_id == NodeModel.id,
            MediaAssetModel.status == MediaStatus.ATTACHED.value,
            owned_by(MediaAssetModel, scope.user_id),
        ]
        if type == "image":
            conditions.append(MediaAssetModel.content_type.like(_IMAGE))
        elif type == "document":
            conditions.append(MediaAssetModel.content_type.not_like(_IMAGE))
        has_media = exists(
            select(1)
            .select_from(MediaAttachmentModel, MediaAssetModel)
            .where(*conditions)
        )
        return has_media if mode == "has" else not_(has_media)

    def media_matches(self, *_args: object) -> bool:
        """Not available: the in-memory evaluator has its own source."""
        raise NotImplementedError

    def collection_predicate(
        self, collection_ids: Sequence[uuid.UUID], scope: ContentFilter
    ) -> ColumnElement[bool]:
        """The item is on any of these live collections owned inside `scope`."""
        return exists(
            select(1)
            .select_from(CollectionMemberModel, CollectionModel)
            .where(
                CollectionModel.id == CollectionMemberModel.collection_id,
                CollectionMemberModel.item_id == NodeModel.id,
                CollectionMemberModel.collection_id.in_(collection_ids),
                CollectionModel.deleted_at.is_(None),
                owned_by(CollectionModel, scope.user_id),
            )
        )

    def collection_matches(self, *_args: object) -> bool:
        """Not available: the in-memory evaluator has its own source."""
        raise NotImplementedError


class CollectionsDefinitions:
    """Reads a collection's kind and stored search from the collections module."""

    def __init__(self, repos: CollectionsRepos) -> None:
        self._repos = repos

    async def get(
        self, collection_id: uuid.UUID, scope: ContentFilter
    ) -> CollectionDefinition | None:
        """Return the live collection in `scope`, or None.

        A smart collection always has a definition; one without would match
        nothing.
        """
        collection = await self._repos.collections.get(collection_id, scope=scope)
        if collection is None:
            return None
        if collection.kind is CollectionKind.DYNAMIC:
            return CollectionDefinition(definition=collection.definition or {})
        return CollectionDefinition(definition=None)


def build_search_graph_repos(session: AsyncSession) -> GraphRepos:
    """Graph repositories whose searches understand media and collection conditions."""
    external = SqlExternalConditions()
    return build_graph_repos(
        session,
        external=external,
        definitions=CollectionsDefinitions(build_collections_repos(session)),
    )
