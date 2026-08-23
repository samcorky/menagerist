import pytest

from app.modules.graph.domain.node import Node
from app.shared_kernel.errors import ValidationError


def test_create_sets_type_attributes_and_matching_timestamps() -> None:
    """Node.create sets type/attributes and equal created/updated timestamps."""
    node = Node.create(type="film", attributes={"title": "Alien"})

    assert node.type == "film"
    assert node.attributes == {"title": "Alien"}
    assert node.created_at == node.updated_at
    assert node.is_deleted is False


def test_create_defaults_attributes_to_empty_dict() -> None:
    """Node.create without attributes defaults to an empty dict."""
    node = Node.create(type="film")

    assert node.attributes == {}


@pytest.mark.parametrize("type_", ["", "   "])
def test_create_rejects_empty_or_blank_type(type_: str) -> None:
    """Node.create raises ValidationError for an empty or whitespace-only type."""
    with pytest.raises(ValidationError):
        Node.create(type=type_)
