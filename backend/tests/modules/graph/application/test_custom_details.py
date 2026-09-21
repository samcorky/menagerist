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
from app.modules.graph.application.custom_details import (
    MAX_CUSTOM_DETAILS,
    MAX_CUSTOM_NAME_LENGTH,
    check_custom_details,
)
from app.modules.graph.application.update_node import UpdateNode, UpdateNodeCommand
from app.modules.graph.domain.errors import InvalidAttributesError
from app.modules.graph.domain.node import Node
from app.modules.graph.domain.node_type import NodeType
from app.modules.graph.ports.unit_of_work import GraphRepos
from app.shared_kernel.actor import SYSTEM_ACTOR
from app.shared_kernel.unit_of_work import InMemoryUnitOfWork

_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "director": {"type": "string"},
        "old": {"type": "string", "x-menagerist": {"archived": True}},
    },
}


def _uow() -> tuple[InMemoryUnitOfWork[GraphRepos], GraphRepos]:
    repos = GraphRepos(
        nodes=InMemoryNodeRepository(),
        edges=InMemoryEdgeRepository(),
        node_types=InMemoryNodeTypeRepository(),
        edge_types=InMemoryEdgeTypeRepository(),
    )
    return InMemoryUnitOfWork(repos), repos


def _many(count: int) -> dict[str, Any]:
    return {f"detail {i:03d}": i for i in range(count)}


def _messages(exc: pytest.ExceptionInfo[InvalidAttributesError]) -> list[str]:
    return [e["message"] for e in exc.value.validation_errors]


def test_accepts_ordinary_details_and_schema_keys() -> None:
    """Names with spaces, case and unicode are fine; schema keys are not custom."""
    check_custom_details(
        _SCHEMA, {"director": "x", "Region": "EU", "café notes": "y", "old": "z"}
    )
    check_custom_details(None, {"Region": "EU"})
    check_custom_details(None, {})


@pytest.mark.parametrize("name", ["", "   ", " lead", "trail ", "x" * 101])
def test_rejects_bad_new_names(name: str) -> None:
    """Blank, padded and over-long names are rejected with the name as path."""
    with pytest.raises(InvalidAttributesError) as exc_info:
        check_custom_details(_SCHEMA, {name: 1})

    error = exc_info.value.validation_errors[0]
    assert error["path"] == "/" + name
    assert error["keyword"] == "customDetail"


def test_accepts_a_name_of_exactly_the_limit() -> None:
    """The name limit is inclusive."""
    check_custom_details(None, {"x" * MAX_CUSTOM_NAME_LENGTH: 1})


def test_existing_bad_names_do_not_block_other_edits() -> None:
    """A name that was already stored is not checked again."""
    stored = {" odd ": 1, "x" * 150: 2}

    check_custom_details(None, {**stored, "new": 3}, previous=stored)


def test_rejects_more_than_the_limit_of_details() -> None:
    """Going past the count limit is rejected once."""
    with pytest.raises(InvalidAttributesError) as exc_info:
        check_custom_details(_SCHEMA, _many(MAX_CUSTOM_DETAILS + 1))

    assert _messages(exc_info) == [
        f"An item can have at most {MAX_CUSTOM_DETAILS} extra details."
    ]
    check_custom_details(_SCHEMA, _many(MAX_CUSTOM_DETAILS))


def test_schema_keys_do_not_count_towards_the_limit() -> None:
    """Only keys the schema does not define count as details."""
    check_custom_details(_SCHEMA, {**_many(MAX_CUSTOM_DETAILS), "director": "x"})


def test_an_item_already_over_the_limit_can_still_be_edited() -> None:
    """Editing without adding a detail passes; adding one more does not."""
    stored = _many(MAX_CUSTOM_DETAILS + 5)

    check_custom_details(None, {**stored, "detail 000": 99}, previous=stored)
    with pytest.raises(InvalidAttributesError):
        check_custom_details(None, {**stored, "one more": 1}, previous=stored)


async def test_create_node_rejects_a_bad_detail_name() -> None:
    """CreateNode applies the check to untyped and typed nodes."""
    uow, repos = _uow()

    with pytest.raises(InvalidAttributesError):
        await CreateNode(uow).handle(
            CreateNodeCommand(name="A", attributes={"x" * 101: 1}), SYSTEM_ACTOR
        )

    await repos.node_types.add(
        NodeType.create(slug="film", label="Film", attributes_schema=_SCHEMA)
    )
    with pytest.raises(InvalidAttributesError):
        await CreateNode(uow).handle(
            CreateNodeCommand(name="A", type="film", attributes={" ": 1}), SYSTEM_ACTOR
        )
    node = await CreateNode(uow).handle(
        CreateNodeCommand(name="A", type="film", attributes={"Region": "EU"}),
        SYSTEM_ACTOR,
    )
    assert node.attributes == {"Region": "EU"}


async def test_update_node_checks_only_new_details() -> None:
    """UpdateNode rejects a new bad name but keeps stored ones editable."""
    uow, repos = _uow()
    node = Node.create(name="A", attributes={" odd ": 1})
    await repos.nodes.add(node)

    updated = await UpdateNode(uow).handle(
        UpdateNodeCommand(node_id=node.id, attributes={" odd ": 2, "new": 3}),
        SYSTEM_ACTOR,
    )
    assert updated.attributes == {" odd ": 2, "new": 3}

    with pytest.raises(InvalidAttributesError):
        await UpdateNode(uow).handle(
            UpdateNodeCommand(node_id=node.id, attributes={"y" * 101: 1}), SYSTEM_ACTOR
        )
