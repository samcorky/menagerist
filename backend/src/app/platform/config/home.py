from functools import lru_cache
from typing import Annotated, Final

from pydantic import AfterValidator, Field

from app.platform.config._base import MenageristBaseSettings
from app.platform.config._markers import Scope, Tunable

# The frontend disables "Show on Home", with the reason, at the same limit.
MAX_HOME_COLLECTIONS: Final = 50
_UUID = r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$"


def _no_repeats(ids: list[str]) -> list[str]:
    """A collection is shown on Home once."""
    if len({i.lower() for i in ids}) != len(ids):
        msg = "a collection is listed more than once"
        raise ValueError(msg)
    return ids


class HomeSettings(MenageristBaseSettings, group="home"):
    """What each person's Home shows."""

    collections: Annotated[
        list[Annotated[str, Field(pattern=_UUID)]],
        Field(
            default_factory=list,
            max_length=MAX_HOME_COLLECTIONS,
            title="Collections on Home",
            description=(
                "The collections shown on Home, by id, in the order they were added. "
                + "Changed with Show on Home on a collection's page."
            ),
        ),
        AfterValidator(_no_repeats),
        # Changed from a collection's page, and not a deployment's to choose.
        Tunable(scope=Scope.USER, hidden=True, env_default=False),
    ]


@lru_cache(maxsize=1)
def get_home_settings() -> HomeSettings:
    """Return the cached Home settings."""
    return HomeSettings()
