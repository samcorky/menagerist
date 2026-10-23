"""Integration tests for the media and collection predicates over Postgres."""

import uuid
from datetime import UTC, date, datetime
from typing import TYPE_CHECKING, Any

import pytest
from sqlalchemy import select, text

from app.entrypoints.api.shared.bridges.collection_conditions import (
    build_search_graph_repos,
)
from app.modules.collections.adapters.persistence.collection_repository import (
    SqlAlchemyCollectionRepository,
)
from app.modules.collections.domain.collection import Collection
from app.modules.graph.adapters.persistence.models import NodeModel
from app.modules.graph.adapters.persistence.query_env import QueryEnv
from app.modules.graph.adapters.persistence.query_sql import compile_where
from app.modules.graph.application.prepare_query import prepare_query
from app.modules.graph.domain.node import Node
from app.modules.media.adapters.persistence.models import (
    MediaAssetModel,
    MediaAttachmentModel,
)
from app.shared_kernel.content_filter import ContentFilter
from app.shared_kernel.slug import Slug

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

    from app.modules.graph.ports.unit_of_work import GraphRepos

pytestmark = pytest.mark.integration

ME = uuid.UUID(int=1)
THEM = uuid.UUID(int=2)
NOW = datetime(2026, 10, 18, tzinfo=UTC)


async def _collection(
    session: AsyncSession,
    owner: uuid.UUID,
    name: str,
    definition: dict[str, Any] | None = None,
    *,
    deleted: bool = False,
) -> Collection:
    collection = Collection.create(
        name=name, slug=Slug(name), owner_id=owner, definition=definition
    )
    if deleted:
        collection.soft_delete()
    await SqlAlchemyCollectionRepository(session).add(collection)
    return collection


async def test_definitions_report_kind_and_hide_what_is_not_the_callers(
    db_session: AsyncSession,
) -> None:
    """A manual collection has no definition; deleted and foreign ones are None."""
    repos = build_search_graph_repos(db_session)
    definitions = repos.definitions
    assert definitions is not None
    stored = {"v": 1, "where": None}
    manual = await _collection(db_session, ME, "manual")
    smart = await _collection(db_session, ME, "smart", stored)
    gone = await _collection(db_session, ME, "gone", deleted=True)
    theirs = await _collection(db_session, THEM, "theirs")
    scope = ContentFilter.of(ME)

    got_manual = await definitions.get(manual.id, scope)
    got_smart = await definitions.get(smart.id, scope)

    assert got_manual is not None
    assert got_manual.definition is None
    assert got_smart is not None
    assert got_smart.definition == stored
    assert await definitions.get(gone.id, scope) is None
    assert await definitions.get(theirs.id, scope) is None
    assert await definitions.get(uuid.uuid7(), scope) is None
    everyone = await definitions.get(theirs.id, ContentFilter.everyone())
    assert everyone is not None


async def _explain(
    session: AsyncSession, repos: GraphRepos, raw: dict[str, Any], node_id: uuid.UUID
) -> str:
    """The plan for the condition on one item, as a paged lookup would probe it."""
    scope = ContentFilter.of(ME)
    resolved, _ = await prepare_query(repos, raw, date(2026, 10, 18), scope=scope)
    where = compile_where(resolved, QueryEnv(scope=scope, external=repos.external))
    assert where is not None
    statement = select(NodeModel.id).where(NodeModel.id == node_id, where)
    await session.execute(text("ANALYZE"))
    await session.execute(text("SET LOCAL enable_seqscan = off"))
    compiled = statement.compile(
        dialect=session.bind.dialect,
        compile_kwargs={"literal_binds": True},
    )
    result = await session.execute(text(f"EXPLAIN {compiled}"))
    return "\n".join(row[0] for row in result)


async def test_media_condition_uses_the_attachment_target_index(
    db_session: AsyncSession,
) -> None:
    """The `EXISTS` probes `media_attachments` by `target_id`, not by scanning."""
    repos = build_search_graph_repos(db_session)
    first = uuid.uuid7()
    for number in range(30):
        node = Node.create(owner_id=ME, name=f"n{number}", type="thing")
        node.id = first if number == 0 else node.id
        await repos.nodes.add(node)
        asset_id = uuid.uuid7()
        db_session.add(
            MediaAssetModel(
                id=asset_id,
                owner_id=ME,
                filename="a.png",
                content_type="image/png",
                size=1,
                sha256="0" * 64,
                status="attached",
                created_at=NOW,
                updated_at=NOW,
            )
        )
        await db_session.flush()
        db_session.add(
            MediaAttachmentModel(
                id=uuid.uuid7(),
                asset_id=asset_id,
                target_type="node",
                target_id=node.id,
                attribute_key=None,
                created_at=NOW,
                updated_at=NOW,
            )
        )

    plan = await _explain(
        db_session,
        repos,
        {
            "v": 1,
            "where": {"op": "and", "children": [{"kind": "media", "mode": "has"}]},
        },
        first,
    )

    assert "ix_media_attachments_target_id" in plan, plan


async def test_collection_condition_uses_the_membership_key(
    db_session: AsyncSession,
) -> None:
    """The `EXISTS` probes `collection_members` by key, not by scanning."""
    repos = build_search_graph_repos(db_session)
    collection = await _collection(db_session, ME, "mine")
    condition = {"kind": "collection", "mode": "any", "in": [str(collection.id)]}

    plan = await _explain(
        db_session,
        repos,
        {"v": 1, "where": {"op": "and", "children": [condition]}},
        uuid.uuid7(),
    )

    assert "collection_members" in plan
    assert "Seq Scan on collection_members" not in plan, plan
