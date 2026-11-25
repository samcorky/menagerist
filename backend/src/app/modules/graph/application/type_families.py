"""Let a parent item type stand for its subtypes when a query names it.

Filtering by Memorabilia should find its posters and figures; filtering by Poster
finds only posters. The evaluators match a type by its exact slug, so a query is
rewritten here, each time it runs, before they see it:

- a type condition naming a parent also names its subtypes (for "is one of" and for
  "is none of" alike, and nothing is added when no type is named);
- a field condition on a parent's field becomes "that, or the same on a subtype", so
  each leaf still reads one type's field;
- a sort on a parent's field is told the family (`ResolvedQuery.families`), since an
  ordering is one key, not an `or`.

Because this runs on the query as it is asked, a smart collection that names a parent
follows a subtype added after it was saved. A subtype's own schema includes what it
inherits, so a condition on a subtype may name an inherited field.
"""

from collections.abc import Mapping
from dataclasses import replace
from typing import TYPE_CHECKING, Any

from app.modules.graph.application.schema_meta import effective_schema
from app.modules.graph.domain.query import (
    ConnectionCondition,
    FieldCondition,
    Group,
    TypeCondition,
)

if TYPE_CHECKING:
    from collections.abc import Iterable

    from app.modules.graph.domain.node_type import NodeType
    from app.modules.graph.domain.query import Condition

type Families = Mapping[str, tuple[str, ...]]


def type_views(
    node_types: Iterable[NodeType],
) -> tuple[dict[str, dict[str, Any]], dict[str, tuple[str, ...]]]:
    """The fields each type uses, and each parent's subtypes, by slug.

    A subtype's fields are its parent's followed by its own. A parent with no
    subtype is not in the second mapping.
    """
    by_slug = {str(t.slug): t for t in node_types}
    schemas: dict[str, dict[str, Any]] = {}
    subtypes: dict[str, list[str]] = {}
    for slug, node_type in by_slug.items():
        parent = by_slug.get(node_type.parent) if node_type.parent else None
        schemas[slug] = (
            effective_schema(
                parent.attributes_schema if parent else None,
                node_type.attributes_schema,
            )
            or {}
        )
        if parent is not None:
            subtypes.setdefault(str(parent.slug), []).append(slug)
    return schemas, {parent: tuple(subs) for parent, subs in subtypes.items()}


def _type(condition: TypeCondition, families: Families) -> TypeCondition:
    slugs = list(condition.slugs)
    for slug in condition.slugs:
        slugs.extend(s for s in families.get(slug, ()) if s not in slugs)
    return replace(condition, slugs=tuple(slugs))


def _field(condition: FieldCondition, families: Families) -> Group | FieldCondition:
    if condition.type is None or condition.type not in families:
        return condition
    return Group(
        op="or",
        children=(
            condition,
            *(replace(condition, type=sub) for sub in families[condition.type]),
        ),
    )


def _group(group: Group, families: Families) -> Group:
    children: list[Group | Condition] = []
    for child in group.children:
        if isinstance(child, Group):
            children.append(_group(child, families))
        elif isinstance(child, TypeCondition):
            children.append(_type(child, families))
        elif isinstance(child, FieldCondition):
            children.append(_field(child, families))
        elif isinstance(child, ConnectionCondition) and child.where is not None:
            children.append(replace(child, where=_group(child.where, families)))
        else:
            children.append(child)
    return replace(group, children=tuple(children))


def expand_type_families(where: Group | None, families: Families) -> Group | None:
    """Rewrite every type and field condition under `where` to cover subtypes."""
    if where is None or not families:
        return where
    return _group(where, families)
