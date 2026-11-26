"""A subtype uses its parent's fields: in what the type reports and in item checks."""

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
from app.modules.graph.application.create_node import CreateNode, CreateNodeCommand
from app.modules.graph.application.create_node_type import (
    CreateNodeType,
    CreateNodeTypeCommand,
)
from app.modules.graph.application.get_node_type import GetNodeType, GetNodeTypeQuery
from app.modules.graph.application.list_node_types import (
    ListNodeTypes,
    ListNodeTypesQuery,
)
from app.modules.graph.application.list_subtypes import ListSubtypes, ListSubtypesQuery
from app.modules.graph.application.update_node import UpdateNode, UpdateNodeCommand
from app.modules.graph.application.update_node_type import (
    UpdateNodeType,
    UpdateNodeTypeCommand,
)
from app.modules.graph.domain.errors import InvalidAttributesError, InvalidSchemaError
from app.modules.graph.domain.node_type import NodeType
from app.modules.graph.ports.unit_of_work import GraphRepos
from app.shared_kernel.access_guard import InMemoryAccessGuard
from app.shared_kernel.actor import SYSTEM_ACTOR
from app.shared_kernel.unit_of_work import InMemoryUnitOfWork

type Uow = InMemoryUnitOfWork[GraphRepos]

GUARD = InMemoryAccessGuard()


def _uow() -> tuple[Uow, GraphRepos]:
    repos = GraphRepos(
        nodes=InMemoryNodeRepository(),
        edges=InMemoryEdgeRepository(),
        node_types=InMemoryNodeTypeRepository(),
        edge_types=InMemoryEdgeTypeRepository(),
    )
    return InMemoryUnitOfWork(repos), repos


def _schema(
    props: dict[str, Any], highlights: dict[str, Any] | None = None
) -> dict[str, Any]:
    schema: dict[str, Any] = {"type": "object", "properties": props}
    if highlights is not None:
        schema["x-menagerist"] = {"highlights": highlights}
    return schema


