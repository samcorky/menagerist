"""Listing the fields several subtypes share, and moving one up to the parent (#774)."""

import copy
import uuid
from typing import Any

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
from app.modules.graph.application.list_shared_subtype_fields import (
    ListSharedSubtypeFields,
    ListSharedSubtypeFieldsQuery,
)
from app.modules.graph.application.parent_type import resolve_effective_schema
from app.modules.graph.application.promote_subtype_field import (
    PromoteSubtypeField,
    PromoteSubtypeFieldCommand,
)
from app.modules.graph.domain.errors import InvalidSchemaError, NodeTypeNotFoundError
from app.modules.graph.domain.node import Node
from app.modules.graph.domain.node_type import NodeType
from app.modules.graph.ports.unit_of_work import GraphRepos
from app.shared_kernel.access_guard import InMemoryAccessGuard
from app.shared_kernel.actor import SYSTEM_ACTOR, Actor
from app.shared_kernel.content_filter import ContentFilter
from app.shared_kernel.unit_of_work import InMemoryUnitOfWork

EVERYONE = ContentFilter.everyone()


def _text(title: str, **meta: Any) -> dict[str, Any]:  # noqa: ANN401
    prop: dict[str, Any] = {
        "type": "string",
        "title": title,
        "x-menagerist": {"kind": "text", **meta},
    }
    return prop


def _choice(title: str, *options: str) -> dict[str, Any]:
    return {
        "type": "string",
        "title": title,
        "enum": list(options),
        "x-menagerist": {"kind": "choice"},
    }


def _number(title: str) -> dict[str, Any]:
    return {"type": "number", "title": title, "x-menagerist": {"kind": "number"}}


def _schema(props: dict[str, Any], **meta: object) -> dict[str, Any]:
    schema: dict[str, Any] = {"type": "object", "properties": props}
    if meta:
        schema["x-menagerist"] = dict(meta)
    return schema


def _repos() -> GraphRepos:
    return GraphRepos(
        nodes=InMemoryNodeRepository(),
        edges=InMemoryEdgeRepository(),
        node_types=InMemoryNodeTypeRepository(),
        edge_types=InMemoryEdgeTypeRepository(),
    )


async def _type(
    repos: GraphRepos,
    slug: str,
    schema: dict[str, Any] | None = None,
    parent: str | None = None,
    owner: uuid.UUID = SYSTEM_ACTOR.id,
) -> NodeType:
    node_type = NodeType.create(
        owner_id=owner,
        slug=slug,
        label=slug.title(),
        attributes_schema=schema,
        parent=parent,
    )
    await repos.node_types.add(node_type)
    return node_type


async def _family(repos: GraphRepos) -> NodeType:
    """Memorabilia with three subtypes, the first two sharing `condition`."""
    memo = await _type(repos, "memorabilia", _schema({"value": _text("Value")}))
    await _type(
        repos,
        "poster",
        _schema(
            {"condition": _choice("Condition", "Mint", "Good"), "width": _text("W")},
            required=["condition"],
            layout=[{"key": "condition"}, {"key": "width"}],
        ),
        parent="memorabilia",
    )
    await _type(
        repos,
        "print",
        _schema({"condition": _choice("Condition", "Fair", "Mint")}),
        parent="memorabilia",
    )
    await _type(
        repos, "figure", _schema({"height": _text("Height")}), parent="memorabilia"
    )
    return memo


async def _list(repos: GraphRepos, parent: NodeType) -> list[Any]:
    return await ListSharedSubtypeFields(repos, InMemoryAccessGuard()).handle(
        ListSharedSubtypeFieldsQuery(node_type_id=parent.id), SYSTEM_ACTOR
    )


async def _promote(
    repos: GraphRepos, parent: NodeType, key: str
) -> tuple[Any, InMemoryUnitOfWork[GraphRepos]]:
    uow = InMemoryUnitOfWork(repos)
    result = await PromoteSubtypeField(uow, InMemoryAccessGuard()).handle(
        PromoteSubtypeFieldCommand(node_type_id=parent.id, key=key), SYSTEM_ACTOR
    )
    return result, uow


