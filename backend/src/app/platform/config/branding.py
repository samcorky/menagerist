from functools import lru_cache
from typing import Annotated

from pydantic import Field, StringConstraints

from app.platform.config._base import MenageristBaseSettings
from app.platform.config._markers import Tunable

# Installed apps keep the name and icon they were installed with until the browser
# next checks the manifest, which can take a day or more, or a reinstall.
_REFRESH_NOTE = (
    " Installed apps may keep the old value until the browser next checks the "
    + "app, which can take a day or more."
)


class BrandingSettings(MenageristBaseSettings, group="branding"):
    """How the instance names and describes itself when installed as an app."""

    name: Annotated[
        str,
        StringConstraints(strip_whitespace=True, min_length=1, max_length=45),
        Field(
            title="App name",
            description="The name an installed app shows, such as in an app list."
            + _REFRESH_NOTE,
        ),
        Tunable(),
    ] = "Menagerist"
    short_name: Annotated[
        str,
        StringConstraints(strip_whitespace=True, min_length=1, max_length=12),
        Field(
            title="Short app name",
            description=(
                "The name under an installed app's icon, where there is little room: "
                + "at most 12 characters."
            )
            + _REFRESH_NOTE,
        ),
        Tunable(),
    ] = "Menagerist"
    description: Annotated[
        str,
        StringConstraints(strip_whitespace=True, max_length=300),
        Field(
            title="App description",
            description=(
                "What the instance is for, shown where a browser offers to install it. "
                + "Empty uses Menagerist's own description."
            ),
        ),
        Tunable(),
    ] = ""


@lru_cache(maxsize=1)
def get_branding_settings() -> BrandingSettings:
    """Return the cached branding settings."""
    return BrandingSettings()
