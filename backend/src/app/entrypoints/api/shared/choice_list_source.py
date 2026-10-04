import uuid
from typing import TYPE_CHECKING, Annotated

from fastapi import Depends

from app.modules.presets.adapters.persistence.unit_of_work import build_preset_repos
from app.platform.database import get_session_factory

if TYPE_CHECKING:
    from collections.abc import AsyncIterator

    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

    from app.modules.presets.ports.unit_of_work import PresetRepos


class PresetChoiceListSource:
    """Reads saved choice lists from the presets module for the graph module."""

    def __init__(self, repos: PresetRepos) -> None:
        self._repos = repos

    async def options(self, list_id: str) -> list[str] | None:
        """Return the options, or `None` if the list is missing or not a choice list."""
        try:
            preset_id = uuid.UUID(list_id)
        except ValueError:
            return None
        preset = await self._repos.presets.get(preset_id)
        if preset is None or preset.kind != "choice_list":
            return None
        options = preset.definition.get("options")
        if not isinstance(options, list):
            return None
        return [o for o in options if isinstance(o, str)]


async def get_choice_list_source(
    session_factory: Annotated[
        async_sessionmaker[AsyncSession], Depends(get_session_factory)
    ],
) -> AsyncIterator[PresetChoiceListSource]:
    """Yield the choice list source, backed by a read session on the presets table."""
    async with session_factory() as session:
        yield PresetChoiceListSource(build_preset_repos(session))
