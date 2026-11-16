import pytest

from app.modules.graph.domain.edge_type import EdgeType
from app.shared_kernel.actor import SYSTEM_ACTOR
from app.shared_kernel.errors import ValidationError


def test_create_sets_fields_and_matching_timestamps() -> None:
    """EdgeType.create sets all fields and equal created/updated timestamps."""
    et = EdgeType.create(
        owner_id=SYSTEM_ACTOR.id,
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
    et = EdgeType.create(
        owner_id=SYSTEM_ACTOR.id, slug="related-to", label="Related To"
    )

    assert et.reverse_label is None
    assert et.description is None
    assert et.directional is True
    assert et.attributes_schema is None


def test_create_slugifies_slug() -> None:
    """EdgeType.create wraps the slug in a Slug value object that normalises it."""
    et = EdgeType.create(
        owner_id=SYSTEM_ACTOR.id, slug="Directed By", label="Directed By"
    )

    assert str(et.slug) == "directed-by"


@pytest.mark.parametrize("label", ["", "   "])
def test_create_rejects_empty_or_blank_label(label: str) -> None:
    """EdgeType.create raises ValidationError for an empty or whitespace-only label."""
    with pytest.raises(ValidationError, match="label must be provided"):
        EdgeType.create(owner_id=SYSTEM_ACTOR.id, slug="related-to", label=label)


def test_slug_is_immutable() -> None:
    """update() has no slug parameter - the slug cannot be changed after creation."""
    et = EdgeType.create(
        owner_id=SYSTEM_ACTOR.id, slug="directed-by", label="Directed By"
    )
    original_slug = et.slug

    et.update(label="Helmed By")

    assert et.slug is original_slug


def test_update_changes_label_and_bumps_updated_at() -> None:
    """update() with a new label overwrites label and bumps updated_at."""
    et = EdgeType.create(
        owner_id=SYSTEM_ACTOR.id, slug="directed-by", label="Directed By"
    )
    original_updated_at = et.updated_at

    et.update(label="Helmed By")

    assert et.label == "Helmed By"
    assert et.updated_at >= original_updated_at


def test_update_changes_reverse_label() -> None:
    """update() with a reverse_label overwrites it."""
    et = EdgeType.create(
        owner_id=SYSTEM_ACTOR.id, slug="directed-by", label="Directed By"
    )

    et.update(reverse_label="Director Of")

    assert et.reverse_label == "Director Of"


def test_update_changes_directional() -> None:
    """update() can toggle the directional flag."""
    et = EdgeType.create(
        owner_id=SYSTEM_ACTOR.id,
        slug="related-to",
        label="Related To",
        directional=True,
    )

    et.update(directional=False)

    assert et.directional is False


def test_update_changes_attributes_schema() -> None:
    """update() replaces attributes_schema when provided."""
    schema = {"fields": [{"key": "since", "label": "Since", "type": "date"}]}
    et = EdgeType.create(
        owner_id=SYSTEM_ACTOR.id, slug="directed-by", label="Directed By"
    )

    et.update(attributes_schema=schema)

    assert et.attributes_schema == schema


def test_update_changes_description() -> None:
    """update() with a description overwrites it."""
    et = EdgeType.create(
        owner_id=SYSTEM_ACTOR.id, slug="directed-by", label="Directed By"
    )

    et.update(description="Links a film to its director.")

    assert et.description == "Links a film to its director."


def test_update_leaves_unspecified_fields_unchanged() -> None:
    """update() with no arguments leaves all fields untouched."""
    et = EdgeType.create(
        owner_id=SYSTEM_ACTOR.id,
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
    et = EdgeType.create(
        owner_id=SYSTEM_ACTOR.id, slug="directed-by", label="Directed By"
    )

    with pytest.raises(ValidationError, match="label must be provided"):
        et.update(label=label)


def _located_in(**extra: object) -> EdgeType:
    return EdgeType.create(
        owner_id=SYSTEM_ACTOR.id,
        slug="located-in",
        label="Located in",
        **extra,  # type: ignore[arg-type]
    )


def test_holder_defaults_to_none_and_can_be_set_and_cleared() -> None:
    """Neither end holds the other until said; `none` clears it again."""
    et = _located_in()
    seen = [et.holder]
    et.update(holder="target")
    seen.append(et.holder)
    et.update(label="Kept in")
    seen.append(et.holder)
    et.update(holder="none")
    seen.append(et.holder)

    assert seen == ["none", "target", "target", "none"]


@pytest.mark.parametrize(
    "extra",
    [
        {"holder": "middle"},
        {"holder": "source", "directional": False},
    ],
)
def test_a_holder_needs_a_known_end_and_a_direction(extra: dict[str, object]) -> None:
    """Only `source`, `target` or `none`, and only with a direction."""
    with pytest.raises(ValidationError):
        _located_in(**extra)


def test_dropping_the_direction_of_a_holding_relationship_is_refused() -> None:
    """The holder has to be cleared in the same change."""
    et = _located_in(holder="target")
    with pytest.raises(ValidationError, match="no direction"):
        et.update(directional=False)
    et.update(directional=False, holder="none")
    assert (et.directional, et.holder) == (False, "none")
