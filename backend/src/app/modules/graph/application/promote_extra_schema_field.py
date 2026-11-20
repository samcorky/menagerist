import json
import uuid
from collections import Counter
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, ClassVar

import structlog

from app.modules.graph.application.field_kinds import kind_of
from app.modules.graph.application.permissions import GraphPermission
from app.modules.graph.application.schema_meta import NAMESPACE, archived_keys
from app.modules.graph.application.update_node_type import (
    UpdateNodeType,
    UpdateNodeTypeCommand,
)
from app.modules.graph.domain.errors import (
    InvalidSchemaError,
    NodeNotFoundError,
    NodeTypeNotFoundError,
)
from app.modules.graph.domain.node import Node
from app.modules.graph.domain.node_type import NodeType
from app.modules.graph.ports.unit_of_work import GraphUnitOfWork
from app.shared_kernel.access import Access, Content
from app.shared_kernel.cqrs import CommandHandler
from app.shared_kernel.unit_of_work import JoinedUnitOfWork

if TYPE_CHECKING:
    from collections.abc import Callable

    from app.modules.graph.ports.unit_of_work import GraphRepos
    from app.shared_kernel.actor import Actor

logger = structlog.get_logger()

_BASE_SCHEMA: dict[str, Any] = {
    "$schema": "https://json-schema.org/draft/2020-12/schema",
    "type": "object",
    "properties": {},
}
# Items read per query while gathering the ones that carry the field.
_PAGE = 500


@dataclass(kw_only=True)
class PromoteExtraSchemaFieldCommand:
    """Move a field from its items' own overlays onto their item type.

    With `node_id`, that item must carry the field and its definition is the one
    the type gets; otherwise the definition most of the items share wins.
    """

    node_type_id: uuid.UUID
    key: str
    node_id: uuid.UUID | None = None


@dataclass(kw_only=True, frozen=True, eq=False)
class PromotedField:
    """The item type the field joined, how many items it left, and the named item."""

    node_type: NodeType
    items: int
    node: Node | None


class PromoteExtraSchemaField(
    CommandHandler[GraphUnitOfWork, PromoteExtraSchemaFieldCommand, PromotedField]
):
    """Move a field from every item of a type that has it onto the type itself.

    Values are untouched. Composes `UpdateNodeType` with the overlay edits through
    `JoinedUnitOfWork`, one commit: a key defined on both the type and an item's
    overlay is invalid (`merge_attribute_schemas` rejects the collision), so the
    type cannot gain the field while any of its items still define it.

    The items must agree on the field's kind. Choice options are combined, so no
    stored value stops being one of them.
    """

    access: ClassVar[Access] = Content(GraphPermission.TYPE_WRITE)

    async def _handle(
        self, command: PromoteExtraSchemaFieldCommand, actor: Actor
    ) -> PromotedField:
        """Add `command.key` to the type and remove it from its items' overlays."""
        # The items are edited here, not through UpdateNode, so its stance is checked
        # here: a token needs both permissions (R8).
        await self._guard.check(actor, Content(GraphPermission.ITEM_WRITE))
        async with self._uow as repos:
            joined = JoinedUnitOfWork(repos, owner=self._uow)
            named = await self._named(repos, command, actor)
            node_type = await repos.node_types.get(
                command.node_type_id, scope=self.scope(actor)
            )
            if node_type is None:
                raise NodeTypeNotFoundError(
                    f"NodeType {command.node_type_id} not found"
                )
            type_schema: dict[str, Any] = node_type.attributes_schema or dict(
                _BASE_SCHEMA
            )
            type_properties: dict[str, Any] = dict(type_schema.get("properties") or {})
            if command.key in type_properties or command.key in archived_keys(
                type_schema
            ):
                raise InvalidSchemaError(
                    f"{command.key!r} already exists on this item type"
                )

            nodes = await self._carriers(repos, str(node_type.slug), command.key, actor)
            if not nodes:
                raise InvalidSchemaError(
                    f"No item of this type has {command.key!r} as its own field"
                )
            definitions = [_properties(node)[command.key] for node in nodes]
            chosen = (
                _properties(named)[command.key]
                if named is not None
                else _most_common(definitions)
            )
            _check_kinds(command.key, chosen, definitions)

            updated_type = await UpdateNodeType(joined, self._guard).handle(
                UpdateNodeTypeCommand(
                    node_type_id=command.node_type_id,
                    attributes_schema={
                        **type_schema,
                        "properties": {
                            **type_properties,
                            command.key: _with_every_option(chosen, definitions),
                        },
                    },
                ),
                actor,
            )
            for node in nodes:
                self._guard.assert_can_modify(actor, node.owner_id)
                node.update(extra_schema=_without(node.extra_schema, command.key))
                await repos.nodes.save(node)

            await self._uow.commit()
        logger.info(
            "extra schema field promoted",
            node_type_id=command.node_type_id,
            key=command.key,
            items=len(nodes),
        )
        moved = {node.id: node for node in nodes}
        return PromotedField(
            node_type=updated_type,
            items=len(nodes),
            node=None if named is None else moved.get(named.id, named),
        )

    async def _named(
        self, repos: GraphRepos, command: PromoteExtraSchemaFieldCommand, actor: Actor
    ) -> Node | None:
        """The item the promotion starts from, checked to carry the field."""
        if command.node_id is None:
            return None
        node = await repos.nodes.get(command.node_id, scope=self.scope(actor))
        if node is None:
            raise NodeNotFoundError(f"Node {command.node_id} not found")
        self._guard.assert_can_modify(actor, node.owner_id)
        if command.key not in _properties(node):
            raise InvalidSchemaError(
                f"{command.key!r} is not defined on this item's extra fields"
            )
        return node

    async def _carriers(
        self, repos: GraphRepos, type_slug: str, key: str, actor: Actor
    ) -> list[Node]:
        """Every item of the type whose overlay defines `key`, page by page."""
        found: list[Node] = []
        after: uuid.UUID | None = None
        while True:
            page = await repos.nodes.list_with_item_field(
                type_slug, key, scope=self.scope(actor), after=after, limit=_PAGE
            )
            found.extend(page)
            if len(page) < _PAGE:
                return found
            after = page[-1].id


