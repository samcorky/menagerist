import uuid
from typing import TYPE_CHECKING

from app.entrypoints.api.shared.bridges.preset_usage import GraphPresetUsage
from app.modules.graph.adapters.persistence.unit_of_work import (
    build_in_memory_graph_repos,
)
from app.modules.graph.domain.edge_type import EdgeType
from app.modules.graph.domain.node_type import NodeType
from app.shared_kernel.content_filter import ContentFilter

if TYPE_CHECKING:
    from app.modules.graph.ports.unit_of_work import GraphRepos

ALICE = uuid.UUID(int=101)
BOB = uuid.UUID(int=102)
LIST_ID = uuid.UUID(int=7)
SCHEMA = {"properties": {"genre": {"x-menagerist": {"list": str(LIST_ID)}}}}


async def _repos() -> GraphRepos:
    repos = build_in_memory_graph_repos()
    await repos.node_types.add(
        NodeType.create(
            owner_id=ALICE, slug="film", label="Film", attributes_schema=SCHEMA
        )
    )
    await repos.node_types.add(
        NodeType.create(
            owner_id=BOB, slug="diary", label="Secret Diaries", attributes_schema=SCHEMA
        )
    )
    await repos.edge_types.add(
        EdgeType.create(
            owner_id=BOB, slug="hides", label="Hides", attributes_schema=SCHEMA
        )
    )
    return repos


async def test_a_viewer_is_told_only_about_their_own_types() -> None:
    """Another person's type is neither named nor counted."""
    usage = GraphPresetUsage(await _repos(), scope=ContentFilter.of(ALICE))

    assert await usage.types_using(LIST_ID) == ["Film"]


async def test_both_kinds_of_type_are_reported() -> None:
    """Item types and relationship types of the viewer both count."""
    usage = GraphPresetUsage(await _repos(), scope=ContentFilter.of(BOB))

    assert await usage.types_using(LIST_ID) == ["Secret Diaries", "Hides"]


async def test_a_list_nobody_uses_has_no_usage() -> None:
    """Nothing links to an unknown list."""
    usage = GraphPresetUsage(await _repos(), scope=ContentFilter.of(ALICE))

    assert await usage.types_using(uuid.UUID(int=8)) == []


async def test_an_unrestricted_check_sees_every_owner_for_the_retention_purge() -> None:
    """The purge asks with no restriction: any use at all is reported."""
    usage = GraphPresetUsage(await _repos(), scope=ContentFilter.everyone())

    assert len(await usage.types_using(LIST_ID)) == 3
