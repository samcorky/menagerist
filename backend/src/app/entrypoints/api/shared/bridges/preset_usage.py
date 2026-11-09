"""The presets module's view of graph usage: which item types link to a saved list."""

from typing import TYPE_CHECKING, Annotated, Any

from fastapi import Depends

from app.entrypoints.api.shared.dependencies import get_current_actor
from app.modules.graph.adapters.api.dependencies import get_graph_repos
from app.shared_kernel.content_filter import ContentFilter

if TYPE_CHECKING:
    import uuid

    from app.modules.graph.ports.unit_of_work import GraphRepos
    from app.shared_kernel.actor import Actor

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


# Choice lists are shared, so a list is in use if anyone's type links to it.
_EVERYONE = ContentFilter.everyone()


class GraphPresetUsage:
    """Lists the node and edge types that link to a saved choice list.

    Choice lists are shared, so a list is in use if anyone's type links to it. The
    labels of the viewer's own types are returned; other people's types are only
    counted, so a private type's name never reaches someone else. With no viewer
    (the retention purge) the answer is only ever tested for emptiness.
    """

    def __init__(self, repos: GraphRepos, *, viewer: uuid.UUID | None = None) -> None:
        self._repos = repos
        self._viewer = viewer

    async def types_using(self, preset_id: uuid.UUID) -> list[str]:
        """Return the viewer's type labels that link to `preset_id`, then a count."""
        target = str(preset_id)
        labels: list[str] = []
        others = 0
        for owner, label in [
            *await self._node_types(target),
            *await self._edge_types(target),
        ]:
            if self._viewer is None or owner == self._viewer:
                labels.append(label)
            else:
                others += 1
        if others:
            labels.append(
                "1 type belonging to another person"
                if others == 1
                else f"{others} types belonging to other people"
            )
        return labels

    async def _node_types(self, target: str) -> list[tuple[uuid.UUID | None, str]]:
        found: list[tuple[uuid.UUID | None, str]] = []
        after: uuid.UUID | None = None
        while True:
            page = await self._repos.node_types.list(
                scope=_EVERYONE, after=after, limit=_PAGE
            )
            found += [
                (t.owner_id, t.label)
                for t in page
                if _references(t.attributes_schema, target)
            ]
            if len(page) < _PAGE:
                return found
            after = page[-1].id

    async def _edge_types(self, target: str) -> list[tuple[uuid.UUID | None, str]]:
        found: list[tuple[uuid.UUID | None, str]] = []
        after: uuid.UUID | None = None
        while True:
            page = await self._repos.edge_types.list(
                scope=_EVERYONE, after=after, limit=_PAGE
            )
            found += [
                (t.owner_id, t.label)
                for t in page
                if _references(t.attributes_schema, target)
            ]
            if len(page) < _PAGE:
                return found
            after = page[-1].id


async def get_preset_usage(
    repos: Annotated[GraphRepos, Depends(get_graph_repos)],
    actor: Annotated[Actor, Depends(get_current_actor)],
) -> GraphPresetUsage:
    """Return the usage checker backed by the graph module, for the caller."""
    return GraphPresetUsage(repos, viewer=actor.id)
