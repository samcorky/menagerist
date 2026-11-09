import uuid
from typing import TYPE_CHECKING

from app.entrypoints.api.shared.bridges.preset_usage import GraphPresetUsage
from app.modules.graph.adapters.persistence.unit_of_work import (
    build_in_memory_graph_repos,
)
from app.modules.graph.domain.edge_type import EdgeType
from app.modules.graph.domain.node_type import NodeType

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


async def test_a_viewer_sees_their_own_labels_and_only_a_count_of_the_rest() -> None:
    """Another person's type is counted, never named, in the in-use message."""
    usage = GraphPresetUsage(await _repos(), viewer=ALICE)

    labels = await usage.types_using(LIST_ID)

    assert labels == ["Film", "2 types belonging to other people"]
    assert not any("Secret" in label or "Hides" in label for label in labels)


async def test_a_single_foreign_type_reads_in_the_singular() -> None:
    """One foreign type is described as one."""
    repos = await _repos()
    usage = GraphPresetUsage(repos, viewer=BOB)

    assert await usage.types_using(LIST_ID) == [
        "Secret Diaries",
        "Hides",
        "1 type belonging to another person",
    ]


async def test_a_list_nobody_uses_has_no_usage() -> None:
    """Nothing links to an unknown list."""
    assert (
        await GraphPresetUsage(await _repos(), viewer=ALICE).types_using(
            uuid.UUID(int=8)
        )
        == []
    )


async def test_a_system_check_names_everything_for_the_retention_purge() -> None:
    """With no viewer (the retention purge) any use at all is reported."""
    labels = await GraphPresetUsage(await _repos()).types_using(LIST_ID)

    assert len(labels) == 3
