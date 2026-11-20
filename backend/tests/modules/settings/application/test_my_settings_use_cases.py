"""A person's own settings: read, change and reset, never another person's."""

from dataclasses import replace
from typing import TYPE_CHECKING, Literal
from uuid import uuid7

import pytest
from pydantic import TypeAdapter

from app.entrypoints.api.shared.access_guard import get_access_guard
from app.modules.settings.adapters.persistence.in_memory_setting_value_repository import (  # noqa: E501
    InMemorySettingValueRepository,
)
from app.modules.settings.adapters.platform.pydantic_settings_catalogue import (
    PydanticSettingsCatalogue,
)
from app.modules.settings.application.get_my_settings_schema import (
    GetMySettingsSchema,
    GetMySettingsSchemaQuery,
)
from app.modules.settings.application.list_my_settings import (
    ListMySettings,
    ListMySettingsQuery,
)
from app.modules.settings.application.reset_my_setting import (
    ResetMySetting,
    ResetMySettingCommand,
)
from app.modules.settings.application.update_my_settings import (
    UpdateMySettings,
    UpdateMySettingsCommand,
)
from app.modules.settings.domain.errors import (
    InvalidSettingValueError,
    UnknownSettingError,
)
from app.modules.settings.domain.setting import SettingScope, SettingSource
from app.modules.settings.ports.unit_of_work import SettingsRepos
from app.shared_kernel.actor import Actor
from app.shared_kernel.errors import ForbiddenError
from app.shared_kernel.unit_of_work import InMemoryUnitOfWork

if TYPE_CHECKING:
    from tests.modules.settings.conftest import DescriptorFactory

ALICE = Actor(id=uuid7(), roles=frozenset({"member"}))
BOB = Actor(id=uuid7(), roles=frozenset({"member"}))
TOKEN = Actor(id=ALICE.id, roles=frozenset({"member"}), grants=frozenset())


@pytest.fixture
def mine(make_descriptor: DescriptorFactory) -> PydanticSettingsCatalogue:
    """One instance setting, one per-person setting with an env default, one hidden."""
    first_day = replace(
        make_descriptor("datetime.first_day", "sunday", SettingScope.USER),
        schema={"type": "string", "enum": ["automatic", "monday", "sunday"]},
        default_from_env=True,
    )
    home = replace(
        make_descriptor("home.collections", [], SettingScope.USER),
        schema={"type": "array", "items": {"type": "string"}},
        hidden=True,
    )
    return PydanticSettingsCatalogue(
        [make_descriptor("backup.keep_last", 7), first_day, home],
        {
            "backup.keep_last": TypeAdapter(int),
            "datetime.first_day": TypeAdapter(Literal["automatic", "monday", "sunday"]),
            "home.collections": TypeAdapter(list[str]),
        },
    )


def _uow(repo: InMemorySettingValueRepository) -> InMemoryUnitOfWork[SettingsRepos]:
    return InMemoryUnitOfWork(SettingsRepos(values=repo))


async def _list(
    catalogue: PydanticSettingsCatalogue,
    repo: InMemorySettingValueRepository,
    actor: Actor,
) -> dict[str, tuple[object, SettingSource]]:
    listing = await ListMySettings(repo, get_access_guard(), catalogue).handle(
        ListMySettingsQuery(), actor
    )
    return {item.descriptor.key: (item.value, item.source) for item in listing}


async def _update(
    catalogue: PydanticSettingsCatalogue,
    repo: InMemorySettingValueRepository,
    actor: Actor,
    values: dict[str, object],
    on_changed: list[str] | None = None,
) -> None:
    changed = on_changed if on_changed is not None else []
    await UpdateMySettings(
        _uow(repo), get_access_guard(), catalogue, lambda: changed.append("x")
    ).handle(UpdateMySettingsCommand(values=values), actor)


async def test_list_shows_every_own_setting_with_the_env_default(
    mine: PydanticSettingsCatalogue,
) -> None:
    """Hidden settings are listed; instance ones are not; the env default is marked."""
    listing = await _list(mine, InMemorySettingValueRepository(), ALICE)

    assert listing == {
        "datetime.first_day": ("sunday", SettingSource.ENV_DEFAULT),
        "home.collections": ([], SettingSource.DEFAULT),
    }


async def test_a_change_is_the_persons_own(mine: PydanticSettingsCatalogue) -> None:
    """One person's value never shows for another."""
    repo = InMemorySettingValueRepository()
    changed: list[str] = []

    await _update(mine, repo, ALICE, {"datetime.first_day": "monday"}, changed)

    assert (await _list(mine, repo, ALICE))["datetime.first_day"] == (
        "monday",
        SettingSource.USER,
    )
    assert (await _list(mine, repo, BOB))["datetime.first_day"] == (
        "sunday",
        SettingSource.ENV_DEFAULT,
    )
    assert changed == ["x"]


