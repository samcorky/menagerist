"""Parse a stored query and resolve it against the current item types."""

from datetime import UTC, date, datetime
from typing import TYPE_CHECKING, Any

from app.modules.graph.application.query_resolution import resolve_fields
from app.modules.graph.application.schema_meta import search_excluded_keys
from app.modules.graph.application.type_catalogue import load_node_types
from app.modules.graph.domain.query import QueryWarning, ResolvedQuery, parse_query

if TYPE_CHECKING:
    from collections.abc import Callable, Mapping

    from app.modules.graph.ports.unit_of_work import GraphRepos
    from app.shared_kernel.content_filter import ContentFilter


def utc_today() -> date:
    """Return today's date in UTC."""
    return datetime.now(UTC).date()


async def prepare_query(
    repos: GraphRepos, raw: Mapping[str, Any], today: date
) -> tuple[ResolvedQuery, list[QueryWarning]]:
    """Return the query ready to run, and the conditions that no longer apply.

    Raises:
        InvalidQueryError: For a malformed query, or an operator or value that
            does not fit a field that still exists.
    """
    parsed = parse_query(raw)
    node_types = await load_node_types(repos)
    schemas = {str(t.slug): t.attributes_schema or {} for t in node_types}
    resolution = resolve_fields(parsed, schemas)
    resolved = ResolvedQuery(
        query=parsed,
        field_kinds=resolution.kinds,
        search_exclusions={
            slug: keys
            for slug, schema in schemas.items()
            if (keys := search_excluded_keys(schema))
        },
        today=today,
        stale=resolution.stale,
    )
    return resolved, resolution.warnings


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
    resolved, _ = await prepare_query(repos, raw, today())
    if cap is None:
        return await repos.nodes.search_count(scope=scope, resolved=resolved), False
    # One past the cap tells "exactly the cap" from "more than the cap".
    counted = await repos.nodes.search_count(
        scope=scope, resolved=resolved, limit=cap + 1
    )
    return min(counted, cap), counted > cap
