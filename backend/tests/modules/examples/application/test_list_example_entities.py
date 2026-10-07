import uuid

from app.modules.examples.adapters.persistence.in_memory_installation_repository import (  # noqa: E501
    InMemoryInstallationRepository,
)
from app.modules.examples.application.list_example_entities import (
    ListExampleEntities,
    ListExampleEntitiesQuery,
)
from app.modules.examples.domain.installation import EntityKind, Installation, Outcome
from app.modules.examples.ports.unit_of_work import ExampleRepos
from app.shared_kernel.actor import SYSTEM_ACTOR


def _installation(
    pack_id: str, *entities: tuple[EntityKind, uuid.UUID]
) -> Installation:
    """Build an installing installation recording the given entities."""
    installation = Installation.start(pack_id)
    for kind, entity_id in entities:
        installation.record(kind, str(entity_id), "label", entity_id, "hash")
    return installation


async def _list(repo: InMemoryInstallationRepository) -> tuple[list[uuid.UUID], ...]:
    """Run the query and return the item ids and item type ids."""
    result = await ListExampleEntities(ExampleRepos(installations=repo)).handle(
        ListExampleEntitiesQuery(), SYSTEM_ACTOR
    )
    return result.item_ids, result.item_type_ids


async def test_lists_owned_items_and_item_types_across_installations() -> None:
    """Owned items and item types are grouped; other kinds are ignored."""
    repo = InMemoryInstallationRepository()
    item_a, item_b, type_a, preset = (uuid.uuid7() for _ in range(4))
    first = _installation(
        "one",
        (EntityKind.ITEM, item_a),
        (EntityKind.ITEM_TYPE, type_a),
        (EntityKind.PRESET, preset),
    )
    first.mark_installed()
    second = _installation("two", (EntityKind.ITEM, item_b))
    await repo.add(first)
    await repo.add(second)

    item_ids, item_type_ids = await _list(repo)

    assert sorted(item_ids) == sorted([item_a, item_b])
    assert item_type_ids == [type_a]


async def test_excludes_removed_and_kept_records() -> None:
    """Records no longer owned by the pack are not listed."""
    repo = InMemoryInstallationRepository()
    owned, removed, kept, kept_type = (uuid.uuid7() for _ in range(4))
    installation = _installation(
        "one",
        (EntityKind.ITEM, owned),
        (EntityKind.ITEM, removed),
        (EntityKind.ITEM, kept),
        (EntityKind.ITEM_TYPE, kept_type),
    )
    installation.settle(removed, Outcome.REMOVED)
    installation.settle(kept, Outcome.KEPT, "edited")
    installation.settle(kept_type, Outcome.KEPT, "edited")
    installation.mark_installed()
    await repo.add(installation)

    item_ids, item_type_ids = await _list(repo)

    assert item_ids == [owned]
    assert item_type_ids == []


async def test_excludes_removed_installations() -> None:
    """A removed installation contributes nothing."""
    repo = InMemoryInstallationRepository()
    installation = Installation.start("one")
    installation.mark_removed()
    await repo.add(installation)

    assert await _list(repo) == ([], [])


async def test_is_empty_with_no_installations() -> None:
    """No installations means no ids."""
    assert await _list(InMemoryInstallationRepository()) == ([], [])
