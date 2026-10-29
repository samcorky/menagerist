"""Postgres storage for the latest release-check result."""

from typing import TYPE_CHECKING

from sqlalchemy.dialects.postgresql import insert

from app.modules.system.adapters.persistence.models import UpdateCheckModel
from app.modules.system.domain.release import (
    CheckFailure,
    Release,
    ReleaseChannel,
    UpdateCheck,
)

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession


def _to_domain(model: UpdateCheckModel) -> UpdateCheck:
    latest = (
        None
        if model.latest_version is None or model.latest_url is None
        else Release(
            version=model.latest_version,
            url=model.latest_url,
            published_at=model.latest_published_at,
            prerelease=model.latest_prerelease,
        )
    )
    return UpdateCheck(
        source=model.source,
        channel=ReleaseChannel(model.channel),
        latest=latest,
        last_success_at=model.last_success_at,
        last_attempt_at=model.last_attempt_at,
        failure=None if model.failure is None else CheckFailure(model.failure),
    )


class SqlAlchemyUpdateCheckStore:
    """Keeps one row per source and channel."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get(self, key: str) -> UpdateCheck | None:
        """Return the stored result for `key`, if there is one."""
        model = await self._session.get(UpdateCheckModel, key, populate_existing=True)
        return None if model is None else _to_domain(model)

    async def save(self, key: str, check: UpdateCheck) -> None:
        """Upsert in one statement, so two overlapping checks cannot collide."""
        latest = check.latest
        values = {
            "source": check.source,
            "channel": check.channel.value,
            "latest_version": None if latest is None else latest.version,
            "latest_url": None if latest is None else latest.url,
            "latest_published_at": None if latest is None else latest.published_at,
            "latest_prerelease": False if latest is None else latest.prerelease,
            "last_success_at": check.last_success_at,
            "last_attempt_at": check.last_attempt_at,
            "failure": None if check.failure is None else check.failure.value,
        }
        statement = insert(UpdateCheckModel).values(key=key, **values)
        await self._session.execute(
            statement.on_conflict_do_update(index_elements=["key"], set_=values)
        )
