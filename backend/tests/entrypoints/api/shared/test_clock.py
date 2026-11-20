"""The request's "today" follows the `Time-Zone` header; smart collections use it."""

import uuid
from datetime import UTC, date, datetime, timedelta
from types import SimpleNamespace
from typing import Any
from zoneinfo import ZoneInfo

import pytest

from app.entrypoints.api.shared.bridges.collection_items import GraphItemLookup
from app.entrypoints.api.shared.clock import get_today, today_in, zone_named
from app.modules.graph.adapters.persistence.in_memory_edge_repository import (
    InMemoryEdgeRepository,
)
from app.modules.graph.adapters.persistence.in_memory_edge_type_repository import (
    InMemoryEdgeTypeRepository,
)
from app.modules.graph.adapters.persistence.in_memory_node_repository import (
    InMemoryNodeRepository,
)
from app.modules.graph.adapters.persistence.in_memory_node_type_repository import (
    InMemoryNodeTypeRepository,
)
from app.modules.graph.domain.node import Node
from app.modules.graph.domain.node_type import NodeType
from app.modules.graph.ports.unit_of_work import GraphRepos
from app.shared_kernel.content_filter import ContentFilter

OWNER = uuid.UUID(int=1)


@pytest.mark.parametrize(
    "name", ["Europe/London", "Asia/Tokyo", "America/Argentina/Salta"]
)
def test_a_known_zone_is_used(name: str) -> None:
    """IANA names resolve to their zone."""
    assert zone_named(name) == ZoneInfo(name)


@pytest.mark.parametrize(
    "name",
    [None, "", "Mars/Base", "../../etc/passwd", "/etc/localtime", "Europe/" + "x" * 80],
)
def test_a_missing_or_unknown_zone_means_utc(name: str | None) -> None:
    """Nothing that isn't a plain IANA name is looked up; it falls back to UTC."""
    assert zone_named(name) is UTC


def test_the_clock_reads_today_in_its_zone() -> None:
    """The date is the zone's own, read on each call."""
    for name in ("Pacific/Kiritimati", "Pacific/Pago_Pago"):
        zone = ZoneInfo(name)
        assert today_in(zone)() == datetime.now(zone).date()


def test_the_dependency_follows_the_header(monkeypatch: pytest.MonkeyPatch) -> None:
    """`get_today` reads the header's zone, or the server's zone without one."""
    kiritimati = ZoneInfo("Pacific/Kiritimati")
    monkeypatch.setattr(
        "app.entrypoints.api.shared.clock.get_server_settings",
        lambda: SimpleNamespace(time_zone=kiritimati),
    )
    tokyo = ZoneInfo("Asia/Tokyo")
    assert get_today("Asia/Tokyo")() == datetime.now(tokyo).date()
    assert get_today(None)() == datetime.now(kiritimati).date()
    assert get_today("Mars/Base")() == datetime.now(kiritimati).date()


async def _repos_with_release(released: date) -> GraphRepos:
    repos = GraphRepos(
        nodes=InMemoryNodeRepository(),
        edges=InMemoryEdgeRepository(),
        node_types=InMemoryNodeTypeRepository(),
        edge_types=InMemoryEdgeTypeRepository(),
    )
    schema: dict[str, Any] = {
        "type": "object",
        "properties": {"released": {"type": "string", "format": "date"}},
    }
    await repos.node_types.add(
        NodeType.create(
            owner_id=OWNER, slug="film", label="Film", attributes_schema=schema
        )
    )
    await repos.nodes.add(
        Node.create(
            owner_id=OWNER,
            name="Alien",
            type="film",
            attributes={"released": released.isoformat()},
        )
    )
    return repos


async def test_smart_collection_counts_use_the_injected_today() -> None:
    """'Released today or later' depends on whose today it is."""
    day = date(2026, 11, 20)
    repos = await _repos_with_release(day)
    definition = {
        "v": 1,
        "where": {
            "op": "and",
            "children": [
                {
                    "kind": "field",
                    "type": "film",
                    "key": "released",
                    "op": ">=",
                    "value": {"rel": "-0d"},
                }
            ],
        },
    }
    scope = ContentFilter.of(OWNER)

    same_day = GraphItemLookup(repos, today=lambda: day)
    next_day = GraphItemLookup(repos, today=lambda: day + timedelta(days=1))

    assert await same_day.count_matching(definition, scope, cap=None) == (1, False)
    assert await next_day.count_matching(definition, scope, cap=None) == (0, False)
