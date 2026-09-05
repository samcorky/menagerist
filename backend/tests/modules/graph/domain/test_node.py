import pytest

from app.modules.graph.domain.node import Node
from app.shared_kernel.errors import ValidationError


def test_create_sets_fields_and_matching_timestamps() -> None:
    """Node.create sets fields and equal created/updated timestamps."""
    node = Node.create(
        name="Alien",
        type="film",
        description="A 1979 science fiction horror film directed by Ridley Scott.",
        attributes={"title": "Alien"},
    )

    assert node.name == "Alien"
    assert node.type == "film"
    assert (
        node.description
        == "A 1979 science fiction horror film directed by Ridley Scott."
    )
    assert node.attributes == {"title": "Alien"}
    assert node.created_at == node.updated_at
    assert node.is_deleted is False


def test_create_defaults_attributes_to_empty_dict() -> None:
    """Node.create without attributes defaults to an empty dict."""
    node = Node.create(name="Alien", type="film")

    assert node.attributes == {}


def test_create_defaults_description_to_none() -> None:
    """Node.create without description defaults to None."""
    node = Node.create(name="Alien", type="film")

    assert node.description is None


@pytest.mark.parametrize("name", ["", "   "])
def test_create_rejects_empty_or_blank_name(name: str) -> None:
    """Node.create raises ValidationError for empty or whitespace-only name."""
    with pytest.raises(ValidationError, match="name must be provided"):
        Node.create(name=name, type="dummy")


@pytest.mark.parametrize("type_", ["", "   "])
def test_create_rejects_empty_or_blank_type(type_: str) -> None:
    """Node.create raises ValidationError for an empty or whitespace-only type."""
    with pytest.raises(
        ValidationError, match="type must be a non-empty string when provided"
    ):
        Node.create(name="dummy", type=type_)


@pytest.mark.parametrize(
    ("input_type", "expected_type"),
    [
        ("film", "film"),
        ("   film   ", "film"),
        ("Film", "film"),
        ("   Film   ", "film"),
        ("Science Fiction Film", "science-fiction-film"),
        ("sci-fi!!!!", "sci-fi"),
        ("sci--fi", "sci-fi"),
    ],
)
def test_create_slugifies_type(input_type: str, expected_type: str) -> None:
    """Node.create slugifies the type."""
    node = Node.create(name="Alien", type=input_type)

    assert node.type == expected_type


def test_create_allows_null_type() -> None:
    """Node.create with no type produces a node with type=None."""
    node = Node.create(name="Quick capture")

    assert node.type is None


def test_create_rejects_type_that_slugifies_to_empty_string() -> None:
    """Node.create raises ValidationError for a type that slugs to an empty string."""
    with pytest.raises(
        ValidationError, match="type must be a non-empty string when provided"
    ):
        Node.create(name="dummy", type="!!!")


def test_update_applies_provided_fields_and_touches_updated_at() -> None:
    """update() overwrites only the fields it's given and bumps updated_at."""
    node = Node.create(name="Alien", type="film", description="Original")
    original_updated_at = node.updated_at

    node.update(name="Alien (1979)", description="New", attributes={"year": 1979})

    assert node.name == "Alien (1979)"
    assert node.description == "New"
    assert node.attributes == {"year": 1979}
    assert node.updated_at >= original_updated_at


def test_update_leaves_unspecified_fields_unchanged() -> None:
    """update() with no arguments leaves name/description/attributes untouched."""
    node = Node.create(name="Alien", type="film", description="Original")

    node.update()

    assert node.name == "Alien"
    assert node.description == "Original"


@pytest.mark.parametrize("name", ["", "   "])
def test_update_rejects_empty_or_blank_name(name: str) -> None:
    """update() raises ValidationError for an empty or whitespace-only name."""
    node = Node.create(name="Alien", type="film")

    with pytest.raises(ValidationError, match="name must be provided"):
        node.update(name=name)


def test_update_sets_type_when_currently_none() -> None:
    """update() assigns type when the node was created without one."""
    node = Node.create(name="Alien")

    node.update(type="film")

    assert node.type == "film"


def test_update_slugifies_type_on_assignment() -> None:
    """update() slugifies the type the same way create() does."""
    node = Node.create(name="Alien")

    node.update(type="Science Fiction Film")

    assert node.type == "science-fiction-film"


def test_update_rejects_type_change_once_set() -> None:
    """update() raises ValidationError when trying to change an existing type."""
    node = Node.create(name="Alien", type="film")

    with pytest.raises(ValidationError, match="type cannot be changed after it is set"):
        node.update(type="book")


@pytest.mark.parametrize("type_", ["", "   ", "!!!"])
def test_update_rejects_type_that_slugifies_to_empty(type_: str) -> None:
    """update() raises when the provided type slugifies to an empty string."""
    node = Node.create(name="Alien")

    with pytest.raises(
        ValidationError, match="type must be a non-empty string when provided"
    ):
        node.update(type=type_)


def test_create_defaults_favourite_to_false() -> None:
    """Node.create without favourite defaults to False."""
    node = Node.create(name="Alien")

    assert node.favourite is False


def test_create_with_favourite_true() -> None:
    """Node.create with favourite=True stores the value."""
    node = Node.create(name="Alien", favourite=True)

    assert node.favourite is True


def test_update_sets_favourite() -> None:
    """update() sets favourite when provided."""
    node = Node.create(name="Alien")

    node.update(favourite=True)

    assert node.favourite is True


def test_update_clears_favourite() -> None:
    """update() can unset favourite by passing False."""
    node = Node.create(name="Alien", favourite=True)

    node.update(favourite=False)

    assert node.favourite is False


def test_update_leaves_favourite_unchanged_when_not_given() -> None:
    """update() without favourite leaves the existing value untouched."""
    node = Node.create(name="Alien", favourite=True)

    node.update(name="Alien (1979)")

    assert node.favourite is True
