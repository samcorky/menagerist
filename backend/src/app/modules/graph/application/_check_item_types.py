from typing import TYPE_CHECKING

from app.modules.graph.domain.errors import ItemTypeNotAllowedError

if TYPE_CHECKING:
    from app.modules.graph.domain.edge_type import EdgeType
    from app.modules.graph.domain.node import Node


def _check_end(
    edge_type: EdgeType, end: str, item: Node, allowed: tuple[str, ...]
) -> None:
    if not allowed or (item.type is not None and item.type in allowed):
        return
    actual = f"a {item.type} item" if item.type else "an item with no type"
    raise ItemTypeNotAllowedError(
        f"'{edge_type.label}' joins only {', '.join(allowed)} at its {end}; "
        + f"{item.name} is {actual}"
    )


def check_item_types_fit(edge_type: EdgeType, source: Node, target: Node) -> None:
    """Raise `ItemTypeNotAllowedError` unless both items suit the connection type.

    The message names the end that fails, the item's own type and the allowed ones.
    """
    _check_end(edge_type, "source", source, edge_type.source_types)
    _check_end(edge_type, "target", target, edge_type.target_types)
