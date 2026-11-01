import re
from typing import Any, ClassVar

from pydantic_settings import SettingsConfigDict

from app.platform.config._tracking import TrackedSettings

ENV_PREFIX = "MENAGERIST_"
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
