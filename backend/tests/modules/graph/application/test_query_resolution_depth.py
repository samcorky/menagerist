"""Resolving a connection that follows a relationship through several hops."""

import uuid
from datetime import date
from typing import TYPE_CHECKING

import pytest

from app.modules.graph.adapters.persistence.unit_of_work import (
    build_in_memory_graph_repos,
)
from app.modules.graph.application.prepare_query import prepare_query
from app.modules.graph.domain.edge_type import EdgeType
from app.modules.graph.domain.query import RelationshipInfo
from app.shared_kernel.content_filter import ContentFilter

if TYPE_CHECKING:
    from app.modules.graph.ports.unit_of_work import GraphRepos

ALICE = uuid.UUID(int=1)
TODAY = date(2026, 11, 15)
SCOPE = ContentFilter.of(ALICE)


def _query(relationship: str) -> dict[str, object]:
    condition = {
        "kind": "connection",
        "mode": "exists",
        "relationship": relationship,
        "direction": "out",
        "depth": 3,
    }
    return {"v": 1, "where": {"op": "and", "children": [condition]}}


@pytest.fixture
async def repos() -> GraphRepos:
    """A directional and a non-directional relationship."""
    built = build_in_memory_graph_repos()
    await built.edge_types.add(
        EdgeType.create(owner_id=ALICE, slug="contains", label="Contains")
    )
    await built.edge_types.add(
        EdgeType.create(
            owner_id=ALICE, slug="related", label="Related", directional=False
        )
    )
    return built


async def test_a_directional_relationship_resolves_for_several_hops(
    repos: GraphRepos,
) -> None:
    """Following a directional relationship deeper is fine."""
    resolved, warnings = await prepare_query(
        repos, _query("contains"), TODAY, scope=SCOPE
    )
    assert resolved.relationships == {
        "contains": RelationshipInfo(slug="contains", directional=True)
    }
    assert warnings == []


async def test_a_non_directional_relationship_cannot_be_followed_deeper(
    repos: GraphRepos,
) -> None:
    """It warns and, left out of `relationships`, matches nothing."""
    resolved, warnings = await prepare_query(
        repos, _query("related"), TODAY, scope=SCOPE
    )
    assert resolved.relationships == {}
    assert [w.path for w in warnings] == ["where.children[0]"]
    assert "related" in warnings[0].message
