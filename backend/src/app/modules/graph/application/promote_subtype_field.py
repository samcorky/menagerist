import copy
import uuid
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, ClassVar

import structlog

from app.modules.graph.application.field_definitions import (
    field_kind,
    forget_fields,
    with_every_option,
)
from app.modules.graph.application.permissions import GraphPermission
from app.modules.graph.application.schema_meta import (
    NAMESPACE,
    archived_keys,
    check_meta_shape,
    required_keys,
)
from app.modules.graph.application.subtype_fields import live_definitions, most_common
from app.modules.graph.domain.errors import InvalidSchemaError, NodeTypeNotFoundError
from app.modules.graph.domain.node_type import NodeType
from app.modules.graph.ports.unit_of_work import GraphUnitOfWork
from app.shared_kernel.access import Access, Content
from app.shared_kernel.cqrs import CommandHandler

if TYPE_CHECKING:
    from app.shared_kernel.actor import Actor

logger = structlog.get_logger()

_BASE_SCHEMA: dict[str, Any] = {
    "$schema": "https://json-schema.org/draft/2020-12/schema",
    "type": "object",
    "properties": {},
}


@dataclass(kw_only=True)
class PromoteSubtypeFieldCommand:
    """Move a field the subtypes of an item type define up onto the item type."""

    node_type_id: uuid.UUID
    key: str


@dataclass(frozen=True, eq=False)
class PromotedSubtypeField:
    """The parent item type, now with the field, and how many subtypes it left."""

    node_type: NodeType
    subtypes: int


class PromoteSubtypeField(
    CommandHandler[GraphUnitOfWork, PromoteSubtypeFieldCommand, PromotedSubtypeField]
):
    """Add a field to a parent type and take it off every subtype that defined it.

    One change in one transaction. Items are untouched: they store values by key, and a
    subtype still uses the field through its parent. A choice field gets the options of
    every subtype so no stored value stops being one; any other difference follows the
    definition most subtypes share. A field some subtypes keep as another kind of field
    is refused, since it could not sit beside the parent's. If any subtype required it,
    the parent now does, so it applies to them all.
    """

    access: ClassVar[Access] = Content(GraphPermission.TYPE_WRITE)

    async def _handle(
        self, command: PromoteSubtypeFieldCommand, actor: Actor
    ) -> PromotedSubtypeField:
        """Move `command.key` from the subtypes onto the type and commit."""
        scope = self.scope(actor)
        async with self._uow as repos:
            parent = await repos.node_types.get(command.node_type_id, scope=scope)
            if parent is None:
                raise NodeTypeNotFoundError(
                    f"NodeType {command.node_type_id} not found"
                )
            self._guard.assert_can_modify(actor, parent.owner_id)
            subtypes = await repos.node_types.list_subtypes(
                str(parent.slug), scope=scope
            )
            key = command.key
            parent_schema = parent.attributes_schema or copy.deepcopy(_BASE_SCHEMA)
            parent_props: dict[str, Any] = dict(parent_schema.get("properties") or {})
            if key in parent_props or key in archived_keys(parent_schema):
                raise InvalidSchemaError(f"{key!r} already exists on this item type")

            self._refuse_hidden_copies(key, subtypes)
            definitions = live_definitions(subtypes).get(key, [])
            if not definitions:
                raise InvalidSchemaError(f"No subtype of this item type has {key!r}")
            chosen = most_common(definitions)
            self._refuse_other_kinds(key, chosen, definitions)

            required = any(key in _required_in(s) for s in subtypes)
            new_parent = _with_field(
                parent_schema,
                key,
                with_every_option(chosen, [d.prop for d in definitions]),
                required=required,
            )
            check_meta_shape(new_parent)
            moved = [
                s for s in subtypes if str(s.slug) in {d.slug for d in definitions}
            ]
            inherited = new_parent["properties"]
            for subtype in moved:
                self._guard.assert_can_modify(actor, subtype.owner_id)
                own = _without_field(subtype.attributes_schema or {}, key)
                check_meta_shape(own, inherited=inherited)
                subtype.update(attributes_schema=own)
                await repos.node_types.save(subtype)
            parent.update(attributes_schema=new_parent)
            await repos.node_types.save(parent)
            await self._uow.commit()
        logger.info(
            "subtype field promoted",
            node_type_id=command.node_type_id,
            key=key,
            subtypes=len(moved),
        )
        return PromotedSubtypeField(node_type=parent, subtypes=len(moved))

    @staticmethod
    def _refuse_hidden_copies(key: str, subtypes: list[NodeType]) -> None:
        """A subtype with the key archived would clash with the parent's."""
        hidden = [
            s.label for s in subtypes if key in archived_keys(s.attributes_schema or {})
        ]
        if hidden:
            names = ", ".join(hidden)
            raise InvalidSchemaError(
                f"{names} {'has' if len(hidden) == 1 else 'have'} {key!r} hidden. "
                + "Restore or remove it first."
            )

    @staticmethod
    def _refuse_other_kinds(
        key: str, chosen: dict[str, Any], definitions: list[Any]
    ) -> None:
        """Refuse when some subtypes keep the key as another kind of field."""
        kind = field_kind(chosen)
        others = sum(1 for d in definitions if field_kind(d.prop) != kind)
        if others:
            noun = "subtype keeps" if others == 1 else "subtypes keep"
            title = chosen.get("title") or key
            raise InvalidSchemaError(
                f"{others} {noun} {title} as a different kind of field. "
                + "Change them to match first."
            )


def _required_in(subtype: NodeType) -> list[str]:
    schema = subtype.attributes_schema or {}
    root = schema.get("required")
    return [*required_keys(schema), *(root if isinstance(root, list) else [])]


def _with_field(
    schema: dict[str, Any], key: str, prop: dict[str, Any], *, required: bool
) -> dict[str, Any]:
    """`schema` with `key` added as a field, and required if it was on a subtype."""
    result = copy.deepcopy(schema)
    result["properties"] = {**(result.get("properties") or {}), key: prop}
    if required:
        meta = dict(result.get(NAMESPACE) or {})
        listed = [k for k in meta.get("required", []) if isinstance(k, str)]
        meta["required"] = [*listed, key] if key not in listed else listed
        result[NAMESPACE] = meta
    return result


def _without_field(schema: dict[str, Any], key: str) -> dict[str, Any]:
    """`schema` with `key` gone from its properties, required lists and layout."""
    result = copy.deepcopy(schema)
    result["properties"] = {
        k: v for k, v in (result.get("properties") or {}).items() if k != key
    }
    forget_fields(result, {key})
    return result
