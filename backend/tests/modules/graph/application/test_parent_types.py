"""The rules that keep a type's parent to one level and its fields free of clashes."""

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
from app.modules.graph.application.create_node_type import (
    CreateNodeType,
    CreateNodeTypeCommand,
)
from app.modules.graph.application.delete_node_type import (
    DeleteNodeType,
    DeleteNodeTypeCommand,
)
from app.modules.graph.application.delete_unused_node_type import (
    DeleteUnusedNodeType,
    DeleteUnusedNodeTypeCommand,
)
from app.modules.graph.application.update_node_type import (
    UpdateNodeType,
    UpdateNodeTypeCommand,
)
from app.modules.graph.domain.errors import (
    InvalidParentTypeError,
    NodeTypeHasSubtypesError,
)
from app.modules.graph.domain.node_type import NodeType
from app.modules.graph.ports.unit_of_work import GraphRepos
from app.shared_kernel.access_guard import InMemoryAccessGuard
from app.shared_kernel.actor import SYSTEM_ACTOR
from app.shared_kernel.unit_of_work import InMemoryUnitOfWork

type Uow = InMemoryUnitOfWork[GraphRepos]


def _schema(*keys: str) -> dict[str, Any]:
    return {"type": "object", "properties": {k: {"type": "string"} for k in keys}}


def _uow() -> tuple[Uow, GraphRepos]:
    repos = GraphRepos(
        nodes=InMemoryNodeRepository(),
        edges=InMemoryEdgeRepository(),
        node_types=InMemoryNodeTypeRepository(),
        edge_types=InMemoryEdgeTypeRepository(),
    )
    return InMemoryUnitOfWork(repos), repos


async def _add(
    repos: GraphRepos,
    slug: str,
    *,
    parent: str | None = None,
    keys: tuple[str, ...] = (),
) -> NodeType:
    node_type = NodeType.create(
        owner_id=SYSTEM_ACTOR.id,
        slug=slug,
        label=slug.title(),
        parent=parent,
        attributes_schema=_schema(*keys) if keys else None,
    )
    await repos.node_types.add(node_type)
    return node_type


async def _create(
    uow: Uow,
    slug: str,
    *,
    parent: str | None = None,
    attributes_schema: dict[str, Any] | None = None,
) -> NodeType:
    return await CreateNodeType(uow, InMemoryAccessGuard()).handle(
        CreateNodeTypeCommand(
            slug=slug,
            label=slug.title(),
            parent=parent,
            attributes_schema=attributes_schema,
        ),
        SYSTEM_ACTOR,
    )


async def _update(
    uow: Uow,
    node_type: NodeType,
    *,
    label: str | None = None,
    parent: str | None = None,
    clear_parent: bool = False,
    attributes_schema: dict[str, Any] | None = None,
) -> NodeType:
    return await UpdateNodeType(uow, InMemoryAccessGuard()).handle(
        UpdateNodeTypeCommand(
            node_type_id=node_type.id,
            label=label,
            parent=parent,
            clear_parent=clear_parent,
            attributes_schema=attributes_schema,
        ),
        SYSTEM_ACTOR,
    )


async def test_create_a_subtype_of_a_top_level_type() -> None:
    """A type can be created as a subtype of an existing top-level type."""
    uow, repos = _uow()
    await _add(repos, "memorabilia")

    poster = await _create(uow, "poster", parent="memorabilia")

    assert poster.parent == "memorabilia"
    assert uow.committed is True


async def test_create_refuses_a_parent_that_does_not_exist() -> None:
    """A parent has to be one of the person's types."""
    uow, _ = _uow()

    with pytest.raises(InvalidParentTypeError, match="'memorabilia' not found"):
        await _create(uow, "poster", parent="memorabilia")

    assert uow.committed is False


async def test_create_refuses_a_parent_that_is_itself_a_subtype() -> None:
    """Only one level: a subtype cannot be a parent."""
    uow, repos = _uow()
    await _add(repos, "memorabilia")
    await _add(repos, "poster", parent="memorabilia")

    with pytest.raises(InvalidParentTypeError, match="one level"):
        await _create(uow, "film-poster", parent="poster")


async def test_create_refuses_a_field_the_parent_already_has() -> None:
    """One key, one definition: a subtype cannot redefine a parent's field."""
    uow, repos = _uow()
    await _add(repos, "memorabilia", keys=("condition", "value"))

    with pytest.raises(InvalidParentTypeError, match="condition"):
        await _create(
            uow, "poster", parent="memorabilia", attributes_schema=_schema("condition")
        )


async def test_create_allows_fields_the_parent_does_not_have() -> None:
    """A subtype adds its own fields beside its parent's."""
    uow, repos = _uow()
    await _add(repos, "memorabilia", keys=("condition",))

    poster = await _create(
        uow, "poster", parent="memorabilia", attributes_schema=_schema("width")
    )

    assert poster.parent == "memorabilia"