async def test_a_list_value_replaces_the_saved_one(
    mine: PydanticSettingsCatalogue,
) -> None:
    """A hidden list is saved whole, so the last write wins."""
    repo = InMemorySettingValueRepository()

    await _update(mine, repo, ALICE, {"home.collections": ["a", "b"]})
    await _update(mine, repo, ALICE, {"home.collections": ["b"]})

    assert (await _list(mine, repo, ALICE))["home.collections"] == (
        ["b"],
        SettingSource.USER,
    )


async def test_update_returns_what_it_saved(mine: PydanticSettingsCatalogue) -> None:
    """The response carries each changed setting resolved."""
    result = await UpdateMySettings(
        _uow(InMemorySettingValueRepository()), get_access_guard(), mine
    ).handle(UpdateMySettingsCommand(values={"datetime.first_day": "monday"}), ALICE)

    assert [(r.descriptor.key, r.value, r.source) for r in result] == [
        ("datetime.first_day", "monday", SettingSource.USER)
    ]


async def test_an_empty_update_saves_nothing(mine: PydanticSettingsCatalogue) -> None:
    """No values is not an error and changes nothing."""
    repo = InMemorySettingValueRepository()
    result = await UpdateMySettings(_uow(repo), get_access_guard(), mine).handle(
        UpdateMySettingsCommand(values={}), ALICE
    )

    assert result == []
    assert await repo.list(SettingScope.USER, ALICE.id) == {}


@pytest.mark.parametrize("key", ["backup.keep_last", "calendar.nope"])
async def test_update_refuses_an_instance_or_unknown_key(
    mine: PydanticSettingsCatalogue, key: str
) -> None:
    """A person can't reach instance settings through their own."""
    with pytest.raises(UnknownSettingError):
        await _update(mine, InMemorySettingValueRepository(), ALICE, {key: 1})


async def test_one_bad_value_saves_nothing(mine: PydanticSettingsCatalogue) -> None:
    """Every value is checked before any is saved."""
    repo = InMemorySettingValueRepository()
    with pytest.raises(InvalidSettingValueError):
        await _update(
            mine,
            repo,
            ALICE,
            {"home.collections": ["a"], "datetime.first_day": "friday"},
        )

    assert await repo.list(SettingScope.USER, ALICE.id) == {}


async def test_reset_restores_the_default_for_that_person_only(
    mine: PydanticSettingsCatalogue,
) -> None:
    """Resetting drops the person's value; another person's stays."""
    repo = InMemorySettingValueRepository()
    await _update(mine, repo, ALICE, {"datetime.first_day": "monday"})
    await _update(mine, repo, BOB, {"datetime.first_day": "monday"})
    changed: list[str] = []
    reset = ResetMySetting(
        _uow(repo), get_access_guard(), mine, lambda: changed.append("x")
    )

    result = await reset.handle(ResetMySettingCommand(key="datetime.first_day"), ALICE)
    again = await reset.handle(ResetMySettingCommand(key="datetime.first_day"), ALICE)

    assert (result.value, result.source) == ("sunday", SettingSource.ENV_DEFAULT)
    assert (again.value, again.source) == ("sunday", SettingSource.ENV_DEFAULT)
    assert changed == ["x"]
    assert (await _list(mine, repo, BOB))["datetime.first_day"][0] == "monday"


async def test_reset_refuses_an_instance_key(mine: PydanticSettingsCatalogue) -> None:
    """Instance settings are reset on the server page only."""
    with pytest.raises(UnknownSettingError):
        await ResetMySetting(
            _uow(InMemorySettingValueRepository()), get_access_guard(), mine
        ).handle(ResetMySettingCommand(key="backup.keep_last"), ALICE)


async def test_schema_lists_only_form_settings(mine: PydanticSettingsCatalogue) -> None:
    """Hidden and instance settings are left out of the Preferences form."""
    schema = await GetMySettingsSchema(mine, get_access_guard()).handle(
        GetMySettingsSchemaQuery(), ALICE
    )

    assert list(schema["properties"]) == ["datetime.first_day"]  # type: ignore[call-overload]


async def test_a_token_is_refused(mine: PydanticSettingsCatalogue) -> None:
    """Own-account routes refuse API tokens."""
    with pytest.raises(ForbiddenError):
        await _list(mine, InMemorySettingValueRepository(), TOKEN)
