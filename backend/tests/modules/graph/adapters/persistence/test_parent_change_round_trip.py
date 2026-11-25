"""Attaching and detaching a parent on Postgres never changes an item (#775).

The use cases run against the real repositories, then everything is read back from
the database (not from the objects the use cases held) to check what was stored.
"""

import copy
import uuid
from typing import TYPE_CHECKING, Any

import pytest

from app.modules.graph.adapters.persistence.unit_of_work import (
    build_graph_repos,
    create_in_memory_graph_uow,
)
from app.modules.graph.application._validate_attributes import validate_attributes
from app.modules.graph.application.parent_type import resolve_effective_schema
from app.modules.graph.application.plan_parent_change import (
    PlanParentChange,
    PlanParentChangeQuery,
)
from app.modules.graph.application.update_node_type import (
    UpdateNodeType,
    UpdateNodeTypeCommand,
)
from app.modules.graph.domain.errors import InvalidParentTypeError
from app.modules.graph.domain.node import Node
from app.modules.graph.domain.node_type import NodeType
from app.shared_kernel.access_guard import InMemoryAccessGuard
from app.shared_kernel.actor import SYSTEM_ACTOR
from app.shared_kernel.content_filter import ContentFilter

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

    from app.modules.graph.application.parent_change import OnClash, OnDetach
    from app.modules.graph.ports.unit_of_work import GraphRepos

pytestmark = pytest.mark.integration

EVERYONE = ContentFilter.everyone()
VALUES = {"condition": "Worn", "width": "27 in", "value": "high"}


def _choice(*options: str) -> dict[str, Any]:
    return {
        "type": "string",
        "enum": list(options),
        "x-menagerist": {"kind": "choice"},
    }


def _schema(props: dict[str, Any]) -> dict[str, Any]:
    return {"type": "object", "properties": props}


