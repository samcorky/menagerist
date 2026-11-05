import re
from pathlib import Path
from typing import Any, ClassVar

from pydantic_settings import (
    BaseSettings,
    PydanticBaseSettingsSource,
    SecretsSettingsSource,
    SettingsConfigDict,
)

from app.platform.config._tracking import TrackedSettings

ENV_PREFIX = "MENAGERIST_"
# Where Docker and Compose mount secrets; a file named after a variable supplies it.
SECRETS_DIR = Path("/run/secrets")
_GROUP = re.compile(r"[a-z][a-z0-9_]*")


class MenageristBaseSettings(TrackedSettings):
    """Base for deployment settings; the one place the `MENAGERIST_` prefix lives.

    A subclass declared with `group="backup"` reads `MENAGERIST_BACKUP_<FIELD>` and
    names its tunable settings `backup.<field>`. Without a group it reads
    `MENAGERIST_<FIELD>`.
    """

    model_config = SettingsConfigDict(
        env_prefix=ENV_PREFIX,
        frozen=True,
        validate_default=True,
    )

    group: ClassVar[str | None] = None

    @classmethod
    def settings_customise_sources(
        cls,
        settings_cls: type[BaseSettings],
        init_settings: PydanticBaseSettingsSource,
        env_settings: PydanticBaseSettingsSource,
        dotenv_settings: PydanticBaseSettingsSource,
        file_secret_settings: PydanticBaseSettingsSource,
    ) -> tuple[PydanticBaseSettingsSource, ...]:
        """Add `/run/secrets/<VARIABLE>` files below the environment and `.env`.

        A directory given at construction (`_secrets_dir`) is kept as it is. The
        default one is looked up on each load, and skipped when absent so a host
        without Docker secrets sees no warning.
        """
        if (
            isinstance(file_secret_settings, SecretsSettingsSource)
            and file_secret_settings.secrets_dir is None
            and SECRETS_DIR.is_dir()
        ):
            file_secret_settings = SecretsSettingsSource(settings_cls, SECRETS_DIR)
        return init_settings, env_settings, dotenv_settings, file_secret_settings

    def __init_subclass__(
        cls,
        group: str | None = None,
        **kwargs: Any,  # noqa: ANN401 - Pydantic class options
    ) -> None:
        super().__init_subclass__(**kwargs)

    @classmethod
    def __pydantic_init_subclass__(
        cls,
        group: str | None = None,
        **kwargs: Any,  # noqa: ANN401 - Pydantic class options
    ) -> None:
        super().__pydantic_init_subclass__(**kwargs)
        if group is None:
            return
        if not _GROUP.fullmatch(group):
            msg = f"{cls.__name__}: group must be lower snake case, not {group!r}"
            raise ValueError(msg)
        cls.group = group
        cls.model_config["env_prefix"] = f"{ENV_PREFIX}{group.upper()}_"
