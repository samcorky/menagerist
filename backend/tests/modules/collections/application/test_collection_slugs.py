"""Editable slugs, UUID-shaped slug rejection and id-or-slug resolution."""

import uuid
from typing import TYPE_CHECKING

import pytest

from app.entrypoints.api.shared.access_policy import OwnerAccessPolicy
from app.modules.collections.application.create_collection import (
    CreateCollection,
    CreateCollectionCommand,
)
from app.modules.collections.application.resolve_collection import (
    ResolveCollection,
    ResolveCollectionQuery,
)
from app.modules.collections.application.update_collection import (
    UpdateCollection,
    UpdateCollectionCommand,
)
from app.modules.collections.domain.errors import (
    CollectionNotFoundError,
    InvalidCollectionError,
)
from app.modules.collections.ports.unit_of_work import CollectionsRepos
from app.shared_kernel.actor import Actor
from app.shared_kernel.errors import ConflictError

if TYPE_CHECKING:
    from app.modules.collections.domain.collection import Collection
    from tests.modules.collections.conftest import World

ACTOR = Actor(id=uuid.uuid7())
OTHER = Actor(id=uuid.uuid7())
A_UUID = "01978c3e-2b8b-7c3a-9c2e-3a2f6b9d4e20"


def _repos(world: World) -> CollectionsRepos:
    return CollectionsRepos(
        collections=world.collections, memberships=world.memberships
    )


async def _create(
    world: World, name: str, slug: str | None = None, actor: Actor = ACTOR
) -> Collection:
    return await CreateCollection(world.uow, OwnerAccessPolicy(), world.checker).handle(
        CreateCollectionCommand(name=name, slug=slug), actor
    )


async def _update(
    world: World, collection: Collection, actor: Actor = ACTOR, **fields: object
) -> Collection:
    return await UpdateCollection(world.uow, OwnerAccessPolicy(), world.checker).handle(
        UpdateCollectionCommand(collection_id=collection.id, **fields),  # type: ignore[arg-type]
        actor,
    )


async def test_slug_change_is_normalised_and_committed(world: World) -> None:
    """Slug change is normalised and committed."""
    shelf = await _create(world, "Shelf")
    world.uow.committed = False

    result = await _update(world, shelf, slug="  My New Link! ")

    assert result.slug.value == "my-new-link"
    assert world.uow.committed is True
    found = await world.collections.get_by_slug(
        "my-new-link", scope=OwnerAccessPolicy().scope_for(ACTOR)
    )
    assert found is shelf
    old = await world.collections.get_by_slug(
        "shelf", scope=OwnerAccessPolicy().scope_for(ACTOR)
    )
    assert old is None


async def test_slug_taken_by_another_live_collection_conflicts(world: World) -> None:
    """Slug taken by another live collection conflicts."""
    await _create(world, "Taken")
    shelf = await _create(world, "Shelf")

    with pytest.raises(ConflictError):
        await _update(world, shelf, slug="taken")

    assert shelf.slug.value == "shelf"


async def test_unchanged_slug_is_a_no_op_success(world: World) -> None:
    """Unchanged slug is a no op success."""
    shelf = await _create(world, "Shelf")

    result = await _update(world, shelf, slug="Shelf")

    assert result.slug.value == "shelf"


@pytest.mark.parametrize("slug", ["", "   ", "!!!", "---"])
async def test_empty_or_unusable_slug_is_invalid(world: World, slug: str) -> None:
    """Empty or unusable slug is invalid."""
    shelf = await _create(world, "Shelf")

    with pytest.raises(InvalidCollectionError):
        await _update(world, shelf, slug=slug)


@pytest.mark.parametrize(
    "slug", [A_UUID, A_UUID.upper(), A_UUID.replace("-", ""), f" {A_UUID} "]
)
async def test_uuid_shaped_slug_is_invalid_on_update_and_create(
    world: World, slug: str
) -> None:
    """Uuid shaped slug is invalid on update and create."""
    shelf = await _create(world, "Shelf")

    with pytest.raises(InvalidCollectionError):
        await _update(world, shelf, slug=slug)
    with pytest.raises(InvalidCollectionError):
        await _create(world, "Other", slug)


async def test_slug_and_regenerate_together_are_invalid(world: World) -> None:
    """Slug and regenerate together are invalid."""
    shelf = await _create(world, "Shelf")

    with pytest.raises(InvalidCollectionError):
        await _update(world, shelf, slug="x", regenerate_slug=True)


async def test_regenerate_rebuilds_from_the_current_name_with_suffix(
    world: World,
) -> None:
    """Regenerate rebuilds from the current name with suffix."""
    await _create(world, "Films")
    shelf = await _create(world, "Shelf")
    await _update(world, shelf, name="Films")
    assert shelf.slug.value == "shelf"

    result = await _update(world, shelf, regenerate_slug=True)

    assert result.slug.value == "films-2"


async def test_regenerate_excludes_itself(world: World) -> None:
    """Regenerate excludes itself."""
    shelf = await _create(world, "Shelf")

    result = await _update(world, shelf, regenerate_slug=True)

    assert result.slug.value == "shelf"


async def test_regenerate_uses_the_name_given_in_the_same_request(
    world: World,
) -> None:
    """Regenerate uses the name given in the same request."""
    shelf = await _create(world, "Shelf")

    result = await _update(world, shelf, name="Brand New", regenerate_slug=True)

    assert result.slug.value == "brand-new"


async def test_slug_changes_stay_within_one_owner(world: World) -> None:
    """Slug changes stay within one owner."""
    await _create(world, "Shelf", actor=OTHER)
    shelf = await _create(world, "Mine", actor=ACTOR)

    result = await _update(world, shelf, slug="shelf")

    assert result.slug.value == "shelf"


async def test_deleted_collections_slug_is_free_to_take(world: World) -> None:
    """Deleted collections slug is free to take."""
    gone = await _create(world, "Gone")
    gone.soft_delete()
    await world.collections.save(gone)
    shelf = await _create(world, "Shelf")

    result = await _update(world, shelf, slug="gone")

    assert result.slug.value == "gone"


async def test_derived_slug_is_never_uuid_shaped(world: World) -> None:
    """Derived slug is never uuid shaped."""
    first = await _create(world, A_UUID)
    second = await _create(world, A_UUID)

    assert first.slug.value == f"{A_UUID}-2"
    assert second.slug.value == f"{A_UUID}-3"


async def test_resolve_by_id_passes_through_and_by_slug_looks_up(
    world: World,
) -> None:
    """Resolve by id passes through and by slug looks up."""
    shelf = await _create(world, "Shelf")
    resolve = ResolveCollection(_repos(world), OwnerAccessPolicy())

    by_id = await resolve.handle(
        ResolveCollectionQuery(id_or_slug=str(shelf.id)), ACTOR
    )
    by_slug = await resolve.handle(ResolveCollectionQuery(id_or_slug="shelf"), ACTOR)

    assert by_id == by_slug == shelf.id


async def test_resolve_unknown_or_other_owners_slug_is_not_found(
    world: World,
) -> None:
    """Resolve unknown or other owners slug is not found."""
    await _create(world, "Shelf", actor=OTHER)
    resolve = ResolveCollection(_repos(world), OwnerAccessPolicy())

    for slug in ("shelf", "nothing"):
        with pytest.raises(CollectionNotFoundError):
            await resolve.handle(ResolveCollectionQuery(id_or_slug=slug), ACTOR)
