from typing import Annotated

from pydantic import Field

from app.platform.config._base import MenageristBaseSettings
from app.platform.config._markers import Internal


class TerminalSettings(MenageristBaseSettings, group="terminal"):
    """What the terminal the process writes to can show.

    Both fields are the standard names other tools use, not `MENAGERIST_TERMINAL_*`.
    """

    term: Annotated[
        str | None,
        Field(
            validation_alias="TERM",
            description="The terminal type; `dumb` means it cannot redraw or colour.",
        ),
        Internal(),
    ] = None
    no_color: str | None = Field(
        default=None,
        validation_alias="NO_COLOR",
        description=(
            "Set to any value that does not start with 0 to turn off colour in console "
            + "logs (see https://no-color.org)."
        ),
    )

    @property
    def is_dumb(self) -> bool:
        """Whether the terminal cannot redraw (progress bars, tables)."""
        return self.term == "dumb"

    @property
    def colour(self) -> bool:
        """Whether console logs may use colour: empty or a leading 0 leaves it on."""
        return not self.no_color or self.no_color.startswith("0")


def get_terminal_settings() -> TerminalSettings:
    """Load the settings fresh: tests and shells change them between calls."""
    return TerminalSettings()