class _World:
    """A parent, a clashing subtype with items, and another person's type."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.repos: GraphRepos = build_graph_repos(session)
        self.uow = create_in_memory_graph_uow(self.repos)
        self.guard = InMemoryAccessGuard()

    async def build(self) -> None:
        memorabilia = NodeType.create(
            owner_id=SYSTEM_ACTOR.id,
            slug="memorabilia",
            label="Memorabilia",
            attributes_schema=_schema(
                {"condition": _choice("Mint", "Good"), "value": {"type": "string"}}
            ),
        )
        self.poster = NodeType.create(
            owner_id=SYSTEM_ACTOR.id,
            slug="poster",
            label="Poster",
            attributes_schema=_schema(
                {"condition": _choice("Worn"), "width": {"type": "string"}}
            ),
        )
        self.stranger = NodeType.create(
            owner_id=uuid.uuid4(),
            slug="stranger",
            label="Stranger",
            attributes_schema=_schema({"condition": _choice("Fine")}),
        )
        self.item = Node.create(
            owner_id=SYSTEM_ACTOR.id,
            name="Alien",
            type="poster",
            attributes=dict(VALUES),
        )
        for row in (memorabilia, self.poster, self.stranger):
            await self.repos.node_types.add(row)
        await self.repos.nodes.add(self.item)
        await self.session.flush()
        self.memorabilia_id = memorabilia.id
        self.stranger_before = copy.deepcopy(self.stranger.attributes_schema)

    async def change(
        self,
        *,
        parent: str | None = None,
        clear_parent: bool = False,
        on_clash: OnClash = "refuse",
        on_detach: OnDetach = "keep",
    ) -> None:
        await UpdateNodeType(self.uow, self.guard).handle(
            UpdateNodeTypeCommand(
                node_type_id=self.poster.id,
                parent=parent,
                clear_parent=clear_parent,
                on_clash=on_clash,
                on_detach=on_detach,
            ),
            SYSTEM_ACTOR,
        )

    async def stored(self, node_type: NodeType) -> NodeType:
        """The type as the database holds it, not as this session remembers it."""
        await self.session.flush()
        self.session.expire_all()
        found = await self.repos.node_types.get(node_type.id, scope=EVERYONE)
        assert found is not None
        return found

    async def check_item_intact(self) -> None:
        """The item holds exactly what it did and is valid for what its type uses."""
        await self.session.flush()
        self.session.expire_all()
        item = await self.repos.nodes.get(self.item.id, scope=EVERYONE)
        poster = await self.stored(self.poster)
        schema = await resolve_effective_schema(self.repos, poster, scope=EVERYONE)
        assert item is not None
        assert item.attributes == VALUES
        assert schema is not None
        validate_attributes(schema, item.attributes)

    async def check_stranger_untouched(self) -> None:
        stranger = await self.stored(self.stranger)
        assert stranger.attributes_schema == self.stranger_before


async def _world(db_session: AsyncSession) -> _World:
    world = _World(db_session)
    await world.build()
    return world


async def test_a_merge_and_a_keep_round_trip_leaves_the_item_untouched(
    db_session: AsyncSession,
) -> None:
    """Attach with merge, detach with keep, twice: stored values never change."""
    world = await _world(db_session)

    for _ in range(2):
        await world.change(parent="memorabilia", on_clash="merge")
        attached = await world.stored(world.poster)
        assert attached.parent == "memorabilia"
        assert list((attached.attributes_schema or {})["properties"]) == ["width"]
        await world.check_item_intact()

        await world.change(clear_parent=True)
        detached = await world.stored(world.poster)
        assert detached.parent is None
        assert set((detached.attributes_schema or {})["properties"]) == {
            "condition",
            "width",
            "value",
        }
        await world.check_item_intact()

    parent = await world.repos.node_types.get(world.memorabilia_id, scope=EVERYONE)
    assert parent is not None
    options = (parent.attributes_schema or {})["properties"]["condition"]["enum"]
    assert options == ["Mint", "Good", "Worn"]
    await world.check_stranger_untouched()


async def test_a_dropped_parent_can_have_its_fields_restored(
    db_session: AsyncSession,
) -> None:
    """Drop archives the inherited fields; unarchiving them brings every value back."""
    world = await _world(db_session)
    await world.change(parent="memorabilia", on_clash="merge")

    await world.change(clear_parent=True, on_detach="drop")

    dropped = await world.stored(world.poster)
    props = (dropped.attributes_schema or {})["properties"]
    assert props["condition"]["x-menagerist"]["archived"] is True
    assert "archived" not in props["width"].get("x-menagerist", {})
    item = await world.repos.nodes.get(world.item.id, scope=EVERYONE)
    assert item is not None
    assert item.attributes == VALUES
    schema = copy.deepcopy(dropped.attributes_schema)
    assert schema is not None
    for key in ("condition", "value"):
        schema["properties"][key]["x-menagerist"]["archived"] = False
    validate_attributes(schema, item.attributes)


async def test_a_refused_change_leaves_every_type_as_it_was(
    db_session: AsyncSession,
) -> None:
    """A clash without merge is refused and nothing is written."""
    world = await _world(db_session)
    parent_before = (await world.stored(world.poster)).attributes_schema
    memorabilia = await world.repos.node_types.get(world.memorabilia_id, scope=EVERYONE)
    assert memorabilia is not None
    memorabilia_before = copy.deepcopy(memorabilia.attributes_schema)

    with pytest.raises(InvalidParentTypeError, match="condition"):
        await world.change(parent="memorabilia")

    poster = await world.stored(world.poster)
    memorabilia = await world.stored(memorabilia)
    assert poster.parent is None
    assert poster.attributes_schema == parent_before
    assert memorabilia.attributes_schema == memorabilia_before
    await world.check_item_intact()
    await world.check_stranger_untouched()


async def test_the_preview_reports_what_the_change_then_does(
    db_session: AsyncSession,
) -> None:
    """The plan and the update agree, and the plan saves nothing."""
    world = await _world(db_session)
    plan = await PlanParentChange(world.repos, world.guard).handle(
        PlanParentChangeQuery(
            node_type_id=world.poster.id, parent="memorabilia", on_clash="merge"
        ),
        SYSTEM_ACTOR,
    )

    assert plan.allowed is True
    assert plan.result.merged == ("condition",)
    assert plan.items == 1
    assert (await world.stored(world.poster)).parent is None

    await world.change(parent="memorabilia", on_clash="merge")

    after = await world.stored(world.poster)
    assert after.parent == "memorabilia"
    assert list((after.attributes_schema or {})["properties"]) == ["width"]
