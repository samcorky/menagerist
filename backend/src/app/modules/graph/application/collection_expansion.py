"""Resolve "in collection" conditions: what each collection is, and its limits.

A manual collection is matched by its membership rows. A smart collection is
inlined as its stored filter, up to `MAX_NESTING` levels, never twice on one
path and at most `MAX_EXPANSIONS` times per query. Anything else (gone, not the
caller's, cyclic, too deep) becomes a stale target with a warning and matches
nothing. A smart collection that reaches the one being saved is refused.
"""

import uuid
from collections.abc import Mapping
from dataclasses import dataclass, field, replace
from typing import TYPE_CHECKING, Any, Final

from app.modules.graph.application.query_resolution import resolve_fields
from app.modules.graph.domain.query import (
    CollectionCondition,
    CollectionTarget,
    FieldCondition,
    FieldKey,
    Group,
    InvalidQueryError,
    ManualTarget,
    Query,
    QueryWarning,
    SmartTarget,
    StaleTarget,
    parse_query,
)
from app.modules.graph.ports.collection_definitions import CollectionDefinitions
from app.shared_kernel.content_filter import ContentFilter

if TYPE_CHECKING:
    from app.modules.graph.domain.query import Condition

MAX_NESTING: Final = 3
MAX_EXPANSIONS: Final = 50
GONE: Final = "That collection no longer exists."

type _Trail = tuple[uuid.UUID, ...]


@dataclass(kw_only=True)
class Expansion:
    """The query filter with collection targets filled in.

    `kinds` and `stale` cover the fields of inlined smart collections, to be
    merged with the query's own.
    """

    where: Group | None
    kinds: dict[FieldKey, str] = field(default_factory=dict)
    stale: set[FieldCondition] = field(default_factory=set)
    warnings: list[QueryWarning] = field(default_factory=list)


@dataclass
class _Expander:
    definitions: CollectionDefinitions | None
    scope: ContentFilter
    schemas: Mapping[str, Mapping[str, Any]]
    self_id: uuid.UUID | None
    out: Expansion
    expansions: int = 0

    async def group(self, group: Group, path: str, trail: _Trail) -> Group:
        children: list[Group | Condition] = []
        for index, child in enumerate(group.children):
            child_path = f"{path}.children[{index}]"
            if isinstance(child, Group):
                children.append(await self.group(child, child_path, trail))
            elif isinstance(child, CollectionCondition):
                targets = [
                    await self.target(cid, f"{child_path}.in[{n}]", trail)
                    for n, cid in enumerate(child.ids)
                ]
                children.append(replace(child, targets=tuple(targets)))
            else:
                children.append(child)
        return replace(group, children=tuple(children))

    def stale(self, collection_id: uuid.UUID, path: str, why: str) -> CollectionTarget:
        self.out.warnings.append(QueryWarning(path, why))
        return StaleTarget(id=collection_id)

    async def target(
        self, collection_id: uuid.UUID, path: str, trail: _Trail
    ) -> CollectionTarget:
        if collection_id == self.self_id:
            names = " > ".join(str(c) for c in (*trail, collection_id))
            msg = f"A smart collection cannot refer to itself ({names})."
            raise InvalidQueryError(msg, path=path)
        if collection_id in trail:
            return self.stale(
                collection_id, path, "That collection refers back to itself."
            )
        if len(trail) >= MAX_NESTING:
            return self.stale(collection_id, path, "Collections are nested too deeply.")
        found = (
            None
            if self.definitions is None
            else await self.definitions.get(collection_id, self.scope)
        )
        if found is None:
            return self.stale(collection_id, path, GONE)
        if found.definition is None:
            return ManualTarget(id=collection_id)
        if self.expansions >= MAX_EXPANSIONS:
            return self.stale(
                collection_id, path, "This search uses too many collections."
            )
        self.expansions += 1
        return await self.smart(collection_id, found.definition, path, trail)

    async def smart(
        self,
        collection_id: uuid.UUID,
        definition: Mapping[str, Any],
        path: str,
        trail: _Trail,
    ) -> CollectionTarget:
        try:
            parsed = parse_query(definition)
            resolution = resolve_fields(Query(where=parsed.where), self.schemas)
        except InvalidQueryError:
            return self.stale(
                collection_id, path, "That collection's search is no longer valid."
            )
        self.out.kinds.update(resolution.kinds)
        self.out.stale.update(resolution.stale)
        self.out.warnings.extend(
            QueryWarning(path + w.path.removeprefix("where"), w.message)
            for w in resolution.warnings
        )
        where = None
        if parsed.where is not None:
            where = await self.group(parsed.where, path, (*trail, collection_id))
        return SmartTarget(id=collection_id, where=where)


async def expand_collections(
    where: Group | None,
    *,
    definitions: CollectionDefinitions | None,
    scope: ContentFilter,
    schemas: Mapping[str, Mapping[str, Any]],
    self_id: uuid.UUID | None,
) -> Expansion:
    """Fill in the targets of every collection condition under `where`.

    Raises:
        InvalidQueryError: If a smart collection reaches `self_id`.
    """
    out = Expansion(where=None)
    if where is not None:
        expander = _Expander(definitions, scope, schemas, self_id, out)
        out.where = await expander.group(where, "where", ())
    return out
