"""The process-wide settings catalogue and reader, shared by every entrypoint."""

from functools import lru_cache
from typing import TYPE_CHECKING

from app.modules.settings.adapters.persistence.unit_of_work import create_settings_uow
from app.modules.settings.adapters.platform.deployment_catalogue import (
    deployment_catalogue,
)
from app.modules.settings.application.settings_reader import CachedSettingsReader
from app.platform.database import get_session_factory

if TYPE_CHECKING:
    from app.modules.settings.ports.settings_catalogue import SettingsCatalogue
    from app.modules.settings.ports.unit_of_work import SettingsUnitOfWork


@lru_cache(maxsize=1)
def get_settings_catalogue() -> SettingsCatalogue:
    """The tunable settings and the deployment's pins, built once per process."""
    return deployment_catalogue()


def settings_uow() -> SettingsUnitOfWork:
    """A fresh unit of work over the database; tests swap this for an in-memory one."""
    return create_settings_uow(get_session_factory())


@lru_cache(maxsize=1)
def get_settings_reader() -> CachedSettingsReader:
    """The reader the API, CLI and worker resolve effective settings through."""
    return CachedSettingsReader(get_settings_catalogue(), lambda: settings_uow())
