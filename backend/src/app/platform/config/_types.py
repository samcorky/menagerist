"""Validated setting value types; each is kept as the string the consumer needs."""

from datetime import UTC, datetime
from typing import Annotated, Literal

from cronsim import CronSim, CronSimError
from pydantic import (
    AfterValidator,
    AnyHttpUrl,
    BeforeValidator,
    IPvAnyAddress,
    IPvAnyNetwork,
    ValidateAs,
)
from pydantic_settings import NoDecode

_DEFAULT_PORTS = {"http": 80, "https": 443}


def _split_csv(v: object) -> list[str] | object:
    if isinstance(v, str):
        return [item.strip() for item in v.split(",") if item.strip()]
    return v


def _star_alone[T](items: list[T]) -> list[T]:
    if "*" in items and len(items) > 1:
        raise ValueError('"*" cannot be combined with other entries')
    return items


type CSV[T] = Annotated[list[T], NoDecode, BeforeValidator(_split_csv)]
# A CSV that may instead be the single entry "*" (any).
type StarOrCSV[T] = Annotated[
    list[Literal["*"] | T],
    NoDecode,
    BeforeValidator(_split_csv),
    AfterValidator(_star_alone),
]


def _origin(value: object) -> str:
    """Return `scheme://host[:port]` as browsers send it; reject anything more."""
    url = AnyHttpUrl(str(value))
    if url.path not in (None, "", "/") or url.query or url.fragment or url.username:
        raise ValueError("an origin is scheme://host[:port] with no path or query")
    port = "" if url.port == _DEFAULT_PORTS[url.scheme] else f":{url.port}"
    return f"{url.scheme}://{url.host}{port}"


type Origin = Annotated[str, ValidateAs(AnyHttpUrl, _origin)]
type ProxyAddress = Annotated[str, ValidateAs(IPvAnyAddress | IPvAnyNetwork, str)]


def _cron(value: str) -> str:
    """Accept a five-field cron expression; empty means the job is off."""
    if value:
        try:
            CronSim(value, datetime(2000, 1, 1, tzinfo=UTC))
        except CronSimError as exc:
            msg = f"invalid cron schedule: {value}"
            raise ValueError(msg) from exc
    return value


type Cron = Annotated[str, ValidateAs(str, _cron)]
