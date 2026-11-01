import pytest

from app.modules.graph.domain.node_type import NodeType
from app.shared_kernel.errors import ValidationError


def test_create_sets_fields_and_matching_timestamps() -> None:
    """NodeType.create sets all fields and equal created/updated timestamps."""
    nt = NodeType.create(
        slug="film",
        label="Film",
        description="A motion picture.",
        attributes_schema={"fields": []},
    )

    assert str(nt.slug) == "film"
    assert nt.label == "Film"
    assert nt.description == "A motion picture."
    assert nt.attributes_schema == {"fields": []}
    assert nt.created_at == nt.updated_at
    assert nt.is_deleted is False


def test_create_defaults_description_and_schema_to_none() -> None:
    """NodeType.create without optional args defaults them to None."""
    nt = NodeType.create(slug="film", label="Film")

    assert nt.description is None
    assert nt.attributes_schema is None


def test_create_slugifies_slug() -> None:
    """NodeType.create wraps the slug in a Slug value object that normalises it."""
    nt = NodeType.create(slug="Science Fiction", label="Science Fiction")

    assert str(nt.slug) == "science-fiction"


@pytest.mark.parametrize("label", ["", "   "])
def test_create_rejects_empty_or_blank_label(label: str) -> None:
    """NodeType.create raises ValidationError for an empty or whitespace-only label."""
    with pytest.raises(ValidationError, match="label must be provided"):
        NodeType.create(slug="film", label=label)


def test_slug_is_immutable() -> None:
    """update() has no slug parameter - the slug cannot be changed after creation."""
    nt = NodeType.create(slug="film", label="Film")
    original_slug = nt.slug

    nt.update(label="Updated Film")

    assert nt.slug is original_slug


def test_update_changes_label_and_bumps_updated_at() -> None:
    """update() with a new label overwrites label and bumps updated_at."""
    nt = NodeType.create(slug="film", label="Film")
    original_updated_at = nt.updated_at

    nt.update(label="Movie")

    assert nt.label == "Movie"
    assert nt.updated_at >= original_updated_at


def test_update_changes_description() -> None:
    """update() with a description overwrites the existing description."""
    nt = NodeType.create(slug="film", label="Film", description="Old")

    nt.update(description="New")

    assert nt.description == "New"


def test_update_changes_attributes_schema() -> None:
    """update() replaces attributes_schema when provided."""
    schema = {"fields": [{"key": "year", "label": "Year", "type": "number"}]}
    nt = NodeType.create(slug="film", label="Film")

    nt.update(attributes_schema=schema)

    assert nt.attributes_schema == schema


def test_update_leaves_unspecified_fields_unchanged() -> None:
    """update() with no arguments leaves all fields untouched."""
    nt = NodeType.create(slug="film", label="Film", description="Original")

    nt.update()

    assert nt.label == "Film"
    assert nt.description == "Original"
    assert nt.attributes_schema is None


@pytest.mark.parametrize("label", ["", "   "])
def test_update_rejects_empty_or_blank_label(label: str) -> None:
    """update() raises ValidationError for an empty or whitespace-only label."""
    nt = NodeType.create(slug="film", label="Film")

    with pytest.raises(ValidationError, match="label must be provided"):
        nt.update(label=label)


def test_create_defaults_icon_and_colour_to_none() -> None:
    """NodeType.create without an icon or colour leaves both unset."""
    nt = NodeType.create(slug="film", label="Film")

    assert nt.icon is None
    assert nt.colour is None


def test_create_stores_an_icon_and_colour() -> None:
    """NodeType.create keeps a valid icon name and palette colour."""
    nt = NodeType.create(slug="film", label="Film", icon="clapperboard", colour="red")

    assert nt.icon == "clapperboard"
    assert nt.colour == "red"


def test_create_treats_a_blank_icon_or_colour_as_unset() -> None:
    """A blank icon or colour is the same as none."""
    nt = NodeType.create(slug="film", label="Film", icon="  ", colour="")

    assert nt.icon is None
    assert nt.colour is None


@pytest.mark.parametrize(
    "icon", ["Film", "my icon", "-film", "film-", "film--roll", "1film", "x" * 65]
)
def test_create_rejects_an_icon_that_is_not_a_lucide_name(icon: str) -> None:
    """Icons are kebab-case Lucide names of at most 64 characters."""
    with pytest.raises(ValidationError, match="icon must be"):
        NodeType.create(slug="film", label="Film", icon=icon)


@pytest.mark.parametrize("colour", ["purple", "#ff0000", "Red"])
def test_create_rejects_a_colour_outside_the_palette(colour: str) -> None:
    """Colours are palette keys, not free values."""
    with pytest.raises(ValidationError, match="colour must be one of"):
        NodeType.create(slug="film", label="Film", colour=colour)


def test_update_sets_changes_and_clears_icon_and_colour() -> None:
    """update() sets an icon and colour and keeps them when omitted; clear_* removes."""
    nt = NodeType.create(slug="film", label="Film")

    nt.update(icon="film", colour="blue")
    assert (nt.icon, nt.colour) == ("film", "blue")

    nt.update(label="Movie")
    assert (nt.icon, nt.colour) == ("film", "blue")

    nt.clear_icon()
    nt.clear_colour()
    assert (nt.icon, nt.colour) == (None, None)


@pytest.mark.parametrize("blank", ["", "   "])
def test_update_rejects_a_blank_icon_or_colour_instead_of_clearing(blank: str) -> None:
    """A blank string is an error; clearing is clear_icon() and clear_colour()."""
    nt = NodeType.create(slug="film", label="Film", icon="film", colour="blue")

    with pytest.raises(ValidationError, match="icon must be"):
        nt.update(icon=blank)
    with pytest.raises(ValidationError, match="colour must be"):
        nt.update(colour=blank)

    assert (nt.icon, nt.colour) == ("film", "blue")


def test_update_validates_icon_and_colour() -> None:
    """update() rejects the same bad values create() does."""
    nt = NodeType.create(slug="film", label="Film")

    with pytest.raises(ValidationError, match="icon must be"):
        nt.update(icon="Not An Icon")
    with pytest.raises(ValidationError, match="colour must be one of"):
        nt.update(colour="purple")
