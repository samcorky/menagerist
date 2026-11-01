"""Annotations that mark a settings field as editable, public or UI-hinted."""

from dataclasses import dataclass
from enum import StrEnum
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from pydantic import GetJsonSchemaHandler
    from pydantic.json_schema import JsonSchemaValue
    from pydantic_core import CoreSchema


class Scope(StrEnum):
    """Who owns the stored value of a tunable setting."""

    INSTANCE = "instance"
    USER = "user"


@dataclass(frozen=True, kw_only=True)
class Tunable:
    """Server-side marker: an admin or user may change this field at runtime.

    Never written into the JSON Schema.
    """

    scope: Scope = Scope.INSTANCE
    restart_required: bool = False


@dataclass(frozen=True)
class Public:
    """Server-side marker: the value is exposed by public configuration."""


@dataclass(frozen=True, kw_only=True)
class UIMeta:
    """Hints merged into a property's `x-menagerist` JSON Schema namespace.

    Only names the frontend's `PropertyMeta` understands are accepted, so a
    misspelt hint fails type checking.
    """

    kind: str | None = None
    unit: str | None = None
    display: str | None = None

    def __get_pydantic_json_schema__(
        self, core_schema: CoreSchema, handler: GetJsonSchemaHandler
    ) -> JsonSchemaValue:
        schema = handler(core_schema)
        hints = {
            name: value
            for name, value in (
                ("kind", self.kind),
                ("unit", self.unit),
                ("display", self.display),
            )
            if value is not None
        }
        if hints:
            schema.setdefault("x-menagerist", {}).update(hints)
        return schema
