"""The presets module's view of graph usage: which item types link to a saved list."""

from typing import TYPE_CHECKING, Annotated, Any

from fastapi import Depends

from app.entrypoints.api.shared.access_guard import get_access_guard
from app.entrypoints.api.shared.dependencies import get_current_actor
from app.modules.graph.adapters.api.dependencies import get_graph_repos

if TYPE_CHECKING:
    import uuid

    from app.modules.graph.ports.unit_of_work import GraphRepos
    from app.shared_kernel.actor import Actor
    from app.shared_kernel.content_filter import ContentFilter

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
    """Lists the node and edge types that link to a saved choice list.

    Presets belong to one person, so only types inside `scope` can use one. The
    retention purge passes an unrestricted scope and only tests for emptiness.
    """

    def __init__(self, repos: GraphRepos, *, scope: ContentFilter) -> None:
        self._repos = repos
        self._scope = scope

    async def types_using(self, preset_id: uuid.UUID) -> list[str]:
        """Return the labels of the types in scope that link to `preset_id`."""
        target = str(preset_id)
        return [*await self._node_types(target), *await self._edge_types(target)]

    async def _node_types(self, target: str) -> list[str]:
        found: list[str] = []
        after: uuid.UUID | None = None
        while True:
            page = await self._repos.node_types.list(
                scope=self._scope, after=after, limit=_PAGE
            )
            found += [t.label for t in page if _references(t.attributes_schema, target)]
            if len(page) < _PAGE:
                return found
            after = page[-1].id

    async def _edge_types(self, target: str) -> list[str]:
        found: list[str] = []
        after: uuid.UUID | None = None
        while True:
            page = await self._repos.edge_types.list(
                scope=self._scope, after=after, limit=_PAGE
            )
            found += [t.label for t in page if _references(t.attributes_schema, target)]
            if len(page) < _PAGE:
                return found
            after = page[-1].id


async def get_preset_usage(
    repos: Annotated[GraphRepos, Depends(get_graph_repos)],
    actor: Annotated[Actor, Depends(get_current_actor)],
) -> GraphPresetUsage:
    """Return the usage checker backed by the graph module, for the caller."""
    return GraphPresetUsage(repos, scope=get_access_guard().scope_for(actor))
