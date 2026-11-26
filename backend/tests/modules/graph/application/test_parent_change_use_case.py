"""Attaching or detaching a parent through UpdateNodeType keeps items intact (#775)."""

import copy
from typing import TYPE_CHECKING, Any

import pytest

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
from app.modules.graph.application._validate_attributes import validate_attributes
from app.modules.graph.application.parent_type import resolve_effective_schema
from app.modules.graph.application.update_node_type import (
    UpdateNodeType,
    UpdateNodeTypeCommand,
)
from app.modules.graph.domain.errors import InvalidParentTypeError
from app.modules.graph.domain.node import Node
from app.modules.graph.domain.node_type import NodeType
from app.modules.graph.ports.unit_of_work import GraphRepos
from app.shared_kernel.access_guard import InMemoryAccessGuard
from app.shared_kernel.actor import SYSTEM_ACTOR
from app.shared_kernel.content_filter import ContentFilter
from app.shared_kernel.unit_of_work import InMemoryUnitOfWork

if TYPE_CHECKING:
    from app.modules.graph.application.parent_change import OnClash, OnDetach

type Uow = InMemoryUnitOfWork[GraphRepos]

EVERYONE = ContentFilter.everyone()


def _text(title: str) -> dict[str, Any]:
    return {"type": "string", "title": title}


def _choice(title: str, *options: str) -> dict[str, Any]:
    return {
        "type": "string",
        "title": title,
        "enum": list(options),
        "x-menagerist": {"kind": "choice"},
    }


def _schema(props: dict[str, dict[str, Any]], **meta: object) -> dict[str, Any]:
    schema: dict[str, Any] = {"type": "object", "properties": props}
    if meta:
        schema["x-menagerist"] = dict(meta)
    return schema


def _uow() -> tuple[Uow, GraphRepos]:
    repos = GraphRepos(
        nodes=InMemoryNodeRepository(),
        edges=InMemoryEdgeRepository(),
        node_types=InMemoryNodeTypeRepository(),
        edge_types=InMemoryEdgeTypeRepository(),
    )
    return InMemoryUnitOfWork(repos), repos


async def _type(
    repos: GraphRepos,
    slug: str,
    schema: dict[str, Any] | None,
    parent: str | None = None,
) -> NodeType:
    node_type = NodeType.create(
        owner_id=SYSTEM_ACTOR.id,
        slug=slug,
        label=slug.title(),
        attributes_schema=schema,
        parent=parent,
    )
    await repos.node_types.add(node_type)
    return node_type


async def _item(
    repos: GraphRepos, type_slug: str, name: str, attributes: dict[str, Any]
) -> Node:
    node = Node.create(
        owner_id=SYSTEM_ACTOR.id, name=name, type=type_slug, attributes=attributes
    )
    await repos.nodes.add(node)
    return node


async def _change(
    uow: Uow,
    node_type: NodeType,
    *,
    parent: str | None = None,
    clear_parent: bool = False,
    on_clash: OnClash = "refuse",
    on_detach: OnDetach = "keep",
) -> NodeType:
    return await UpdateNodeType(uow, InMemoryAccessGuard()).handle(
        UpdateNodeTypeCommand(
            node_type_id=node_type.id,
            parent=parent,
            clear_parent=clear_parent,
            on_clash=on_clash,
            on_detach=on_detach,
        ),
        SYSTEM_ACTOR,
    )


async def _every_item_validates(repos: GraphRepos, node_type: NodeType) -> None:
    """Every item of the type is valid against what the type now uses."""
    schema = await resolve_effective_schema(repos, node_type, scope=EVERYONE)
    assert schema is not None
    items = await repos.nodes.list(
        scope=EVERYONE, after=None, limit=100, type=str(node_type.slug)
    )
    assert items
    for item in items:
        validate_attributes(schema, item.attributes)


MEMORABILIA = _schema(
    {"condition": _choice("Condition", "Mint", "Good"), "value": _text("Value")}
)
VALUES = {"condition": "Worn", "width": "27 in", "value": "high"}


async def _poster_world(
    repos: GraphRepos, *, parent: str | None = None
) -> tuple[NodeType, NodeType, Node]:
    memorabilia = await _type(repos, "memorabilia", copy.deepcopy(MEMORABILIA))
    poster = await _type(
        repos,
        "poster",
        _schema({"condition": _choice("Condition", "Worn"), "width": _text("Width")}),
        parent=parent,
    )
    item = await _item(repos, "poster", "Alien", dict(VALUES))
    return memorabilia, poster, item


async def test_attaching_refuses_a_shared_key_by_default() -> None:
    """Without a choice, a clash is still refused, and nothing changes."""
    uow, repos = _uow()
    memorabilia, poster, _ = await _poster_world(repos)
    before = copy.deepcopy((memorabilia.attributes_schema, poster.attributes_schema))

    with pytest.raises(InvalidParentTypeError, match="condition"):
        await _change(uow, poster, parent="memorabilia")

    assert (memorabilia.attributes_schema, poster.attributes_schema) == before
    assert poster.parent is None
    assert uow.committed is False