async def test_update_gives_a_type_a_parent_and_clears_it_again() -> None:
    """A parent can be added to an existing type and taken away again."""
    uow, repos = _uow()
    await _add(repos, "memorabilia")
    poster = await _add(repos, "poster")

    await _update(uow, poster, parent="memorabilia")
    assert poster.parent == "memorabilia"

    await _update(uow, poster, clear_parent=True)
    assert poster.parent is None


async def test_update_refuses_a_type_as_its_own_parent() -> None:
    """The slug is the identity, so a type cannot name itself."""
    uow, repos = _uow()
    poster = await _add(repos, "poster")

    with pytest.raises(InvalidParentTypeError, match="its own parent"):
        await _update(uow, poster, parent="Poster")

    assert poster.parent is None


async def test_update_refuses_a_parent_for_a_type_that_has_subtypes() -> None:
    """A type with subtypes is a parent, so it stays top-level."""
    uow, repos = _uow()
    await _add(repos, "merchandise")
    memorabilia = await _add(repos, "memorabilia")
    await _add(repos, "poster", parent="memorabilia")

    with pytest.raises(InvalidParentTypeError, match="has subtypes"):
        await _update(uow, memorabilia, parent="merchandise")


async def test_update_refuses_a_subtype_field_that_clashes_with_its_parent() -> None:
    """Adding a field the parent already has to a subtype is refused."""
    uow, repos = _uow()
    await _add(repos, "memorabilia", keys=("condition",))
    poster = await _add(repos, "poster", parent="memorabilia", keys=("width",))

    with pytest.raises(InvalidParentTypeError, match="condition"):
        await _update(uow, poster, attributes_schema=_schema("width", "condition"))


async def test_update_refuses_a_parent_field_a_subtype_already_has() -> None:
    """Adding a field to a parent that one of its subtypes has is refused."""
    uow, repos = _uow()
    memorabilia = await _add(repos, "memorabilia", keys=("condition",))
    await _add(repos, "poster", parent="memorabilia", keys=("width",))

    with pytest.raises(InvalidParentTypeError, match=r"poster.*width"):
        await _update(uow, memorabilia, attributes_schema=_schema("condition", "width"))


async def test_update_lets_a_parent_gain_a_field_no_subtype_has() -> None:
    """A parent can gain fields that clash with nothing."""
    uow, repos = _uow()
    memorabilia = await _add(repos, "memorabilia", keys=("condition",))
    await _add(repos, "poster", parent="memorabilia", keys=("width",))

    await _update(uow, memorabilia, attributes_schema=_schema("condition", "value"))

    schema = memorabilia.attributes_schema or {}
    assert set(schema["properties"]) == {"condition", "value"}


async def test_update_unrelated_to_parent_or_fields_changes_nothing_else() -> None:
    """Editing only a label leaves the parent as it was."""
    uow, repos = _uow()
    await _add(repos, "memorabilia")
    poster = await _add(repos, "poster", parent="memorabilia")

    await _update(uow, poster, label="Film poster")

    assert (poster.label, poster.parent) == ("Film poster", "memorabilia")


async def test_delete_refuses_a_parent_that_has_subtypes() -> None:
    """The error names the subtypes, and nothing is deleted."""
    uow, repos = _uow()
    memorabilia = await _add(repos, "memorabilia")
    await _add(repos, "poster", parent="memorabilia")
    await _add(repos, "figure", parent="memorabilia")

    with pytest.raises(NodeTypeHasSubtypesError, match="poster, figure"):
        await DeleteNodeType(uow, InMemoryAccessGuard()).handle(
            DeleteNodeTypeCommand(node_type_id=memorabilia.id), SYSTEM_ACTOR
        )

    assert memorabilia.is_deleted is False
    assert uow.committed is False


async def test_delete_removes_a_subtype_and_then_its_parent() -> None:
    """Once its subtypes are gone the parent can be deleted."""
    uow, repos = _uow()
    memorabilia = await _add(repos, "memorabilia")
    poster = await _add(repos, "poster", parent="memorabilia")
    delete = DeleteNodeType(uow, InMemoryAccessGuard())

    await delete.handle(DeleteNodeTypeCommand(node_type_id=poster.id), SYSTEM_ACTOR)
    await delete.handle(
        DeleteNodeTypeCommand(node_type_id=memorabilia.id), SYSTEM_ACTOR
    )

    assert (poster.is_deleted, memorabilia.is_deleted) == (True, True)


async def test_delete_unused_also_refuses_a_parent_that_has_subtypes() -> None:
    """The example-pack removal path keeps the same rule."""
    uow, repos = _uow()
    memorabilia = await _add(repos, "memorabilia")
    await _add(repos, "poster", parent="memorabilia")

    with pytest.raises(NodeTypeHasSubtypesError, match="poster"):
        await DeleteUnusedNodeType(uow, InMemoryAccessGuard()).handle(
            DeleteUnusedNodeTypeCommand(node_type_id=memorabilia.id), SYSTEM_ACTOR
        )

    assert memorabilia.is_deleted is False
