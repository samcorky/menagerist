"""Total, average, count or compare a field over the items a query matches."""

from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import date  # noqa: TC003
from typing import TYPE_CHECKING, Any, ClassVar

import structlog

from app.modules.graph.application.field_scope_expansion import fields_reached
from app.modules.graph.application.permissions import GraphPermission
from app.modules.graph.application.prepare_query import prepare_query, utc_today
from app.modules.graph.application.type_catalogue import load_node_types
from app.modules.graph.application.type_families import type_views
from app.modules.graph.domain.aggregate import (
    KINDS_BY_FUNCTION,
    Measure,
    MeasureSource,
    MeasureValue,
    ResolvedMeasure,
    parse_measures,
)
from app.modules.graph.domain.query import InvalidQueryError, QueryWarning
from app.modules.graph.ports.unit_of_work import GraphRepos
from app.shared_kernel.access import Access, Content

# Needed at runtime: the CQRS signature test evaluates __init__ annotations.
from app.shared_kernel.actor import Actor  # noqa: TC001
from app.shared_kernel.cqrs import QueryHandler

if TYPE_CHECKING:
    from app.shared_kernel.access_guard import AccessGuard

logger = structlog.get_logger()

# What a request without a query asks about: every item.
EVERYTHING: Mapping[str, Any] = {"v": 1}


@dataclass(kw_only=True)
class AggregateNodesQuery:
    """A condition tree (as JSON) and the measures to take over what it matches."""

    measures: Sequence[object]
    query: Mapping[str, Any] = field(default_factory=lambda: dict(EVERYTHING))


@dataclass(frozen=True)
class AggregateNodesResult:
    """How many items matched, one value per measure in order, and stale warnings.

    A measure whose field no longer exists has no value and a warning at its path.
    """

    items: int
    values: list[MeasureValue]
    warnings: list[QueryWarning]


class AggregateNodes(
    QueryHandler[GraphRepos, AggregateNodesQuery, AggregateNodesResult]
):
    """Aggregate fields of the items a query matches, in the actor's scope.

    The query is parsed and resolved as `SearchNodes` does it, so the items
    aggregated are exactly the ones that search lists. Money is totalled per
    currency, never converted.
    """

    access: ClassVar[Access] = Content(GraphPermission.ITEM_READ)

    def __init__(
        self,
        repos: GraphRepos,
        guard: AccessGuard,
        today: Callable[[], date] = utc_today,
    ) -> None:
        super().__init__(repos, guard)
        self._today = today

    async def _handle(
        self, query: AggregateNodesQuery, actor: Actor
    ) -> AggregateNodesResult:
        """Return the aggregates.

        Raises:
            InvalidQueryError: For a malformed query or measure, or a function
                that cannot read the kind of field it names.
        """
        measures = parse_measures(query.measures)
        scope = self.scope(actor)
        resolved, warnings = await prepare_query(
            self._repos, query.query, self._today(), scope=scope
        )
        node_types = await load_node_types(self._repos, scope)
        schemas, families = type_views(node_types)
        ready: list[ResolvedMeasure | None] = []
        for index, measure in enumerate(measures):
            path = f"measures[{index}]"
            found = _resolve(measure, schemas, families, path)
            if found is None:
                warnings.append(QueryWarning(path, "That field no longer exists."))
            ready.append(found)
        runnable = [m for m in ready if m is not None]
        counted = await self._repos.nodes.search_count(scope=scope, resolved=resolved)
        answers = iter(
            await self._repos.nodes.aggregate(
                scope=scope, resolved=resolved, measures=runnable
            )
        )
        values = [MeasureValue() if found is None else next(answers) for found in ready]
        logger.debug("nodes aggregated", measures=len(values), items=counted)
        return AggregateNodesResult(items=counted, values=values, warnings=warnings)


def _fields_of(
    measure: Measure,
    schemas: Mapping[str, Mapping[str, Any]],
    families: Mapping[str, tuple[str, ...]],
) -> tuple[dict[str, list[str]], set[str]]:
    """The types that hold the measure's field under each key, and the kinds seen."""
    by_key: dict[str, list[str]] = {}
    kinds: set[str] = set()
    if measure.origin is not None:
        # Each type is listed on its own: a subtype's schema already holds the field.
        for slug, key, kind in fields_reached(schemas, origin=measure.origin):
            by_key.setdefault(key, []).append(slug)
            kinds.add(kind)
        return by_key, kinds
    for slug, key, kind in fields_reached(schemas, key=measure.key):
        if slug == measure.type:
            by_key.setdefault(key, []).extend((slug, *families.get(slug, ())))
            kinds.add(kind)
    return by_key, kinds


def _resolve(
    measure: Measure,
    schemas: Mapping[str, Mapping[str, Any]],
    families: Mapping[str, tuple[str, ...]],
    path: str,
) -> ResolvedMeasure | None:
    """Check the measure against the item types; None when its field is gone.

    Raises:
        InvalidQueryError: If its function cannot read the field's kind, or the
            fields a saved field reaches are of different kinds.
    """
    if not measure.has_field:
        return ResolvedMeasure(measure=measure, kind=None, sources=())
    by_key, kinds = _fields_of(measure, schemas, families)
    if not by_key:
        return None
    if len(kinds) > 1:
        raise InvalidQueryError(
            f"That saved field is of different kinds ({', '.join(sorted(kinds))}).",
            path=path,
        )
    (kind,) = kinds
    allowed = KINDS_BY_FUNCTION[measure.fn]
    if allowed is not None and kind not in allowed:
        raise InvalidQueryError(
            f"`{measure.fn}` cannot read a {kind} field.", path=path
        )
    sources = tuple(
        MeasureSource(types=tuple(dict.fromkeys(types)), key=key)
        for key, types in by_key.items()
    )
    return ResolvedMeasure(measure=measure, kind=kind, sources=sources)