async def test_attaching_with_merge_uses_the_parents_field_and_keeps_values() -> None:
    """The clash is merged; the item's values are exactly as they were."""
    uow, repos = _uow()
    memorabilia, poster, item = await _poster_world(repos)

    await _change(uow, poster, parent="memorabilia", on_clash="merge")

    assert poster.parent == "memorabilia"
    assert list((poster.attributes_schema or {})["properties"]) == ["width"]
    options = (memorabilia.attributes_schema or {})["properties"]["condition"]["enum"]
    assert options == ["Mint", "Good", "Worn"]
    assert item.attributes == VALUES
    await _every_item_validates(repos, poster)


async def test_a_different_kind_blocks_a_merge_and_changes_nothing() -> None:
    """The same key as another kind of field stops the change, atomically."""
    uow, repos = _uow()
    memorabilia = await _type(repos, "memorabilia", copy.deepcopy(MEMORABILIA))
    poster = await _type(
        repos, "poster", _schema({"condition": {"type": "number", "title": "C"}})
    )
    before = copy.deepcopy((memorabilia.attributes_schema, poster.attributes_schema))

    with pytest.raises(InvalidParentTypeError, match="different kind"):
        await _change(uow, poster, parent="memorabilia", on_clash="merge")

    assert (memorabilia.attributes_schema, poster.attributes_schema) == before
    assert poster.parent is None
    assert uow.committed is False


async def test_detaching_with_keep_leaves_the_type_with_the_fields_it_used() -> None:
    """The type now defines what it inherited, so no item loses a field."""
    uow, repos = _uow()
    memorabilia, poster, item = await _poster_world(repos)
    await _change(uow, poster, parent="memorabilia", on_clash="merge")
    used_before = await resolve_effective_schema(repos, poster, scope=EVERYONE)

    await _change(uow, poster, clear_parent=True)

    assert poster.parent is None
    used_after = await resolve_effective_schema(repos, poster, scope=EVERYONE)
    assert used_before is not None
    assert used_after is not None
    assert set(used_after["properties"]) == set(used_before["properties"])
    assert used_after["properties"]["condition"]["enum"] == ["Mint", "Good", "Worn"]
    assert item.attributes == VALUES
    await _every_item_validates(repos, poster)
    # The parent is as the merge left it.
    assert memorabilia.attributes_schema is not None


async def test_detaching_with_drop_archives_the_fields_and_they_can_come_back() -> None:
    """Hidden, not deleted: values stay, and unarchiving restores the fields."""
    uow, repos = _uow()
    _, poster, item = await _poster_world(repos)
    await _change(uow, poster, parent="memorabilia", on_clash="merge")

    await _change(uow, poster, clear_parent=True, on_detach="drop")

    props = (poster.attributes_schema or {})["properties"]
    assert props["condition"]["x-menagerist"]["archived"] is True
    assert props["value"]["x-menagerist"]["archived"] is True
    assert item.attributes == VALUES
    props["condition"]["x-menagerist"]["archived"] = False
    await _every_item_validates(repos, poster)


async def test_moving_to_another_parent_merges_what_the_two_share() -> None:
    """Fields kept from the old parent meet the new one's, and merge."""
    uow, repos = _uow()
    _, poster, item = await _poster_world(repos, parent=None)
    await _change(uow, poster, parent="memorabilia", on_clash="merge")
    merchandise = await _type(
        repos, "merchandise", _schema({"condition": _choice("Condition", "New")})
    )

    await _change(uow, poster, parent="merchandise", on_clash="merge")

    assert poster.parent == "merchandise"
    options = (merchandise.attributes_schema or {})["properties"]["condition"]["enum"]
    assert options == ["New", "Mint", "Good", "Worn"]
    assert set((poster.attributes_schema or {})["properties"]) == {"width", "value"}
    assert item.attributes == VALUES
    await _every_item_validates(repos, poster)


async def test_a_repeated_round_trip_never_loses_a_value() -> None:
    """Attach, detach, attach again: the item is untouched and always valid."""
    uow, repos = _uow()
    _, poster, item = await _poster_world(repos)

    for _ in range(2):
        await _change(uow, poster, parent="memorabilia", on_clash="merge")
        await _every_item_validates(repos, poster)
        await _change(uow, poster, clear_parent=True)
        await _every_item_validates(repos, poster)

    assert item.attributes == VALUES


async def test_an_unchanged_parent_is_not_a_move() -> None:
    """Naming the parent it already has changes no fields."""
    uow, repos = _uow()
    memorabilia = await _type(repos, "memorabilia", copy.deepcopy(MEMORABILIA))
    poster = await _type(
        repos, "poster", _schema({"width": _text("Width")}), parent="memorabilia"
    )
    before = copy.deepcopy((memorabilia.attributes_schema, poster.attributes_schema))

    await _change(uow, poster, parent="memorabilia", on_clash="merge", on_detach="drop")

    assert (memorabilia.attributes_schema, poster.attributes_schema) == before
