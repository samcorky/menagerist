from functools import lru_cache
from typing import Annotated

from pydantic import Field

from app.platform.config._base import MenageristBaseSettings
from app.platform.config._markers import Tunable
from app.platform.config._types import Cron  # noqa: TC001 - pydantic resolves this at runtime


class TransferSettings(MenageristBaseSettings, group="transfer", label="Imports"):
    """How long uploaded import files are kept."""

    import_ttl_hours: int = Field(
        default=24,
        ge=1,
        description=(
            "Hours to keep an uploaded CSV file and its import's result. A file "
            + "is removed as soon as its import finishes; one never imported is "
            + "removed after this long."
        ),
    )
    prune_imports_schedule: Annotated[
        Cron,
        Field(
            title="Uploaded import files clean-up schedule",
            description=(
                "Cron expression for removing expired uploaded import files, in the "
                + "instance timezone. Empty disables the job."
            ),
        ),
        Tunable(),
    ] = "15 * * * *"


@lru_cache(maxsize=1)
def get_transfer_settings() -> TransferSettings:
    """Return the cached transfer settings."""
    return TransferSettings()
