import dataclasses
import uuid
from datetime import UTC, datetime

import pytest

from app.modules.collections.domain.collection import (
    Collection,
    CollectionKind,
    Membership,
    Visibility,
)
from app.modules.collections.domain.errors import (
    CollectionNotFoundError,
    InvalidCollectionError,
)
from app.shared_kernel.errors import NotFoundError, ValidationError
from app.shared_kernel.slug import Slug


def _make(name: str = "My vinyl", slug: str = "my-vinyl") -> Collection:
    """Build a collection with fixed inputs."""
    return Collection.create(name=name, slug=Slug(slug), owner_id=uuid.uuid7())


def test_create_sets_identity_timestamps_and_defaults() -> None:
    """A new collection is a live, manual, private shelf with a uuid7 id."""
    owner = uuid.uuid7()
    before = datetime.now(UTC)
    c = Collection.create(
        name="My vinyl", slug=Slug("my-vinyl"), owner_id=owner, description="LPs"
    )
    assert c.id.version == 7
    assert before <= c.created_at <= datetime.now(UTC)
    assert c.updated_at == c.created_at
    assert c.kind is CollectionKind.MANUAL
    assert c.visibility is Visibility.PRIVATE
    assert c.owner_id == owner
    assert c.description == "LPs"
    assert c.deleted_at is None
    assert not c.is_deleted


def test_create_description_defaults_to_none() -> None:
    """Description is optional."""
    assert _make().description is None


def test_create_trims_name() -> None:
    """Surrounding whitespace is removed from the name."""
    assert _make(name="  Funkos \n").name == "Funkos"


@pytest.mark.parametrize("name", ["", "   ", "\t\n", "x" * 121, " " + "x" * 121])
def test_create_rejects_bad_names(name: str) -> None:
    """Empty, blank and over-long names are invalid."""
    with pytest.raises(InvalidCollectionError):
        _make(name=name)


def test_create_accepts_120_characters() -> None:
    """The length limit is inclusive."""
    assert len(_make(name="x" * 120).name) == 120


def test_explicit_slug_is_normalised_by_slug() -> None:
    """The Slug value object normalises an explicit slug."""
    assert _make(slug="To Watch!").slug.value == "to-watch"


def test_rename_changes_name_and_touches_updated_at() -> None:
    """Renaming trims the name and bumps updated_at only."""
    c = _make()
    created = c.created_at
    c.rename("  Records ")
    assert c.name == "Records"
    assert c.updated_at >= created
    assert c.created_at == created


def test_rename_leaves_slug_alone() -> None:
    """The slug is immutable across renames."""
    c = _make()
    c.rename("Something else")
    assert c.slug.value == "my-vinyl"


@pytest.mark.parametrize("name", ["", "  ", "x" * 121])
def test_rename_validates_and_keeps_old_name(name: str) -> None:
    """A bad rename raises and changes nothing."""
    c = _make()
    with pytest.raises(InvalidCollectionError):
        c.rename(name)
    assert c.name == "My vinyl"


def test_soft_delete_marks_deleted() -> None:
    """Soft delete comes from the mixin."""
    c = _make()
    c.soft_delete()
    assert c.is_deleted
    assert c.deleted_at == c.updated_at


def test_membership_is_frozen() -> None:
    """A membership cannot be changed after creation."""
    m = Membership(
        collection_id=uuid.uuid7(), item_id=uuid.uuid7(), added_at=datetime.now(UTC)
    )
    with pytest.raises(dataclasses.FrozenInstanceError):
        m.added_at = datetime.now(UTC)  # type: ignore[misc]


def test_errors_map_to_shared_kernel_bases() -> None:
    """Validation and not-found errors use the bases that map to 422 and 404."""
    assert issubclass(InvalidCollectionError, ValidationError)
    assert issubclass(CollectionNotFoundError, NotFoundError)
