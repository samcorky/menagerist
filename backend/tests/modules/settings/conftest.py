from collections.abc import Callable
from datetime import UTC, datetime
from typing import Annotated
from uuid import UUID, uuid7

import pytest
from pydantic import Field, TypeAdapter

from app.modules.settings.adapters.persistence.in_memory_setting_value_repository import (  # noqa: E501
    InMemorySettingValueRepository,
)
from app.modules.settings.adapters.platform.pydantic_settings_catalogue import (
    PydanticSettingsCatalogue,
)
from app.modules.settings.domain.setting import (
    Pin,
    SettingDescriptor,
    SettingScope,
    SettingValue,
    StoredSetting,
)
from app.modules.settings.ports.unit_of_work import SettingsRepos
from app.shared_kernel.unit_of_work import InMemoryUnitOfWork

type DescriptorFactory = Callable[..., SettingDescriptor]
type StoredFactory = Callable[..., StoredSetting]
type UowFactory = Callable[[], InMemoryUnitOfWork[SettingsRepos]]


@pytest.fixture
def make_descriptor() -> DescriptorFactory:
    """Build a minimal descriptor."""

    def build(
        key: str,
        default: SettingValue,
        scope: SettingScope = SettingScope.INSTANCE,
    ) -> SettingDescriptor:
        return SettingDescriptor(
            key=key,
            group=key.split(".")[0],
            title=key,
            description=None,
            scope=scope,
            restart_required=False,
            default=default,
            env_name="MENAGERIST_" + key.replace(".", "_").upper(),
        )

    return build


@pytest.fixture
def make_stored() -> StoredFactory:
    """Build a saved row."""

    def build(
        key: str,
        value: SettingValue,
        owner_id: UUID | None = None,
        scope: SettingScope = SettingScope.INSTANCE,
    ) -> StoredSetting:
        return StoredSetting(
            id=uuid7(),
            scope=scope,
            owner_id=owner_id,
            key=key,
            value=value,
            updated_at=datetime.now(UTC),
            updated_by=None,
        )

    return build


@pytest.fixture
def repo() -> InMemorySettingValueRepository:
    """An empty store."""
    return InMemorySettingValueRepository()


@pytest.fixture
def uow(repo: InMemorySettingValueRepository) -> UowFactory:
    """Open a fresh unit of work over the shared store."""
    return lambda: InMemoryUnitOfWork(SettingsRepos(values=repo))


@pytest.fixture
def pin() -> Pin:
    """A deployment value for `backup.keep_last`."""
    return Pin(env_name="MENAGERIST_BACKUP_KEEP_LAST", value=30)


@pytest.fixture
def catalogue(make_descriptor: DescriptorFactory) -> PydanticSettingsCatalogue:
    """Two instance settings and one per-user setting."""
    return PydanticSettingsCatalogue(
        [
            make_descriptor("backup.keep_last", 7),
            make_descriptor("backup.schedule", "0 3 * * *"),
            make_descriptor("display.timezone", "UTC", SettingScope.USER),
        ],
        {
            "backup.keep_last": TypeAdapter(Annotated[int, Field(ge=1)]),
            "backup.schedule": TypeAdapter(str),
            "display.timezone": TypeAdapter(str),
        },
    )


@pytest.fixture
def pinned_catalogue(
    catalogue: PydanticSettingsCatalogue, pin: Pin
) -> PydanticSettingsCatalogue:
    """The same settings with `backup.keep_last` pinned by the deployment."""
    return PydanticSettingsCatalogue(
        [
            *catalogue.descriptors(SettingScope.INSTANCE),
            *catalogue.descriptors(SettingScope.USER),
        ],
        catalogue.adapters,
        {"backup.keep_last": pin},
    )