async def _stored(repos: GraphRepos, slug: str) -> NodeType:
    found = await repos.node_types.get_by_slug(slug, scope=EVERYONE)
    assert found is not None
    return found


# ---- listing ----


async def test_a_field_two_subtypes_define_is_listed_with_who_has_it() -> None:
    """The key, its name and kind, and the subtypes that define it."""
    repos = _repos()
    memo = await _family(repos)

    (shared,) = await _list(repos, memo)

    assert (shared.key, shared.label, shared.kind) == (
        "condition",
        "Condition",
        "choice",
    )
    assert shared.subtypes == ("poster", "print")
    assert shared.differing == ()


async def test_a_field_only_one_subtype_defines_is_not_listed() -> None:
    """There is nothing repeated to move up."""
    repos = _repos()
    memo = await _family(repos)

    keys = [f.key for f in await _list(repos, memo)]

    assert "height" not in keys
    assert "width" not in keys


async def test_a_subtype_that_keeps_the_key_as_another_kind_is_reported() -> None:
    """The list says which subtypes would stop the promotion."""
    repos = _repos()
    memo = await _family(repos)
    await _type(
        repos, "mug", _schema({"condition": _number("Condition")}), "memorabilia"
    )

    (shared,) = await _list(repos, memo)

    assert shared.subtypes == ("poster", "print")
    assert shared.differing == ("mug",)


async def test_an_archived_field_is_not_listed() -> None:
    """Hidden fields are not offered."""
    repos = _repos()
    memo = await _type(repos, "memorabilia")
    for slug in ("poster", "print"):
        await _type(
            repos,
            slug,
            _schema({"condition": _text("Condition", archived=True)}),
            "memorabilia",
        )

    assert await _list(repos, memo) == []


async def test_only_a_parents_own_subtypes_are_considered() -> None:
    """Another person's subtypes of the same slug are not."""
    repos = _repos()
    me = Actor(id=uuid.uuid4(), roles=frozenset({"member"}))
    stranger = uuid.uuid4()
    memo = await _type(repos, "memorabilia", owner=me.id)
    for slug in ("hat", "scarf"):
        await _type(
            repos, slug, _schema({"size": _text("Size")}), "memorabilia", owner=stranger
        )

    found = await ListSharedSubtypeFields(repos, InMemoryAccessGuard()).handle(
        ListSharedSubtypeFieldsQuery(node_type_id=memo.id), me
    )

    assert found == []


async def test_a_type_with_no_subtypes_has_nothing_to_list() -> None:
    """A subtype, or a standalone type, lists nothing."""
    repos = _repos()
    await _family(repos)
    poster = await _stored(repos, "poster")

    assert await _list(repos, poster) == []


async def test_listing_for_an_unknown_type_is_not_found() -> None:
    """The parent has to exist."""
    repos = _repos()

    with pytest.raises(NodeTypeNotFoundError):
        await ListSharedSubtypeFields(repos, InMemoryAccessGuard()).handle(
            ListSharedSubtypeFieldsQuery(node_type_id=uuid.uuid4()), SYSTEM_ACTOR
        )


# ---- promoting ----


async def test_promoting_adds_the_field_to_the_parent_and_removes_it_below() -> None:
    """The parent defines it, the subtypes no longer do, and they still use it."""
    repos = _repos()
    memo = await _family(repos)

    result, uow = await _promote(repos, memo, "condition")

    assert uow.committed is True
    assert result.subtypes == 2
    parent = await _stored(repos, "memorabilia")
    assert list((parent.attributes_schema or {})["properties"]) == [
        "value",
        "condition",
    ]
    for slug in ("poster", "print"):
        sub = await _stored(repos, slug)
        assert "condition" not in (sub.attributes_schema or {})["properties"]
        used = await resolve_effective_schema(repos, sub, scope=EVERYONE)
        assert used is not None
        assert "condition" in used["properties"]
    # An unrelated subtype is untouched.
    figure = await _stored(repos, "figure")
    assert list((figure.attributes_schema or {})["properties"]) == ["height"]


