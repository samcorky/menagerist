import uuid

from app.modules.examples.adapters.persistence.in_memory_installation_repository import (  # noqa: E501
    InMemoryInstallationRepository,
)
from app.modules.examples.domain.installation import Installation


async def test_add_get_and_save_round_trip() -> None:
    """An added installation is retrievable and saved changes are visible."""
    repo = InMemoryInstallationRepository()
    installation = Installation.start("demo")
    await repo.add(installation)
    assert await repo.get(installation.id) is installation
    installation.mark_installed()
    await repo.save(installation)
    stored = await repo.get(installation.id)
    assert stored is not None
    assert stored.status.value == "installed"


async def test_get_returns_none_for_an_unknown_id() -> None:
    """An unknown id yields `None`."""
    assert await InMemoryInstallationRepository().get(uuid.uuid7()) is None


async def test_active_lookup_ignores_removed_and_failed() -> None:
    """Only installing or installed records count as active."""
    repo = InMemoryInstallationRepository()
    removed = Installation.start("demo")
    removed.mark_removed()
    failed = Installation.start("demo")
    failed.mark_failed()
    live = Installation.start("demo")
    for i in (removed, failed, live):
        await repo.add(i)

    assert await repo.get_active_for_pack("demo") is live
    assert await repo.get_active_for_pack("other") is None
    assert await repo.list_active() == [live]


async def test_list_for_pack_returns_every_status_newest_first() -> None:
    """Every installation of the pack is listed, newest first, others excluded."""
    repo = InMemoryInstallationRepository()
    first = Installation.start("demo")
    first.mark_removed()
    second = Installation.start("demo")
    second.mark_failed()
    third = Installation.start("demo")
    other = Installation.start("other")
    for i in (second, other, first, third):
        await repo.add(i)

    assert await repo.list_for_pack("demo") == [third, second, first]
    assert await repo.list_for_pack("none") == []
