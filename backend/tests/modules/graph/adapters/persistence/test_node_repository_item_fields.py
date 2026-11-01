"""`NodeRepository.item_fields`, against the in-memory and Postgres adapters."""

import uuid
from typing import TYPE_CHECKING, Any

import pytest

from app.modules.graph.adapters.persistence.in_memory_node_repository import (
    InMemoryNodeRepository,
)
from app.modules.graph.adapters.persistence.node_repository import (
    SqlAlchemyNodeRepository,
)
from app.modules.graph.domain.node import Node
from app.modules.graph.domain.query import ItemFieldUse
from app.shared_kernel.content_filter import ContentFilter

if TYPE_CHECKING:
    from app.modules.graph.ports.node_repository import NodeRepository

ALICE = uuid.UUID(int=101)
BOB = uuid.UUID(int=102)
A = ContentFilter.of(ALICE)
B = ContentFilter.of(BOB)
ALL = ContentFilter.everyone()


@pytest.fixture(
    params=["in_memory", pytest.param("postgres", marks=pytest.mark.integration)]
)
def repository(request: pytest.FixtureRequest) -> NodeRepository:
    """The same scenarios run against both adapters."""
    if request.param == "in_memory":
        return InMemoryNodeRepository()
    return SqlAlchemyNodeRepository(request.getfixturevalue("db_session"))


def _prop(kind: str | None, title: str | None = None, **meta: Any) -> dict[str, Any]:  # noqa: ANN401
    prop: dict[str, Any] = {"type": "string"}
    if title is not None:
        prop["title"] = title
    x: dict[str, Any] = dict(meta)
    if kind is not None:
        x["kind"] = kind
    if x:
        prop["x-menagerist"] = x
    return prop


async def _add(
    repository: NodeRepository,
    props: dict[str, Any] | None,
    *,
    owner: uuid.UUID = ALICE,
    name: str = "n",
) -> Node:
    schema = None if props is None else {"type": "object", "properties": props}
    node = Node.create(owner_id=owner, name=name, extra_schema=schema)
    await repository.add(node)
    return node


async def test_empty_store_lists_nothing(repository: NodeRepository) -> None:
    """Empty store lists nothing."""
    assert await repository.item_fields(scope=ALL, limit=200) == []


async def test_counts_by_key_and_kind_ordered_by_count_then_key(
    repository: NodeRepository,
) -> None:
    """Counts by key and kind ordered by count then key."""
    await _add(repository, {"signed": _prop("boolean", "Signed")})
    await _add(repository, {"signed": _prop("boolean", "Signed")})
    await _add(repository, {"alpha": _prop("text", "Alpha")})
    await _add(repository, {"beta": _prop("text", "Beta")})
    await _add(repository, None)

    assert await repository.item_fields(scope=A, limit=200) == [
        ItemFieldUse(key="signed", kind="boolean", label="Signed", count=2),
        ItemFieldUse(key="alpha", kind="text", label="Alpha", count=1),
        ItemFieldUse(key="beta", kind="text", label="Beta", count=1),
    ]


async def test_same_key_with_two_kinds_is_two_rows(repository: NodeRepository) -> None:
    """Same key with two kinds is two rows."""
    await _add(repository, {"size": _prop("number", "Size")})
    await _add(repository, {"size": _prop("text", "Size")})
    await _add(repository, {"size": _prop("text", "Size")})

    assert await repository.item_fields(scope=A, limit=200) == [
        ItemFieldUse(key="size", kind="text", label="Size", count=2),
        ItemFieldUse(key="size", kind="number", label="Size", count=1),
    ]


async def test_omits_archived_inferred_and_unknown_kinds(
    repository: NodeRepository,
) -> None:
    """Omits archived inferred and unknown kinds."""
    await _add(
        repository,
        {
            "old": _prop("text", "Old", archived=True),
            "inferred": _prop(None, "Inferred"),
            "group": _prop("group", "Group"),
            "weird": _prop("nonsense", "Weird"),
            "live": _prop("text", "Live"),
        },
    )
    await _add(repository, {"bad": {"x-menagerist": {"kind": 3}}})
    await _add(repository, {"bad": "not an object"})

    assert await repository.item_fields(scope=A, limit=200) == [
        ItemFieldUse(key="live", kind="text", label="Live", count=1)
    ]


async def test_label_is_most_common_title_ties_by_name_then_key(
    repository: NodeRepository,
) -> None:
    """Label is most common title ties by name then key."""
    await _add(repository, {"a": _prop("text", "Zed"), "b": _prop("text", "Zed")})
    await _add(repository, {"a": _prop("text", "Alpha"), "b": _prop("text")})
    await _add(repository, {"a": _prop("text", "Zed"), "b": _prop("text", "Beta")})
    await _add(repository, {"a": _prop("text", "Alpha")})

    rows = await repository.item_fields(scope=A, limit=200)

    # a: Zed x2, Alpha x2 (a tie) -> Alpha; b: Zed, Beta, no title -> Beta.
    assert [(r.key, r.label, r.count) for r in rows] == [
        ("a", "Alpha", 4),
        ("b", "Beta", 3),
    ]


async def test_label_falls_back_to_key_without_a_title(
    repository: NodeRepository,
) -> None:
    """Label falls back to key without a title."""
    await _add(repository, {"signed": _prop("boolean")})
    await _add(repository, {"blank": _prop("text", "")})

    rows = await repository.item_fields(scope=A, limit=200)

    assert {(r.key, r.label) for r in rows} == {
        ("signed", "signed"),
        ("blank", "blank"),
    }


async def test_scope_and_soft_delete_are_respected(repository: NodeRepository) -> None:
    """Scope and soft delete are respected."""
    await _add(repository, {"mine": _prop("text", "Mine")}, owner=ALICE)
    await _add(repository, {"theirs": _prop("text", "Theirs")}, owner=BOB)
    gone = await _add(repository, {"gone": _prop("text", "Gone")}, owner=ALICE)
    gone.soft_delete()
    await repository.save(gone)

    assert [r.key for r in await repository.item_fields(scope=A, limit=200)] == ["mine"]
    assert [r.key for r in await repository.item_fields(scope=B, limit=200)] == [
        "theirs"
    ]
    assert {r.key for r in await repository.item_fields(scope=ALL, limit=200)} == {
        "mine",
        "theirs",
    }


async def test_limit_applies_after_ordering(repository: NodeRepository) -> None:
    """Limit applies after ordering."""
    await _add(repository, {"a": _prop("text"), "b": _prop("text")})
    await _add(repository, {"b": _prop("text")})

    rows = await repository.item_fields(scope=A, limit=1)

    assert [(r.key, r.count) for r in rows] == [("b", 2)]
