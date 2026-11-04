from pathlib import Path  # noqa: TC003 - pydantic resolves this at runtime
from typing import Annotated

from pydantic import Field

from app.platform.config._base import MenageristBaseSettings
from app.platform.config._markers import Internal


class SharedDataSettings(MenageristBaseSettings):
    """Where the data shared by the backend and frontend is found."""

    shared_dir: Annotated[
        Path | None,
        Field(
            description=(
                "Directory holding the shared data files. The Docker image sets it, "
                + "since the installed package has no source tree to resolve from; "
                + "otherwise the repository's `shared/` is used."
            )
        ),
        Internal(),
    ] = None


def get_shared_data_settings() -> SharedDataSettings:
    """Load the settings fresh: they are read once, by a migration or a test."""
    return SharedDataSettings()
