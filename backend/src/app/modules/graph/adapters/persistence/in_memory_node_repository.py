from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    import builtins
    import uuid
    from collections.abc import Iterator, Mapping, Sequence

    from app.modules.graph.domain.node import Node


def _scalar_values(value: Any) -> Iterator[str]:  # noqa: ANN401
    """Yield every string and number inside `value`; never keys, booleans or nulls."""
    if isinstance(value, dict):
        for inner in value.values():
            yield from _scalar_values(inner)
    elif isinstance(value, list):
        for inner in value:
            yield from _scalar_values(inner)
    elif isinstance(value, str):
        yield value
    elif isinstance(value, (int, float)) and not isinstance(value, bool):
        yield str(value)


def _matches(
    node: Node,
    needle: str,
    exclusions: Mapping[str, Sequence[str]] | None,
) -> bool:
    """Whether `needle` (already casefolded) is found in the node's searchable text."""
    if needle in node.name.casefold() or needle in (node.description or "").casefold():
        return True
    skipped = (exclusions or {}).get(node.type, ()) if node.type else ()
    attributes = {k: v for k, v in node.attributes.items() if k not in skipped}
    return any(needle in text.casefold() for text in _scalar_values(attributes))


class InMemoryNodeRepository:
    """Dict-backed `NodeRepository` for tests and the in-memory adapter."""

    def __init__(self) -> None:
        self._nodes: dict[uuid.UUID, Node] = {}

    async def add(self, node: Node) -> None:
        """Add a new node."""
        self._nodes[node.id] = node

    async def save(self, node: Node) -> None:
        """Persist changes to an existing node."""
        self._nodes[node.id] = node

    async def get(self, node_id: uuid.UUID) -> Node | None:
        """Return the node with `node_id`, or `None` if missing or deleted."""
        node = self._nodes.get(node_id)
        if node is None or node.is_deleted:
            return None
        return node

    async def list(
        self,
        *,
        after: uuid.UUID | None,
        limit: int,
        type: str | None = None,
        q: str | None = None,
        favourite: bool | None = None,
        attribute_search_exclusions: Mapping[str, Sequence[str]] | None = None,
    ) -> list[Node]:
        """List non-deleted node ordered by id, starting after `after` if given."""
        ordered = sorted(
            (node for node in self._nodes.values() if not node.is_deleted),
            key=lambda node: node.id,
        )
        if type is not None:
            ordered = [node for node in ordered if node.type == type]
        if after is not None:
            ordered = [node for node in ordered if node.id > after]
        if q is not None:
            needle = q.casefold()
            ordered = [
                node
                for node in ordered
                if _matches(node, needle, attribute_search_exclusions)
            ]
        if favourite is not None:
            ordered = [node for node in ordered if node.favourite == favourite]
        return ordered[:limit]

    async def count(
        self,
        *,
        type: str | None = None,
        q: str | None = None,
        favourite: bool | None = None,
        attribute_search_exclusions: Mapping[str, Sequence[str]] | None = None,
    ) -> int:
        """Return the total number of non-deleted nodes matching the given filters."""
        nodes = [n for n in self._nodes.values() if not n.is_deleted]
        if type is not None:
            nodes = [n for n in nodes if n.type == type]
        if q is not None:
            needle = q.casefold()
            nodes = [
                n for n in nodes if _matches(n, needle, attribute_search_exclusions)
            ]
        if favourite is not None:
            nodes = [n for n in nodes if n.favourite == favourite]
        return len(nodes)

    async def clear_type(self, type_slug: str) -> None:
        """Set `type` to None on all non-deleted nodes if type matches `type_slug`."""
        for node in self._nodes.values():
            if not node.is_deleted and node.type == type_slug:
                node.type = None

    def _with_attribute(
        self,
        type_slug: str,
        key: str,
        *,
        sub_key: str | None = None,
        value: str | None = None,
    ) -> builtins.list[Node]:
        def matches(node: Node) -> bool:
            if node.is_deleted or node.type != type_slug or key not in node.attributes:
                return False
            if sub_key is None:
                return value is None or node.attributes[key] == value
            rows = node.attributes[key]
            return isinstance(rows, list) and any(
                isinstance(row, dict)
                and sub_key in row
                and (value is None or row[sub_key] == value)
                for row in rows
            )

        return sorted(
            (node for node in self._nodes.values() if matches(node)),
            key=lambda node: node.id,
        )

    async def count_with_attribute(
        self,
        type_slug: str,
        key: str,
        *,
        sub_key: str | None = None,
        value: str | None = None,
    ) -> int:
        """Count non-deleted nodes of `type_slug` whose attributes contain `key`."""
        return len(self._with_attribute(type_slug, key, sub_key=sub_key, value=value))

    async def list_with_attribute(
        self,
        type_slug: str,
        key: str,
        *,
        sub_key: str | None = None,
        after: uuid.UUID | None,
        limit: int,
    ) -> builtins.list[Node]:
        """List non-deleted nodes of `type_slug` holding `key`, ordered by id."""
        nodes = self._with_attribute(type_slug, key, sub_key=sub_key)
        if after is not None:
            nodes = [node for node in nodes if node.id > after]
        return nodes[:limit]
