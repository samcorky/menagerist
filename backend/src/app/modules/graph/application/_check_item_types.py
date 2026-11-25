from typing import TYPE_CHECKING

from app.modules.graph.application.type_catalogue import load_node_types
from app.modules.graph.domain.errors import ItemTypeNotAllowedError

if TYPE_CHECKING:
    from collections.abc import Mapping

    from app.modules.graph.domain.edge_type import EdgeType
    from app.modules.graph.domain.node import Node
    from app.modules.graph.ports.unit_of_work import GraphRepos
    from app.shared_kernel.content_filter import ContentFilter


async def load_type_parents(
    repos: GraphRepos, edge_type: EdgeType, scope: ContentFilter
) -> dict[str, str]:
    """Each subtype's slug mapped to its parent's, read only when a limit needs it."""
    if not (edge_type.source_types or edge_type.target_types):
        return {}
    return {
        str(t.slug): t.parent for t in await load_node_types(repos, scope) if t.parent
    }


def _check_end(
    edge_type: EdgeType,
    end: str,
    item: Node,
    allowed: tuple[str, ...],
    parents: Mapping[str, str],
) -> None:
    if not allowed:
        return
    # A limit on a parent covers its subtypes; one on a subtype covers only it.
    if item.type is not None and (
        item.type in allowed or parents.get(item.type) in allowed
    ):
        return
    actual = f"a {item.type} item" if item.type else "an item with no type"
    raise ItemTypeNotAllowedError(
        f"'{edge_type.label}' joins only {', '.join(allowed)} at its {end}; "
        + f"{item.name} is {actual}"
    )


def check_item_types_fit(
    edge_type: EdgeType, source: Node, target: Node, parents: Mapping[str, str]
) -> None:
    """Raise `ItemTypeNotAllowedError` unless both items suit the connection type.

    `parents` maps a subtype's slug to its parent's (`load_type_parents`). The message
    names the end that fails, the item's own type and the allowed ones.
    """
    _check_end(edge_type, "source", source, edge_type.source_types, parents)
    _check_end(edge_type, "target", target, edge_type.target_types, parents)
