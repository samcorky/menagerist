from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING

import pytest

from app.modules.system.adapters.persistence.update_check_store import (
    SqlAlchemyUpdateCheckStore,
)
from app.modules.system.domain.release import (
    CheckFailure,
    Release,
    ReleaseChannel,
    UpdateCheck,
)

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

pytestmark = pytest.mark.integration

NOW = datetime(2026, 10, 29, 12, 0, tzinfo=UTC)
KEY = "github:o/r:stable"


def _check(**overrides: object) -> UpdateCheck:
    values: dict[str, object] = {
        "source": "o/r",
        "channel": ReleaseChannel.STABLE,
        "latest": Release(
            version="0.2026.11.0",
            url="https://github.com/o/r/releases/tag/0.2026.11.0",
            published_at=NOW,
            prerelease=False,
        ),
        "last_success_at": NOW,
        "last_attempt_at": NOW,
    }
    return UpdateCheck(**{**values, **overrides})  # type: ignore[arg-type]


async def test_a_saved_result_round_trips(db_session: AsyncSession) -> None:
    """Every field of a result survives a write and a read."""
    store = SqlAlchemyUpdateCheckStore(db_session)

    await store.save(KEY, _check())

    assert await store.get(KEY) == _check()


async def test_an_unknown_key_reads_as_nothing(db_session: AsyncSession) -> None:
    """A source never checked has no row."""
    assert await SqlAlchemyUpdateCheckStore(db_session).get("github:x/y:stable") is None


async def test_saving_again_replaces_the_result_in_place(
    db_session: AsyncSession,
) -> None:
    """The upsert updates the one row, so overlapping checks cannot collide."""
    store = SqlAlchemyUpdateCheckStore(db_session)
    await store.save(KEY, _check())
    later = NOW + timedelta(hours=1)

    await store.save(
        KEY,
        _check(last_attempt_at=later, failure=CheckFailure.TIMEOUT),
    )

    stored = await store.get(KEY)
    assert stored is not None
    assert stored.last_attempt_at == later
    assert stored.last_success_at == NOW
    assert stored.failure is CheckFailure.TIMEOUT
    assert stored.latest is not None
    assert stored.latest.version == "0.2026.11.0"


async def test_a_source_with_no_release_is_stored_without_one(
    db_session: AsyncSession,
) -> None:
    """No eligible release is a successful answer, not a missing row."""
    store = SqlAlchemyUpdateCheckStore(db_session)

    await store.save(KEY, _check(latest=None))

    stored = await store.get(KEY)
    assert stored is not None
    assert stored.latest is None
    assert stored.last_success_at == NOW


async def test_each_key_keeps_its_own_row(db_session: AsyncSession) -> None:
    """A channel or repository change never reads another's result."""
    store = SqlAlchemyUpdateCheckStore(db_session)
    await store.save(KEY, _check())
    await store.save("github:o/r:preview", _check(channel=ReleaseChannel.PREVIEW))

    stable = await store.get(KEY)
    preview = await store.get("github:o/r:preview")

    assert stable is not None
    assert preview is not None
    assert stable.channel is ReleaseChannel.STABLE
    assert preview.channel is ReleaseChannel.PREVIEW
