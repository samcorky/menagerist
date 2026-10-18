from pydantic_settings import BaseSettings, SettingsConfigDict


class MenageristBaseSettings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="MENAGERIST_",
        frozen=True,
        validate_default=True,
    )
