"""Total, average, count or compare a field over the items a query matches.

Optionally split into groups by a field, the item type or a tag.
"""

from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field, replace
from datetime import date  # noqa: TC003
from typing import TYPE_CHECKING, Any, ClassVar

import structlog

from app.modules.graph.application.field_scope_expansion import fields_reached
from app.modules.graph.application.permissions import GraphPermission
from app.modules.graph.application.prepare_query import prepare_query, utc_today
from app.modules.graph.application.type_catalogue import load_node_types
from app.modules.graph.application.type_families import type_views
from app.modules.graph.domain.aggregate import (
    GROUPABLE_KINDS,
    KINDS_BY_FUNCTION,
    GroupBy,
    GroupValue,
    Measure,
    MeasureSource,
    MeasureValue,
    ResolvedGroup,
    ResolvedMeasure,
    arrange_groups,
    parse_group_by,
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

# The label of the group of items that have no value to group by.
UNSET_LABEL = "Unset"


@dataclass(kw_only=True)
class AggregateNodesQuery:
    """A condition tree (as JSON) and the measures to take over what it matches."""

    measures: Sequence[object]
    query: Mapping[str, Any] = field(default_factory=lambda: dict(EVERYTHING))
    group_by: Mapping[str, Any] | None = None


@dataclass(frozen=True)
class AggregateGroup:
    """One group of the items: its key, a label to show, its size and its values.

    The key is None, and the label "Unset", for the items with no value to group by.
    `values` has one entry per measure asked, in order.
    """

    key: str | None
    label: str
    count: int
    values: list[MeasureValue]


@dataclass(frozen=True)
class AggregateOther:
    """The items in the groups left out by the limit, each counted once."""

    groups: int
    count: int
    values: list[MeasureValue]


@dataclass(frozen=True)
class AggregateNodesResult:
    """How many items matched, one value per measure in order, and stale warnings.

    A measure whose field no longer exists has no value and a warning at its path.
    `groups` is None unless a grouping was asked for. An item in several groups
    (a tag, a multiple-choice value) counts in each, so group sizes and totals
    can add up to more than the whole.
    """

    items: int
    values: list[MeasureValue]
    warnings: list[QueryWarning]
    groups: list[AggregateGroup] | None = None
    other: AggregateOther | None = None


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
        grouping = None if query.group_by is None else parse_group_by(query.group_by)
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
        group = None
        if grouping is not None:
            _check_order(grouping, ready)
            group = _resolve_group(grouping, schemas, families)
            if group is None:
                warnings.append(
                    QueryWarning("group_by", "That field no longer exists.")
                )
        counted = await self._repos.nodes.search_count(scope=scope, resolved=resolved)
        answers = iter(
            await self._repos.nodes.aggregate(
                scope=scope, resolved=resolved, measures=runnable
            )
        )
        values = [MeasureValue() if found is None else next(answers) for found in ready]
        logger.debug("nodes aggregated", measures=len(values), items=counted)
        result = AggregateNodesResult(items=counted, values=values, warnings=warnings)
        if grouping is None:
            return result
        if group is None:
            return replace(result, groups=[])
        listed = await self._repos.nodes.aggregate_groups(
            scope=scope, resolved=resolved, group=group, measures=runnable
        )
        every = [_aligned(g, ready) for g in listed]
        shown, hidden = arrange_groups(every, grouping)
        other = None
        if hidden:
            rest = await self._repos.nodes.aggregate_outside_groups(
                scope=scope,
                resolved=resolved,
                group=group,
                measures=runnable,
                shown={g.key for g in shown},
            )
            other = AggregateOther(
                groups=len(hidden),
                count=rest.count,
                values=list(_aligned(rest, ready).values),
            )
        labels = {str(t.slug): t.label for t in node_types}
        return replace(
            result,
            groups=[_group(g, grouping, labels) for g in shown],
            other=other,
        )


def _check_order(grouping: GroupBy, ready: Sequence[ResolvedMeasure | None]) -> None:
    """Refuse to order by a measure that does not give one number per group."""
    if grouping.order != "measure":
        return
    index = grouping.measure or 0
    if index >= len(ready):
        raise InvalidQueryError(
            f"There is no measure {index} to order by.", path="group_by"
        )
    chosen = ready[index]
    if chosen is not None and chosen.per_currency:
        raise InvalidQueryError(
            "Money is not converted, so groups cannot be ordered by a money measure.",
            path="group_by",
        )


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
    return ResolvedMeasure(measure=measure, kind=kind, sources=_sources(by_key))


def _sources(by_key: Mapping[str, list[str]]) -> tuple[MeasureSource, ...]:
    return tuple(
        MeasureSource(types=tuple(dict.fromkeys(types)), key=key)
        for key, types in by_key.items()
    )


def _resolve_group(
    grouping: GroupBy,
    schemas: Mapping[str, Mapping[str, Any]],
    families: Mapping[str, tuple[str, ...]],
) -> ResolvedGroup | None:
    """Check the grouping against the item types; None when its field is gone.

    Raises:
        InvalidQueryError: If the field is of a kind that cannot name a group, or
            the fields a saved field reaches are of different kinds.
    """
    if grouping.by != "field":
        return ResolvedGroup(group=grouping, kind=None, sources=())
    named = Measure(
        fn="distinct", type=grouping.type, key=grouping.key, origin=grouping.origin
    )
    by_key, kinds = _fields_of(named, schemas, families)
    if not by_key:
        return None
    if len(kinds) > 1:
        raise InvalidQueryError(
            f"That saved field is of different kinds ({', '.join(sorted(kinds))}).",
            path="group_by",
        )
    (kind,) = kinds
    if kind not in GROUPABLE_KINDS:
        raise InvalidQueryError(
            f"Items cannot be grouped by a {kind} field.", path="group_by"
        )
    return ResolvedGroup(group=grouping, kind=kind, sources=_sources(by_key))


def _aligned(group: GroupValue, ready: Sequence[ResolvedMeasure | None]) -> GroupValue:
    """The group's values with an empty one where a measure's field is gone."""
    answers = iter(group.values)
    return GroupValue(
        key=group.key,
        count=group.count,
        values=tuple(MeasureValue() if m is None else next(answers) for m in ready),
    )


def _group(
    group: GroupValue, grouping: GroupBy, type_labels: Mapping[str, str]
) -> AggregateGroup:
    if group.key is None:
        label = UNSET_LABEL
    elif grouping.by == "type":
        label = type_labels.get(group.key, group.key)
    else:
        label = group.key
    return AggregateGroup(
        key=group.key, label=label, count=group.count, values=list(group.values)
    )