async def _add(
    repos: GraphRepos,
    slug: str,
    schema: dict[str, Any] | None = None,
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


async def _memorabilia_and_poster(repos: GraphRepos) -> tuple[NodeType, NodeType]:
    parent = await _add(
        repos, "memorabilia", _schema({"year": {"type": "number", "title": "Year"}})
    )
    poster = await _add(
        repos,
        "poster",
        _schema({"width": {"type": "string", "title": "Width"}}),
        parent="memorabilia",
    )
    return parent, poster


async def test_get_reports_the_fields_a_subtype_uses() -> None:
    """The response carries the effective schema: parent's fields, then its own."""
    _, repos = _uow()
    parent, poster = await _memorabilia_and_poster(repos)

    got = await GetNodeType(repos, GUARD).handle(
        GetNodeTypeQuery(node_type_id=poster.id), SYSTEM_ACTOR
    )

    assert got.effective_schema is not None
    assert list(got.effective_schema["properties"]) == ["year", "width"]
    assert got.parent_updated_at == parent.updated_at
    # What the type itself defines is unchanged, for the editor to edit.
    assert list((got.attributes_schema or {})["properties"]) == ["width"]


async def test_a_top_level_type_inherits_nothing() -> None:
    """With no parent nothing is derived: it comes back as stored.

    The API answers with the type's own schema as the effective one.
    """
    _, repos = _uow()
    parent, _ = await _memorabilia_and_poster(repos)

    got = await GetNodeType(repos, GUARD).handle(
        GetNodeTypeQuery(node_type_id=parent.id), SYSTEM_ACTOR
    )

    assert got is parent
    assert got.effective_schema is None
    assert got.parent_updated_at is None


async def test_list_reports_each_types_effective_schema() -> None:
    """A subtype in a page reports what it uses; a top-level type derives nothing."""
    _, repos = _uow()
    await _memorabilia_and_poster(repos)

    found = (
        await ListNodeTypes(repos, GUARD).handle(ListNodeTypesQuery(), SYSTEM_ACTOR)
    ).items

    by_slug = {str(t.slug): t for t in found}
    assert by_slug["memorabilia"].effective_schema is None
    assert list(by_slug["poster"].effective_schema["properties"]) == [  # type: ignore[index]
        "year",
        "width",
    ]


async def test_subtypes_are_listed_with_their_effective_schema() -> None:
    """The subtype list reports what each subtype uses."""
    _, repos = _uow()
    parent, _ = await _memorabilia_and_poster(repos)

    found = await ListSubtypes(repos, GUARD).handle(
        ListSubtypesQuery(node_type_id=parent.id), SYSTEM_ACTOR
    )

    assert list(found.items[0].effective_schema["properties"]) == ["year", "width"]  # type: ignore[index]


async def test_create_and_update_report_the_effective_schema_too() -> None:
    """The response to a write shows the fields the type now uses."""
    uow, repos = _uow()
    await _add(repos, "memorabilia", _schema({"year": {"type": "number"}}))

    created = await CreateNodeType(uow, GUARD).handle(
        CreateNodeTypeCommand(
            slug="poster",
            label="Poster",
            parent="memorabilia",
            attributes_schema=_schema({"width": {"type": "string"}}),
        ),
        SYSTEM_ACTOR,
    )
    updated = await UpdateNodeType(uow, GUARD).handle(
        UpdateNodeTypeCommand(
            node_type_id=created.id,
            attributes_schema=_schema({"width": {"type": "string"}, "ink": {}}),
        ),
        SYSTEM_ACTOR,
    )

    assert list(created.effective_schema["properties"]) == ["year", "width"]  # type: ignore[index]
    assert list(updated.effective_schema["properties"]) == ["year", "width", "ink"]  # type: ignore[index]


async def test_an_item_of_a_subtype_is_checked_against_its_parents_fields() -> None:
    """A parent's field is validated on the subtype's items."""
    uow, repos = _uow()
    await _memorabilia_and_poster(repos)
    create = CreateNode(uow, GUARD)

    ok = await create.handle(
        CreateNodeCommand(name="Alien", type="poster", attributes={"year": 1979}),
        SYSTEM_ACTOR,
    )
    with pytest.raises(InvalidAttributesError):
        await create.handle(
            CreateNodeCommand(
                name="Bad", type="poster", attributes={"year": "not a number"}
            ),
            SYSTEM_ACTOR,
        )

    assert ok.attributes == {"year": 1979}


async def test_changing_an_items_type_to_a_subtype_checks_its_values() -> None:
    """Editing an item of a subtype validates the parent's fields too."""
    uow, repos = _uow()
    await _memorabilia_and_poster(repos)
    item = await CreateNode(uow, GUARD).handle(
        CreateNodeCommand(name="Alien", type="poster", attributes={"year": 1979}),
        SYSTEM_ACTOR,
    )

    with pytest.raises(InvalidAttributesError):
        await UpdateNode(uow, GUARD).handle(
            UpdateNodeCommand(node_id=item.id, attributes={"year": "later"}),
            SYSTEM_ACTOR,
        )


async def test_a_subtype_may_highlight_a_field_it_inherits() -> None:
    """Highlights are checked against the parent's fields as well as its own."""
    uow, repos = _uow()
    await _add(repos, "memorabilia", _schema({"year": {"type": "number"}}))

    poster = await CreateNodeType(uow, GUARD).handle(
        CreateNodeTypeCommand(
            slug="poster",
            label="Poster",
            parent="memorabilia",
            attributes_schema=_schema(
                {"width": {"type": "string"}},
                highlights={"card": [{"key": "width"}, {"key": "year"}]},
            ),
        ),
        SYSTEM_ACTOR,
    )

    assert poster.parent == "memorabilia"


async def test_a_highlight_naming_no_field_at_all_is_still_refused() -> None:
    """Inheriting widens what a highlight may name, not what it may refer to."""
    uow, repos = _uow()
    await _add(repos, "memorabilia", _schema({"year": {"type": "number"}}))

    with pytest.raises(InvalidSchemaError, match="unknown field 'nope'"):
        await CreateNodeType(uow, GUARD).handle(
            CreateNodeTypeCommand(
                slug="poster",
                label="Poster",
                parent="memorabilia",
                attributes_schema=_schema(
                    {"width": {"type": "string"}},
                    highlights={"card": [{"key": "nope"}]},
                ),
            ),
            SYSTEM_ACTOR,
        )


async def test_updating_a_subtypes_highlights_sees_the_parents_fields() -> None:
    """The same check applies when an existing subtype's schema is replaced."""
    uow, repos = _uow()
    _, poster = await _memorabilia_and_poster(repos)

    updated = await UpdateNodeType(uow, GUARD).handle(
        UpdateNodeTypeCommand(
            node_type_id=poster.id,
            attributes_schema=_schema(
                {"width": {"type": "string"}},
                highlights={"card": [{"key": "year"}]},
            ),
        ),
        SYSTEM_ACTOR,
    )

    assert updated.attributes_schema is not None
