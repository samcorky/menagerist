import pytest

from app.modules.graph.domain.edge_type import EdgeType
from app.shared_kernel.errors import ValidationError


def test_create_sets_fields_and_matching_timestamps() -> None:
    """EdgeType.create sets all fields and equal created/updated timestamps."""
    et = EdgeType.create(
        slug="directed-by",
        label="Directed By",
        reverse_label="Directed",
        description="Links a film to its director.",
        directional=True,
        attributes_schema={"fields": []},
    )

    assert str(et.slug) == "directed-by"
    assert et.label == "Directed By"
    assert et.reverse_label == "Directed"
    assert et.description == "Links a film to its director."
    assert et.directional is True
    assert et.attributes_schema == {"fields": []}
    assert et.created_at == et.updated_at
    assert et.is_deleted is False


def test_create_defaults_optional_fields() -> None:
    """EdgeType.create without optional args uses sensible defaults."""
    et = EdgeType.create(slug="related-to", label="Related To")

    assert et.reverse_label is None
    assert et.description is None
    assert et.directional is True
    assert et.attributes_schema is None


def test_create_slugifies_slug() -> None:
    """EdgeType.create wraps the slug in a Slug value object that normalises it."""
    et = EdgeType.create(slug="Directed By", label="Directed By")

    assert str(et.slug) == "directed-by"


@pytest.mark.parametrize("label", ["", "   "])
def test_create_rejects_empty_or_blank_label(label: str) -> None:
    """EdgeType.create raises ValidationError for an empty or whitespace-only label."""
    with pytest.raises(ValidationError, match="label must be provided"):
        EdgeType.create(slug="related-to", label=label)


def test_slug_is_immutable() -> None:
    """update() has no slug parameter — the slug cannot be changed after creation."""
    et = EdgeType.create(slug="directed-by", label="Directed By")
    original_slug = et.slug

    et.update(label="Helmed By")

    assert et.slug is original_slug


def test_update_changes_label_and_bumps_updated_at() -> None:
    """update() with a new label overwrites label and bumps updated_at."""
    et = EdgeType.create(slug="directed-by", label="Directed By")
    original_updated_at = et.updated_at

    et.update(label="Helmed By")

    assert et.label == "Helmed By"
    assert et.updated_at >= original_updated_at


def test_update_changes_reverse_label() -> None:
    """update() with a reverse_label overwrites it."""
    et = EdgeType.create(slug="directed-by", label="Directed By")

    et.update(reverse_label="Director Of")

    assert et.reverse_label == "Director Of"


def test_update_changes_directional() -> None:
    """update() can toggle the directional flag."""
    et = EdgeType.create(slug="related-to", label="Related To", directional=True)

    et.update(directional=False)

    assert et.directional is False


def test_update_changes_attributes_schema() -> None:
    """update() replaces attributes_schema when provided."""
    schema = {"fields": [{"key": "since", "label": "Since", "type": "date"}]}
    et = EdgeType.create(slug="directed-by", label="Directed By")

    et.update(attributes_schema=schema)

    assert et.attributes_schema == schema


def test_update_leaves_unspecified_fields_unchanged() -> None:
    """update() with no arguments leaves all fields untouched."""
    et = EdgeType.create(
        slug="directed-by",
        label="Directed By",
        reverse_label="Directed",
        directional=True,
    )

    et.update()

    assert et.label == "Directed By"
    assert et.reverse_label == "Directed"
    assert et.directional is True


@pytest.mark.parametrize("label", ["", "   "])
def test_update_rejects_empty_or_blank_label(label: str) -> None:
    """update() raises ValidationError for an empty or whitespace-only label."""
    et = EdgeType.create(slug="directed-by", label="Directed By")

    with pytest.raises(ValidationError, match="label must be provided"):
        et.update(label=label)