def _properties(node: Node) -> dict[str, Any]:
    return (node.extra_schema or {}).get("properties") or {}


def _kind(prop: dict[str, Any]) -> str | None:
    """The field's kind: the recorded one, else what its JSON Schema shape says."""
    meta = prop.get(NAMESPACE)
    explicit = meta.get("kind") if isinstance(meta, dict) else None
    if isinstance(explicit, str):
        return explicit
    declared = prop.get("type")
    return kind_of(prop) or (declared if isinstance(declared, str) else None)


def _most_common(definitions: list[dict[str, Any]]) -> dict[str, Any]:
    """The definition most items share; the first seen wins a tie."""
    counts = Counter(json.dumps(d, sort_keys=True) for d in definitions)
    winner = counts.most_common(1)[0][0]
    return next(d for d in definitions if json.dumps(d, sort_keys=True) == winner)


def _check_kinds(
    key: str, chosen: dict[str, Any], definitions: list[dict[str, Any]]
) -> None:
    """Refuse when some items keep the key as another kind of field."""
    kind = _kind(chosen)
    others = sum(1 for d in definitions if _kind(d) != kind)
    if others:
        noun = "item keeps" if others == 1 else "items keep"
        title = chosen.get("title") or key
        message = f"{others} {noun} {title} as a different kind of field."
        raise InvalidSchemaError(f"{message} Change them to match first.")


def _with_every_option(
    chosen: dict[str, Any], definitions: list[dict[str, Any]]
) -> dict[str, Any]:
    """`chosen` with its choices widened to every option the items list."""
    if isinstance(chosen.get("enum"), list):
        return {**chosen, "enum": _union(chosen["enum"], definitions, _direct)}
    items = chosen.get("items")
    if isinstance(items, dict) and isinstance(items.get("enum"), list):
        widened = {**items, "enum": _union(items["enum"], definitions, _nested)}
        return {**chosen, "items": widened}
    return chosen


def _direct(prop: dict[str, Any]) -> object:
    return prop.get("enum")


def _nested(prop: dict[str, Any]) -> object:
    items = prop.get("items")
    return items.get("enum") if isinstance(items, dict) else None


def _union(
    first: list[Any],
    definitions: list[dict[str, Any]],
    options_of: Callable[[dict[str, Any]], object],
) -> list[Any]:
    combined = list(first)
    for definition in definitions:
        options = options_of(definition)
        if isinstance(options, list):
            combined.extend(o for o in options if o not in combined)
    return combined


def _without(extra_schema: dict[str, Any] | None, key: str) -> dict[str, Any]:
    """The overlay with `key` gone from its properties and its required list."""
    schema = dict(extra_schema or {})
    schema["properties"] = {
        k: v for k, v in (schema.get("properties") or {}).items() if k != key
    }
    meta = schema.get(NAMESPACE)
    if isinstance(meta, dict) and isinstance(meta.get("required"), list):
        schema[NAMESPACE] = {
            **meta,
            "required": [k for k in meta["required"] if k != key],
        }
    return schema
