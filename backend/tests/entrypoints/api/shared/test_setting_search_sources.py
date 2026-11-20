"""Settings and preferences in search: found by title, description or section."""

from typing import TYPE_CHECKING
from uuid import uuid7

import pytest

from app.entrypoints.api.shared.access_guard import get_access_guard
from app.entrypoints.api.shared.bridges.search_sources import (
    PreferenceSource,
    SettingSource,
)
from app.modules.search.domain.search_hit import SearchKind
from app.modules.settings.adapters.persistence.in_memory_setting_value_repository import (  # noqa: E501
    InMemorySettingValueRepository,
)
from app.modules.settings.adapters.platform.deployment_catalogue import build_catalogue
from app.modules.settings.application.list_my_settings import ListMySettings
from app.modules.settings.application.list_settings import ListSettings
from app.platform.config import (
    DateTimeSettings,
    HomeSettings,
    MenageristBaseSettings,
    ReleaseSettings,
)
from app.platform.config._discovery import discover
from app.shared_kernel.actor import Actor
from app.shared_kernel.errors import ForbiddenError

if TYPE_CHECKING:
    from app.modules.settings.adapters.platform.pydantic_settings_catalogue import (
        PydanticSettingsCatalogue,
    )

MEMBER = Actor(id=uuid7(), roles=frozenset({"member"}))
ADMIN = Actor(id=uuid7(), roles=frozenset({"admin"}))
TOKEN = Actor(id=MEMBER.id, roles=frozenset({"member"}), grants=frozenset())

GROUPS: list[type[MenageristBaseSettings]] = [
    DateTimeSettings,
    HomeSettings,
    ReleaseSettings,
]


def _catalogue() -> PydanticSettingsCatalogue:
    return build_catalogue(discover(GROUPS), {g: g() for g in GROUPS})


def _preferences() -> PreferenceSource:
    return PreferenceSource(
        ListMySettings(
            InMemorySettingValueRepository(), get_access_guard(), _catalogue()
        )
    )


async def test_a_preference_is_found_by_its_title() -> None:
    """The hit opens the preference, under its section's name."""
    hits = await _preferences().find("clock", 5, MEMBER)

    assert [(h.kind, h.ref, h.group, h.group_title) for h in hits] == [
        (SearchKind.PREFERENCE, "datetime.clock", "datetime", "Dates and times")
    ]


async def test_a_section_name_finds_its_preferences() -> None:
    """'Dates' finds every date and time preference, through the section title."""
    hits = await _preferences().find("dates", 10, MEMBER)

    assert {h.ref for h in hits} == {
        "datetime.time_zone",
        "datetime.date_order",
        "datetime.clock",
        "datetime.first_day",
    }


async def test_hidden_preferences_are_never_found() -> None:
    """Home's collections are changed elsewhere, so search leaves them out."""
    assert await _preferences().find("home", 10, MEMBER) == []


async def test_an_api_token_finds_no_preferences() -> None:
    """Own-account data is refused to tokens; the search skips the kind."""
    with pytest.raises(ForbiddenError):
        await _preferences().find("clock", 5, TOKEN)


async def test_a_setting_is_found_by_its_section_title() -> None:
    """Admin settings match on the section people see ('Updates'), not its key."""
    source = SettingSource(
        ListSettings(InMemorySettingValueRepository(), get_access_guard(), _catalogue())
    )

    hits = await source.find("updates", 5, ADMIN)

    assert hits
    assert {(h.kind, h.group_title) for h in hits} == {(SearchKind.SETTING, "Updates")}
