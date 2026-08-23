import uuid

import pytest

from app.modules.graph.domain.edge import Edge
from app.shared_kernel.errors import ValidationError


def test_create_sets_fields_and_matching_timestamps() -> None:
    """Edge.create sets fields and equal created/updated timestamps."""
    source_id = uuid.uuid4()
    target_id = uuid.uuid4()

    edge = Edge.create(
        source_id=source_id,
        target_id=target_id,
        type="signed-by",
        attributes={"date": "1979-05-25"},
    )

    assert edge.source_id == source_id
    assert edge.target_id == target_id
    assert edge.type == "signed-by"
    assert edge.attributes == {"date": "1979-05-25"}
    assert edge.created_at == edge.updated_at
    assert edge.is_deleted is False


def test_create_defaults_attributes_to_empty_dict() -> None:
    """Edge.create without attributes defaults to an empty dict."""
    edge = Edge.create(
        source_id=uuid.uuid4(), target_id=uuid.uuid4(), type="related-to"
    )

    assert edge.attributes == {}


@pytest.mark.parametrize("type_", ["", "   "])
def test_create_rejects_empty_or_blank_type(type_: str) -> None:
    """Edge.create raises ValidationError for an empty or whitespace-only type."""
    with pytest.raises(ValidationError, match="type must be provided"):
        Edge.create(source_id=uuid.uuid4(), target_id=uuid.uuid4(), type=type_)


@pytest.mark.parametrize(
    ("input_type", "expected_type"),
    [
        ("related-to", "related-to"),
        ("   Signed By   ", "signed-by"),
        ("Appeared In!!!", "appeared-in"),
    ],
)
def test_create_slugifies_type(input_type: str, expected_type: str) -> None:
    """Edge.create slugifies the type."""
    edge = Edge.create(source_id=uuid.uuid4(), target_id=uuid.uuid4(), type=input_type)

    assert edge.type == expected_type


def test_create_rejects_self_loop() -> None:
    """Edge.create raises ValidationError when source_id equals target_id."""
    node_id = uuid.uuid4()

    with pytest.raises(ValidationError, match="cannot connect a node to itself"):
        Edge.create(source_id=node_id, target_id=node_id, type="related-to")


def test_update_applies_attributes_and_touches_updated_at() -> None:
    """update() overwrites attributes and bumps updated_at."""
    edge = Edge.create(source_id=uuid.uuid4(), target_id=uuid.uuid4(), type="owns")
    original_updated_at = edge.updated_at

    edge.update(attributes={"since": "1979"})

    assert edge.attributes == {"since": "1979"}
    assert edge.updated_at >= original_updated_at


def test_update_leaves_attributes_unchanged_when_not_given() -> None:
    """update() with no arguments leaves attributes untouched."""
    edge = Edge.create(
        source_id=uuid.uuid4(),
        target_id=uuid.uuid4(),
        type="owns",
        attributes={"since": "1979"},
    )

    edge.update()

    assert edge.attributes == {"since": "1979"}
