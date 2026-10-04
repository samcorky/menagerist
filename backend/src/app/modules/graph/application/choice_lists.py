"""Linked choice lists: a choice field stores a reference, and its options are resolved.

A field with `x-menagerist.list` holds the id of a saved choice list instead of an
`enum`. Writes strip any `enum` from such fields and check the reference. Reads and
validation fill the `enum` back in from the list, so the validator sees a plain choice.
"""

import copy
import uuid
from typing import TYPE_CHECKING, Any, overload

import structlog

from app.modules.graph.domain.errors import InvalidSchemaError

if TYPE_CHECKING:
    from app.modules.graph.ports.choice_list_source import ChoiceListSource

logger = structlog.get_logger()

NAMESPACE = "x-menagerist"
LIST_KEY = "list"


def _linked_properties(schema: dict[str, Any]) -> dict[str, dict[str, Any]]:
    """Return the top-level properties that reference a choice list."""
    properties = schema.get("properties")
    if not isinstance(properties, dict):
        return {}
    return {
        key: prop
        for key, prop in properties.items()
        if isinstance(prop, dict)
        and isinstance(prop.get(NAMESPACE), dict)
        and LIST_KEY in prop[NAMESPACE]
    }


def strip_list_enums(schema: dict[str, Any]) -> dict[str, Any]:
    """Return a copy of `schema` without `enum` on fields linked to a choice list."""
    linked = _linked_properties(schema)
    if not linked:
        return schema
    result = copy.deepcopy(schema)
    for key in linked:
        result["properties"][key].pop("enum", None)
    return result


async def check_list_refs(
    schema: dict[str, Any], source: ChoiceListSource | None
) -> None:
    """Check that every list reference is well formed and points at a live list.

    :raises InvalidSchemaError: a reference is malformed, unknown, or cannot be checked.
    """
    for key, prop in _linked_properties(schema).items():
        list_id = prop[NAMESPACE][LIST_KEY]
        try:
            uuid.UUID(str(list_id))
        except ValueError as exc:
            raise InvalidSchemaError(
                f"'{key}' refers to an invalid choice list"
            ) from exc
        if source is None:
            raise InvalidSchemaError(
                f"'{key}' refers to a choice list, which cannot be checked"
            )
        if await source.options(str(list_id)) is None:
            raise InvalidSchemaError(
                f"'{key}' refers to a choice list that does not exist"
            )


@overload
async def resolve_choice_lists(
    schema: dict[str, Any], source: ChoiceListSource | None
) -> dict[str, Any]: ...


@overload
async def resolve_choice_lists(
    schema: None, source: ChoiceListSource | None
) -> None: ...


async def resolve_choice_lists(
    schema: dict[str, Any] | None, source: ChoiceListSource | None
) -> dict[str, Any] | None:
    """Return `schema` with `enum` filled in for each linked field.

    A reference to a missing list is logged and left unconstrained, so one bad reference
    cannot block every save of the type. Writes call `check_list_refs` to prevent that.
    """
    if schema is None or source is None:
        return schema
    linked = _linked_properties(schema)
    if not linked:
        return schema
    result = copy.deepcopy(schema)
    for key, prop in linked.items():
        options = await source.options(str(prop[NAMESPACE][LIST_KEY]))
        if options is None:
            logger.warning("choice list missing; field left unconstrained", field=key)
            result["properties"][key].pop("enum", None)
            continue
        result["properties"][key]["enum"] = list(options)
    return result
