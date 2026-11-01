"""Compose SQLAlchemy and in-memory adapters using the shared units of work."""

from typing import TYPE_CHECKING

from app.modules.settings.adapters.persistence.in_memory_setting_value_repository import (  # noqa: E501
    InMemorySettingValueRepository,
)
from app.modules.settings.adapters.persistence.setting_value_repository import (
    SqlAlchemySettingValueRepository,
)
from app.modules.settings.ports.unit_of_work import SettingsRepos
from app.platform.unit_of_work import SqlAlchemySessionUnitOfWork
from app.shared_kernel.unit_of_work import InMemoryUnitOfWork

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

    from app.modules.settings.ports.unit_of_work import SettingsUnitOfWork


def build_settings_repos(session: AsyncSession) -> SettingsRepos:
    """Bind the durable settings ports to the caller's existing transaction."""
    return SettingsRepos(values=SqlAlchemySettingValueRepository(session))


def create_settings_uow(
    session_factory: async_sessionmaker[AsyncSession],
) -> SettingsUnitOfWork:
    """Use the common SQLAlchemy unit of work."""
    return SqlAlchemySessionUnitOfWork(session_factory, build_settings_repos)


def create_in_memory_settings_uow(
    repo: InMemorySettingValueRepository | None = None,
) -> InMemoryUnitOfWork[SettingsRepos]:
    """Use the standard in-memory transaction signal implementation."""
    return InMemoryUnitOfWork(
        SettingsRepos(values=repo or InMemorySettingValueRepository())
    )
