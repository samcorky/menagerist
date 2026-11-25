"""Widening a query so a parent type stands for its subtypes (#768)."""

import uuid
from typing import Any

from app.modules.graph.application.type_families import expand_type_families, type_views
from app.modules.graph.domain.node_type import NodeType
from app.modules.graph.domain.query import (
    ConnectionCondition,
    FavouriteCondition,
    FieldCondition,
    Group,
    TypeCondition,
)

ME = uuid.UUID(int=1)


def _node_type(slug: str, parent: str | None = None, **props: Any) -> NodeType:  # noqa: ANN401
    return NodeType.create(
        owner_id=ME,
        slug=slug,
        label=slug.title(),
        attributes_schema={"type": "object", "properties": props} if props else None,
        parent=parent,
    )


FAMILIES = {"memorabilia": ("poster", "figure")}


def _connection(where: Group | None = None) -> ConnectionCondition:
    return ConnectionCondition(
        mode="exists",
        relationship="made-by",
        direction="any",
        item=None,
        where=where,
    )


def test_a_subtype_uses_its_parents_fields_and_a_parent_lists_its_subtypes() -> None:
    """The views give each type its effective fields and each parent its subtypes."""
    types = [
        _node_type("memorabilia", condition={"type": "string"}),
        _node_type("poster", "memorabilia", width={"type": "string"}),
        _node_type("figure", "memorabilia"),
        _node_type("film", rating={"type": "number"}),
        _node_type("orphan", "gone", note={"type": "string"}),
    ]

    schemas, families = type_views(types)

    assert list(schemas["poster"]["properties"]) == ["condition", "width"]
    assert list(schemas["figure"]["properties"]) == ["condition"]
    assert list(schemas["film"]["properties"]) == ["rating"]
    assert list(schemas["orphan"]["properties"]) == ["note"]
    assert schemas["memorabilia"] == types[0].attributes_schema
    assert families == {"memorabilia": ("poster", "figure")}


def test_a_type_with_no_schema_uses_an_empty_one() -> None:
    """No fields at all is not an error."""
    schemas, families = type_views([_node_type("blank")])

    assert schemas == {"blank": {}}
    assert families == {}


def test_a_type_condition_gains_the_subtypes_of_every_parent_it_names() -> None:
    """Each named parent brings its subtypes, once, after what was named."""
    where = Group(
        op="and",
        children=(
            TypeCondition(slugs=("memorabilia", "film", "poster"), mode="any"),
            TypeCondition(slugs=("memorabilia",), mode="none"),
        ),
    )

    out = expand_type_families(where, FAMILIES)

    assert out is not None
    first, second = out.children
    assert isinstance(first, TypeCondition)
    assert first.slugs == ("memorabilia", "film", "poster", "figure")
    assert isinstance(second, TypeCondition)
    assert (second.slugs, second.mode) == (("memorabilia", "poster", "figure"), "none")


def test_a_type_condition_naming_no_types_is_left_alone() -> None:
    """Has an item type, and has none, are not widened."""
    where = Group(
        op="and",
        children=(TypeCondition(mode="any"), TypeCondition(mode="none")),
    )

    assert expand_type_families(where, FAMILIES) == where


def test_a_field_condition_on_a_parent_becomes_an_or_over_the_family() -> None:
    """The parent's leaf stays, and each subtype gets the same leaf."""
    leaf = FieldCondition(type="memorabilia", key="condition", op="=", value="a")
    where = Group(op="and", children=(leaf,))

    out = expand_type_families(where, FAMILIES)

    assert out is not None
    (widened,) = out.children
    assert isinstance(widened, Group)
    assert widened.op == "or"
    assert widened.children[0] == leaf
    assert [c.type for c in widened.children if isinstance(c, FieldCondition)] == [
        "memorabilia",
        "poster",
        "figure",
    ]


def test_field_conditions_elsewhere_are_left_alone() -> None:
    """A subtype, a type with no subtypes, and a per-item field are not widened."""
    leaves = (
        FieldCondition(type="poster", key="condition", op="=", value="a"),
        FieldCondition(type="film", key="rating", op="=", value=1),
        FieldCondition(field_kind="text", key="note", op="=", value="x"),
    )
    where = Group(op="or", children=leaves)

    assert expand_type_families(where, FAMILIES) == where


def test_widening_reaches_into_nested_groups_and_connections() -> None:
    """A condition on the far side of a connection is widened too."""
    inner = Group(op="and", children=(TypeCondition(slugs=("memorabilia",)),))
    where = Group(
        op="not",
        children=(
            Group(
                op="and",
                children=(
                    FavouriteCondition(value=True),
                    _connection(inner),
                    _connection(),
                ),
            ),
        ),
    )

    out = expand_type_families(where, FAMILIES)

    assert out is not None
    (group,) = out.children
    assert isinstance(group, Group)
    favourite, connection, bare = group.children
    assert favourite == FavouriteCondition(value=True)
    assert isinstance(connection, ConnectionCondition)
    assert connection.where is not None
    (widened,) = connection.where.children
    assert isinstance(widened, TypeCondition)
    assert widened.slugs == ("memorabilia", "poster", "figure")
    assert isinstance(bare, ConnectionCondition)
    assert bare.where is None


def test_nothing_is_rewritten_without_a_filter_or_any_subtypes() -> None:
    """No filter, or no parents, hands the query back untouched."""
    where = Group(op="and", children=(TypeCondition(slugs=("film",)),))

    assert expand_type_families(None, FAMILIES) is None
    assert expand_type_families(where, {}) is where
