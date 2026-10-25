from pydantic_settings import SettingsConfigDict

from app.platform.config._tracking import TrackedSettings


class MenageristBaseSettings(TrackedSettings):
    model_config = SettingsConfigDict(
        env_prefix="MENAGERIST_",
        frozen=True,
        validate_default=True,
    )
