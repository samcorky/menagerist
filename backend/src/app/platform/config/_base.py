from typing import Annotated

from pydantic import BeforeValidator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict


def _split_csv(v: object) -> list[str] | object:
    if isinstance(v, str):
        return [item.strip() for item in v.split(",") if item.strip()]
    return v


type CSV[T] = Annotated[list[T], NoDecode, BeforeValidator(_split_csv)]


class MenageristBaseSettings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="MENAGERIST_", frozen=True)
