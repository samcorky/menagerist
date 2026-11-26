"""The fields a parent type's subtypes define for themselves, and which are the same.

The same field means the same key and the same kind, as it does when a per-item field is
promoted to its type (`field_definitions`). Listing what is repeated and moving it up to
the parent both read the subtypes this way.
"""

import json
from collections import Counter
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from app.modules.graph.application.field_definitions import field_kind
from app.modules.graph.application.schema_meta import archived_keys

if TYPE_CHECKING:
    from collections.abc import Sequence

    from app.modules.graph.domain.node_type import NodeType


@dataclass(frozen=True, eq=False)
class SharedField:
    """A field key two or more subtypes define as the same kind of field.

    `subtypes` are the slugs that define it as that kind and `differing` those that
    keep the key as another kind, which would stop it moving up.
    """

    key: str
    label: str
    kind: str | None
    subtypes: tuple[str, ...]
    differing: tuple[str, ...]


@dataclass(frozen=True, eq=False)
class Definition:
    """One subtype's live definition of a field key."""

    slug: str
    label: str
    prop: dict[str, Any]


def live_definitions(subtypes: Sequence[NodeType]) -> dict[str, list[Definition]]:
    """Each key the subtypes define and not archived, with every definition of it."""
    found: dict[str, list[Definition]] = {}
    for subtype in subtypes:
        schema = subtype.attributes_schema or {}
        properties = schema.get("properties")
        if not isinstance(properties, dict):
            continue
        hidden = archived_keys(schema)
        for key, prop in properties.items():
            if key not in hidden and isinstance(prop, dict):
                found.setdefault(key, []).append(
                    Definition(slug=str(subtype.slug), label=subtype.label, prop=prop)
                )
    return found


def most_common(definitions: Sequence[Definition]) -> dict[str, Any]:
    """The definition most subtypes share; the first seen wins a tie."""
    counts = Counter(json.dumps(d.prop, sort_keys=True) for d in definitions)
    winner = counts.most_common(1)[0][0]
    return next(
        d.prop for d in definitions if json.dumps(d.prop, sort_keys=True) == winner
    )


def shared_fields(subtypes: Sequence[NodeType]) -> list[SharedField]:
    """The keys two or more subtypes define as the same kind, in the order met."""
    shared: list[SharedField] = []
    for key, definitions in live_definitions(subtypes).items():
        kinds = Counter(field_kind(d.prop) for d in definitions)
        kind, count = kinds.most_common(1)[0]
        if count < 2:
            continue
        same = [d for d in definitions if field_kind(d.prop) == kind]
        title = most_common(same).get("title")
        shared.append(
            SharedField(
                key=key,
                label=title if isinstance(title, str) and title else key,
                kind=kind,
                subtypes=tuple(d.slug for d in same),
                differing=tuple(d.slug for d in definitions if d not in same),
            )
        )
    return shared
