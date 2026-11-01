"""The presets module's view of graph usage: which item types link to a saved list."""

from typing import TYPE_CHECKING, Annotated, Any

from fastapi import Depends

from app.modules.graph.adapters.api.dependencies import get_graph_repos

if TYPE_CHECKING:
    import uuid

    from app.modules.graph.ports.unit_of_work import GraphRepos

_PAGE = 100


def _references(schema: dict[str, Any] | None, target: str) -> bool:
    """Whether any top-level field of `schema` links to the list `target`."""
    properties = (schema or {}).get("properties")
    if not isinstance(properties, dict):
        return False
    return any(
        isinstance(prop, dict)
        and isinstance(prop.get("x-menagerist"), dict)
        and prop["x-menagerist"].get("list") == target
        for prop in properties.values()
    )


class GraphPresetUsage:
    """Lists the node and edge types that link to a saved choice list."""

    def __init__(self, repos: GraphRepos) -> None:
        self._repos = repos

    async def types_using(self, preset_id: uuid.UUID) -> list[str]:
        """Return the labels of the node and edge types that link to `preset_id`."""
        target = str(preset_id)
        labels: list[str] = []
        after: uuid.UUID | None = None
        while True:
            page = await self._repos.node_types.list(after=after, limit=_PAGE)
            labels += [
                t.label for t in page if _references(t.attributes_schema, target)
            ]
            if len(page) < _PAGE:
                break
            after = page[-1].id
        after = None
        while True:
            edges = await self._repos.edge_types.list(after=after, limit=_PAGE)
            labels += [
                t.label for t in edges if _references(t.attributes_schema, target)
            ]
            if len(edges) < _PAGE:
                return labels
            after = edges[-1].id


async def get_preset_usage(
    repos: Annotated[GraphRepos, Depends(get_graph_repos)],
) -> GraphPresetUsage:
    """Return the usage checker backed by the graph module."""
    return GraphPresetUsage(repos)
