import uuid

from app.modules.examples.adapters.persistence.in_memory_installation_repository import (  # noqa: E501
    InMemoryInstallationRepository,
)
from app.modules.examples.domain.installation import Installation
from app.shared_kernel.content_filter import ContentFilter

OWNER = uuid.UUID(int=0xA1)


async def test_add_get_and_save_round_trip() -> None:
    """An added installation is retrievable and saved changes are visible."""
    repo = InMemoryInstallationRepository()
    installation = Installation.start("demo", OWNER)
    await repo.add(installation)
    assert (
        await repo.get(installation.id, scope=ContentFilter.everyone()) is installation
    )
    installation.mark_installed()
    await repo.save(installation)
    stored = await repo.get(installation.id, scope=ContentFilter.everyone())
    assert stored is not None
    assert stored.status.value == "installed"


async def test_get_returns_none_for_an_unknown_id() -> None:
    """An unknown id yields `None`."""
    assert (
        await InMemoryInstallationRepository().get(
            uuid.uuid7(), scope=ContentFilter.everyone()
        )
        is None
    )


async def test_active_lookup_ignores_removed_and_failed() -> None:
    """Only installing or installed records count as active."""
    repo = InMemoryInstallationRepository()
    removed = Installation.start("demo", OWNER)
    removed.mark_removed()
    failed = Installation.start("demo", OWNER)
    failed.mark_failed()
    live = Installation.start("demo", OWNER)
    for i in (removed, failed, live):
        await repo.add(i)

    assert (
        await repo.get_active_for_pack("demo", scope=ContentFilter.everyone()) is live
    )
    assert (
        await repo.get_active_for_pack("other", scope=ContentFilter.everyone()) is None
    )
    assert await repo.list_active(scope=ContentFilter.everyone()) == [live]


async def test_list_for_pack_returns_every_status_newest_first() -> None:
    """Every installation of the pack is listed, newest first, others excluded."""
    repo = InMemoryInstallationRepository()
    first = Installation.start("demo", OWNER)
    first.mark_removed()
    second = Installation.start("demo", OWNER)
    second.mark_failed()
    third = Installation.start("demo", OWNER)
    other = Installation.start("other", OWNER)
    for i in (second, other, first, third):
        await repo.add(i)

    assert await repo.list_for_pack("demo", scope=ContentFilter.everyone()) == [
        third,
        second,
        first,
    ]
    assert await repo.list_for_pack("none", scope=ContentFilter.everyone()) == []
