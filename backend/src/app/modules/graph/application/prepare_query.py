"""Parse a stored query and resolve it against the current item types."""

from datetime import UTC, date, datetime
from typing import TYPE_CHECKING, Any

from app.modules.graph.application.collection_expansion import expand_collections
from app.modules.graph.application.query_resolution import (
    ConnectionResolution,
    connection_references,
    resolve_connections,
    resolve_fields,
)
from app.modules.graph.application.schema_meta import search_excluded_keys
from app.modules.graph.application.type_catalogue import (
    load_edge_types,
    load_node_types,
)
from app.modules.graph.domain.query import (
    CollectionCondition,
    Group,
    ManualTarget,
    MediaCondition,
    Query,
    QueryWarning,
    ResolvedQuery,
    parse_query,
    walk_conditions,
)

if TYPE_CHECKING:
    import uuid
    from collections.abc import Callable, Mapping

    from app.modules.graph.ports.unit_of_work import GraphRepos
    from app.shared_kernel.content_filter import ContentFilter


def utc_today() -> date:
    """Return today's date in UTC."""
    return datetime.now(UTC).date()


async def _resolve_connections(
    repos: GraphRepos, where: Group | None, scope: ContentFilter
) -> ConnectionResolution:
    """Resolve connection conditions with one read per kind of lookup."""
    named = connection_references(where)
    directional: dict[str, bool] = {}
    if named.slugs:
        directional = {
            str(t.slug): t.directional
            for t in await load_edge_types(repos)
            if str(t.slug) in named.slugs
        }
    visible: set[uuid.UUID] = set()
    if named.items:
        found = await repos.nodes.list(
            scope=scope, after=None, limit=len(named.items), ids=named.items
        )
        visible = {node.id for node in found}
    return resolve_connections(where, directional=directional, visible=visible)


async def prepare_query(
    repos: GraphRepos,
    raw: Mapping[str, Any],
    today: date,
    *,
    scope: ContentFilter,
    self_id: uuid.UUID | None = None,
) -> tuple[ResolvedQuery, list[QueryWarning]]:
    """Return the query ready to run, and the conditions that no longer apply.

    `scope` decides which collections the query may name. `self_id` is the smart
    collection being saved, so a reference back to it can be refused.

    Raises:
        InvalidQueryError: For a malformed query, an operator or value that does
            not fit a field that still exists, or a collection that refers to
            itself.
    """
    parsed = parse_query(raw)
    node_types = await load_node_types(repos)
    schemas = {str(t.slug): t.attributes_schema or {} for t in node_types}
    resolution = resolve_fields(parsed, schemas)
    expansion = await expand_collections(
        parsed.where,
        definitions=repos.definitions,
        scope=scope,
        schemas=schemas,
        self_id=self_id,
    )
    connections = await _resolve_connections(repos, expansion.where, scope)
    warnings = [*resolution.warnings, *expansion.warnings, *connections.warnings]
    if repos.external is None:
        warnings.extend(
            QueryWarning(path, "That cannot be checked here.")
            for path, condition in walk_conditions(expansion.where)
            if isinstance(condition, MediaCondition)
            or (
                isinstance(condition, CollectionCondition)
                and any(isinstance(t, ManualTarget) for t in condition.targets)
            )
        )
    resolved = ResolvedQuery(
        query=Query(where=expansion.where, sort=parsed.sort),
        field_kinds={**resolution.kinds, **expansion.kinds},
        search_exclusions={
            slug: keys
            for slug, schema in schemas.items()
            if (keys := search_excluded_keys(schema))
        },
        today=today,
        stale=resolution.stale | expansion.stale,
        relationships=connections.relationships,
        visible_items=connections.visible_items,
    )
    return resolved, warnings


async def count_matching(
    repos: GraphRepos,
    raw: Mapping[str, Any],
    scope: ContentFilter,
    *,
    cap: int | None,
    today: Callable[[], date] = utc_today,
) -> tuple[int, bool]:
    """Return how many items in `scope` match, up to `cap`, and whether it was capped.

    With `cap=None` the count is exact and never capped.

    Raises:
        InvalidQueryError: As `prepare_query`.
    """
    resolved, _ = await prepare_query(repos, raw, today(), scope=scope)
    if cap is None:
        return await repos.nodes.search_count(scope=scope, resolved=resolved), False
    # One past the cap tells "exactly the cap" from "more than the cap".
    counted = await repos.nodes.search_count(
        scope=scope, resolved=resolved, limit=cap + 1
    )
    return min(counted, cap), counted > cap
