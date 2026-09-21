import json
from pathlib import Path
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
from app.modules.graph.application.create_edge_type import (
    CreateEdgeType,
    CreateEdgeTypeCommand,
)
from app.modules.graph.application.create_node_type import (
    CreateNodeType,
    CreateNodeTypeCommand,
)
from app.modules.graph.application.update_edge_type import (
    UpdateEdgeType,
    UpdateEdgeTypeCommand,
)
from app.modules.graph.application.update_node_type import (
    UpdateNodeType,
    UpdateNodeTypeCommand,
)
from app.modules.graph.domain.edge_type import EdgeType
from app.modules.graph.domain.errors import InvalidAttributesError, InvalidSchemaError
from app.modules.graph.domain.node_type import NodeType
from app.modules.graph.ports.unit_of_work import GraphRepos
from app.shared_kernel.actor import SYSTEM_ACTOR
from app.shared_kernel.unit_of_work import InMemoryUnitOfWork

_FIXTURE = (
    Path(__file__).parents[5] / "contract" / "fixtures" / "regex-conformance.json"
)


def _text_schema(**constraints: object) -> dict[str, Any]:
    return {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "type": "object",
        "properties": {
            "cover_file": {
                "title": "Cover file",
                "type": "string",
                **constraints,
                "x-menagerist": {"kind": "text"},
            }
        },
    }


_BOTH = _text_schema(allOf=[{"pattern": "^cover-"}, {"pattern": r"\.jpg$"}])


def _make_uow() -> tuple[InMemoryUnitOfWork[GraphRepos], GraphRepos]:
    repos = GraphRepos(
        nodes=InMemoryNodeRepository(),
        edges=InMemoryEdgeRepository(),
        node_types=InMemoryNodeTypeRepository(),
        edge_types=InMemoryEdgeTypeRepository(),
    )
    return InMemoryUnitOfWork(repos), repos


def test_valid_value_passes_both_constraints() -> None:
    """A value with the prefix and suffix validates."""
    validate_attributes(_BOTH, {"cover_file": "cover-front.jpg"})


def test_missing_prefix_reports_keyword_and_pattern() -> None:
    """The error names the failing keyword and its pattern for the client to word."""
    with pytest.raises(InvalidAttributesError) as exc_info:
        validate_attributes(_BOTH, {"cover_file": "front.jpg"})

    errors = exc_info.value.validation_errors
    assert len(errors) == 1
    assert errors[0]["path"] == "/cover_file"
    assert errors[0]["keyword"] == "pattern"
    assert errors[0]["value"] == "^cover-"


def test_each_failing_half_is_reported_separately() -> None:
    """Prefix and suffix failures are separate errors, each with its own pattern."""
    with pytest.raises(InvalidAttributesError) as exc_info:
        validate_attributes(_BOTH, {"cover_file": "front.png"})

    values = {e["value"] for e in exc_info.value.validation_errors}
    assert values == {"^cover-", r"\.jpg$"}


def test_omitted_optional_constrained_field_passes() -> None:
    """A constrained field that is left out is not an error."""
    validate_attributes(_BOTH, {})


def test_empty_string_fails_an_anchored_pattern() -> None:
    """The client omits empty values; an empty string that reaches the server fails."""
    with pytest.raises(InvalidAttributesError):
        validate_attributes(_text_schema(pattern="^cover-"), {"cover_file": ""})


def test_unchanged_stale_value_does_not_block_other_edits() -> None:
    """A stored value that no longer matches a new constraint is left alone."""
    schema = _text_schema(pattern="^cover-")
    schema["properties"]["title"] = {"title": "Title", "type": "string"}

    validate_attributes(
        schema,
        {"cover_file": "old.jpg", "title": "New"},
        previous={"cover_file": "old.jpg", "title": "Old"},
    )


def test_group_sub_field_pattern_error_path() -> None:
    """A pattern failure inside a group row carries the full item path."""
    schema = {
        "type": "object",
        "properties": {
            "tracks": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {"code": {"type": "string", "pattern": "^LP-"}},
                },
            }
        },
    }
    with pytest.raises(InvalidAttributesError) as exc_info:
        validate_attributes(schema, {"tracks": [{"code": "X1"}]})

    assert exc_info.value.validation_errors[0]["path"] == "/tracks/0/code"
    assert exc_info.value.validation_errors[0]["value"] == "^LP-"


def test_conformance_cases_match_python_re() -> None:
    """The shared fixture agrees with Python; the frontend suite checks JavaScript."""
    cases = json.loads(_FIXTURE.read_text(encoding="utf-8"))["cases"]
    assert cases
    for case in cases:
        schema = _text_schema(pattern=case["pattern"])
        valid = True
        try:
            validate_attributes(schema, {"cover_file": case["value"]})
        except InvalidAttributesError:
            valid = False
        assert valid is case["expected"], case


_BAD_SCHEMAS = [
    _text_schema(pattern="["),
    _text_schema(pattern="(?<n>a)"),
    _text_schema(allOf=[{"pattern": "^ok"}, {"pattern": "["}]),
]


@pytest.mark.parametrize("schema", _BAD_SCHEMAS)
async def test_create_node_type_rejects_uncompilable_pattern(
    schema: dict[str, Any],
) -> None:
    """CreateNodeType rejects a pattern Python cannot compile."""
    uow, _ = _make_uow()
    with pytest.raises(InvalidSchemaError):
        await CreateNodeType(uow).handle(
            CreateNodeTypeCommand(slug="film", label="Film", attributes_schema=schema),
            SYSTEM_ACTOR,
        )


@pytest.mark.parametrize("schema", _BAD_SCHEMAS)
async def test_update_node_type_rejects_uncompilable_pattern(
    schema: dict[str, Any],
) -> None:
    """UpdateNodeType rejects a pattern Python cannot compile."""
    uow, repos = _make_uow()
    nt = NodeType.create(slug="film", label="Film")
    await repos.node_types.add(nt)
    with pytest.raises(InvalidSchemaError):
        await UpdateNodeType(uow).handle(
            UpdateNodeTypeCommand(node_type_id=nt.id, attributes_schema=schema),
            SYSTEM_ACTOR,
        )


@pytest.mark.parametrize("schema", _BAD_SCHEMAS)
async def test_create_edge_type_rejects_uncompilable_pattern(
    schema: dict[str, Any],
) -> None:
    """CreateEdgeType rejects a pattern Python cannot compile."""
    uow, _ = _make_uow()
    with pytest.raises(InvalidSchemaError):
        await CreateEdgeType(uow).handle(
            CreateEdgeTypeCommand(slug="made", label="Made", attributes_schema=schema),
            SYSTEM_ACTOR,
        )


@pytest.mark.parametrize("schema", _BAD_SCHEMAS)
async def test_update_edge_type_rejects_uncompilable_pattern(
    schema: dict[str, Any],
) -> None:
    """UpdateEdgeType rejects a pattern Python cannot compile."""
    uow, repos = _make_uow()
    et = EdgeType.create(slug="made", label="Made")
    await repos.edge_types.add(et)
    with pytest.raises(InvalidSchemaError):
        await UpdateEdgeType(uow).handle(
            UpdateEdgeTypeCommand(edge_type_id=et.id, attributes_schema=schema),
            SYSTEM_ACTOR,
        )