async def test_the_choices_of_every_subtype_are_combined_on_the_parent() -> None:
    """No stored value stops being an option."""
    repos = _repos()
    memo = await _family(repos)

    await _promote(repos, memo, "condition")

    parent = await _stored(repos, "memorabilia")
    options = (parent.attributes_schema or {})["properties"]["condition"]["enum"]
    assert options == ["Mint", "Good", "Fair"]


async def test_required_and_layout_follow_the_field_up() -> None:
    """The parent now requires it for every subtype, and the subtype's place goes."""
    repos = _repos()
    memo = await _family(repos)

    await _promote(repos, memo, "condition")

    parent = await _stored(repos, "memorabilia")
    assert (parent.attributes_schema or {})["x-menagerist"]["required"] == ["condition"]
    poster = await _stored(repos, "poster")
    meta = (poster.attributes_schema or {})["x-menagerist"]
    assert "required" not in meta
    assert meta["layout"] == [{"key": "width"}]


async def test_items_keep_their_values_and_stay_valid() -> None:
    """Values are stored by key, so a field moving between types changes none."""
    repos = _repos()
    memo = await _family(repos)
    item = Node.create(
        owner_id=SYSTEM_ACTOR.id,
        name="Alien",
        type="poster",
        attributes={"condition": "Good", "width": "27 in", "value": "high"},
    )
    await repos.nodes.add(item)
    before = copy.deepcopy(item.attributes)

    await _promote(repos, memo, "condition")

    assert item.attributes == before
    poster = await _stored(repos, "poster")
    schema = await resolve_effective_schema(repos, poster, scope=EVERYONE)
    assert schema is not None
    validate_attributes(schema, item.attributes)


async def test_a_different_kind_refuses_the_promotion_and_changes_nothing() -> None:
    """The count of subtypes keeping it as another kind is in the message."""
    repos = _repos()
    memo = await _family(repos)
    await _type(
        repos, "mug", _schema({"condition": _number("Condition")}), "memorabilia"
    )
    before = {
        slug: copy.deepcopy((await _stored(repos, slug)).attributes_schema)
        for slug in ("memorabilia", "poster", "print", "mug")
    }

    with pytest.raises(
        InvalidSchemaError, match="1 subtype keeps Condition as a different"
    ):
        await _promote(repos, memo, "condition")

    after = {slug: (await _stored(repos, slug)).attributes_schema for slug in before}
    assert after == before


async def test_a_key_no_subtype_defines_cannot_be_promoted() -> None:
    """There has to be something to move."""
    repos = _repos()
    memo = await _family(repos)

    with pytest.raises(InvalidSchemaError, match="No subtype"):
        await _promote(repos, memo, "nothing")


async def test_a_key_the_parent_already_has_cannot_be_promoted() -> None:
    """The parent defines it already."""
    repos = _repos()
    memo = await _family(repos)

    with pytest.raises(InvalidSchemaError, match="already"):
        await _promote(repos, memo, "value")


async def test_a_subtype_that_has_the_key_archived_stops_the_promotion() -> None:
    """The archived copy would clash with the parent's, so it is named."""
    repos = _repos()
    memo = await _family(repos)
    await _type(
        repos,
        "mug",
        _schema({"condition": _text("Condition", archived=True)}),
        "memorabilia",
    )

    with pytest.raises(InvalidSchemaError, match="Mug has 'condition' hidden"):
        await _promote(repos, memo, "condition")


async def test_promoting_on_an_unknown_type_is_not_found() -> None:
    """The parent has to exist."""
    repos = _repos()
    ghost = NodeType.create(owner_id=SYSTEM_ACTOR.id, slug="ghost", label="Ghost")

    with pytest.raises(NodeTypeNotFoundError):
        await _promote(repos, ghost, "condition")
