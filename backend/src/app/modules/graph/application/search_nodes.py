"""Search items with a saved-able condition tree."""

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import UTC, date, datetime
from typing import Any

import structlog

from app.modules.graph.application.query_cursor import decode_cursor, encode_cursor
from app.modules.graph.application.query_resolution import resolve_fields
from app.modules.graph.application.schema_meta import search_excluded_keys
from app.modules.graph.application.type_catalogue import load_node_types
from app.modules.graph.domain.node import Node
from app.modules.graph.domain.query import (
    Cursor,
    FieldKey,
    InvalidQueryError,
    QueryWarning,
    ResolvedQuery,
    SortKey,
    parse_query,
)
from app.modules.graph.ports.unit_of_work import GraphRepos

# Needed at runtime: the CQRS signature test evaluates __init__ annotations.
from app.shared_kernel.access_policy import AccessPolicy  # noqa: TC001
from app.shared_kernel.actor import Actor  # noqa: TC001
from app.shared_kernel.cqrs import ScopedQueryHandler

logger = structlog.get_logger()

MAX_LIMIT = 200
TOTAL_CAP = 1000
_NUMERIC_KINDS = frozenset({"number", "duration", "rating", "money"})


def _utc_today() -> date:
    return datetime.now(UTC).date()


def _is_number(value: object) -> bool:
    return isinstance(value, int | float) and not isinstance(value, bool)


def _fits_sort_key(key: SortKey, value: object, kinds: Mapping[FieldKey, str]) -> bool:
    """Whether a cursor `value` has the type its sort `key` produces."""
    if value is None:
        return True
    if key.by == "name":
        return isinstance(value, str)
    if key.by in {"created", "updated"}:
        return _is_number(value)
    kind = kinds.get((key.type or "", key.key or "", None))
    if kind is None:
        return False
    return _is_number(value) if kind in _NUMERIC_KINDS else isinstance(value, str)


def _check_cursor_types(
    cursor: Cursor, sort: tuple[SortKey, ...], kinds: Mapping[FieldKey, str]
) -> None:
    """Reject a cursor whose values do not fit the query's sort keys."""
    for key, value in zip(sort, cursor.sort_values, strict=True):
        if not _fits_sort_key(key, value, kinds):
            raise InvalidQueryError("Not a valid cursor.", path="cursor")


@dataclass(kw_only=True)
class SearchNodesQuery:
    """A condition tree (as JSON), a page size and an optional cursor."""

    query: Mapping[str, Any]
    limit: int = 50
    cursor: str | None = None


@dataclass(frozen=True)
class SearchNodesResult:
    """One page of matches, the total, where to resume, and stale conditions.

    `total` is exact up to the cap; when `total_capped` it is a lower bound.
    """

    items: list[Node]
    total: int
    total_capped: bool
    next_cursor: str | None
    warnings: list[QueryWarning]


class SearchNodes(ScopedQueryHandler[GraphRepos, SearchNodesQuery, SearchNodesResult]):
    """Search items by condition tree, ordered and paged by keyset."""

    def __init__(
        self,
        repos: GraphRepos,
        policy: AccessPolicy,
        today: Callable[[], date] = _utc_today,
        total_cap: int = TOTAL_CAP,
    ) -> None:
        super().__init__(repos, policy)
        self._today = today
        self._total_cap = total_cap

    async def handle(self, query: SearchNodesQuery, actor: Actor) -> SearchNodesResult:
        """Return a page of matching items.

        Raises:
            InvalidQueryError: For a malformed query, limit or cursor, or an
                operator or value that does not fit a field.
        """
        if not 1 <= query.limit <= MAX_LIMIT:
            raise InvalidQueryError(
                f"The limit must be 1 to {MAX_LIMIT}.", path="limit"
            )
        parsed = parse_query(query.query)
        node_types = await load_node_types(self._repos)
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
            today=self._today(),
        )
        after: Cursor | None = None
        if query.cursor is not None:
            after = decode_cursor(query.cursor, sort_count=len(parsed.sort))
            _check_cursor_types(after, parsed.sort, resolution.kinds)
        scope = self._policy.scope_for(actor)
        hits = await self._repos.nodes.search(
            scope=scope, resolved=resolved, after=after, limit=query.limit + 1
        )
        # One past the cap tells "exactly the cap" from "more than the cap".
        counted = await self._repos.nodes.search_count(
            scope=scope, resolved=resolved, limit=self._total_cap + 1
        )
        total = min(counted, self._total_cap)
        page = hits[: query.limit]
        next_cursor = None
        if len(hits) > query.limit:
            last = page[-1]
            next_cursor = encode_cursor(
                Cursor(sort_values=last.sort_values, id=last.node.id)
            )
        logger.debug("nodes searched", count=len(page), total=total)
        return SearchNodesResult(
            items=[hit.node for hit in page],
            total=total,
            total_capped=counted > self._total_cap,
            next_cursor=next_cursor,
            warnings=resolution.warnings,
        )
