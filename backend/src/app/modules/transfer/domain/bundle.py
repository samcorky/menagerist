"""What a bundle is made of: the vocabulary targets create, inspect and remove."""

import re
from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any

from app.modules.transfer.domain.errors import InvalidPackError

PRESET_MARKER = "$preset"


COVER_STYLES = ("sleeve", "poster", "box", "card")


REF_PATTERN = re.compile(r"^[a-z0-9][a-z0-9-]*\Z")


REF_RULE = "must be lowercase letters, digits and hyphens"


def split_ref(ref: str) -> tuple[str | None, str]:
    """Split a `pack:ref` reference into its pack id and local ref.

    A ref without a colon is local and returns `(None, ref)`.

    Raises:
        InvalidPackError: If the ref has more than one colon or a malformed part.
    """
    if ":" not in ref:
        return None, ref
    parts = ref.split(":")
    if len(parts) != 2:
        raise InvalidPackError(f"ref '{ref}': pack:ref needs exactly one colon")
    pack_id, local = parts
    if not REF_PATTERN.match(pack_id) or not REF_PATTERN.match(local):
        raise InvalidPackError(f"ref '{ref}' {REF_RULE} on both sides of the colon")
    return pack_id, local


def _is_marker(value: dict[str, Any]) -> bool:
    return set(value) == {PRESET_MARKER} and isinstance(value[PRESET_MARKER], str)


def preset_refs(value: Any) -> set[str]:  # noqa: ANN401
    """Return the preset refs named by `{"$preset": ref}` markers in `value`."""
    if isinstance(value, dict):
        if _is_marker(value):
            return {value[PRESET_MARKER]}
        return set().union(*(preset_refs(v) for v in value.values()))
    if isinstance(value, list):
        return set().union(*(preset_refs(v) for v in value))
    return set()


def resolve_preset_refs(value: Any, ids: Mapping[str, str]) -> Any:  # noqa: ANN401
    """Return a copy of `value` with each preset marker replaced by its id."""
    if isinstance(value, dict):
        if _is_marker(value):
            ref = value[PRESET_MARKER]
            if ref not in ids:
                raise InvalidPackError(f"unknown preset '{ref}'")
            return ids[ref]
        return {k: resolve_preset_refs(v, ids) for k, v in value.items()}
    if isinstance(value, list):
        return [resolve_preset_refs(v, ids) for v in value]
    return value


@dataclass(kw_only=True, frozen=True, eq=False)
class PackPreset:
    """A saved field, field group or choice list the pack creates."""

    ref: str
    kind: str
    label: str
    description: str | None = None
    definition: dict[str, Any] = field(default_factory=dict)


@dataclass(kw_only=True, frozen=True, eq=False)
class PackRelationshipType:
    """A relationship type (an edge type) the pack creates."""

    ref: str
    slug: str
    label: str
    reverse_label: str | None = None
    description: str | None = None
    directional: bool = True
    attributes_schema: dict[str, Any] | None = None


@dataclass(kw_only=True, frozen=True, eq=False)
class PackCover:
    """How the covers of a type's items are drawn."""

    style: str


@dataclass(kw_only=True, frozen=True, eq=False)
class PackItemType:
    """An item type (a node type) the pack creates."""

    ref: str
    slug: str
    label: str
    description: str | None = None
    attributes_schema: dict[str, Any] | None = None
    cover: PackCover | None = None
    icon: str | None = None
    colour: str | None = None

    def __post_init__(self) -> None:
        """Reject a cover style outside the closed set."""
        if self.cover is not None and self.cover.style not in COVER_STYLES:
            raise InvalidPackError(
                f"item type '{self.ref}' has unknown cover style "
                + f"'{self.cover.style}'; use one of {', '.join(COVER_STYLES)}"
            )


@dataclass(kw_only=True, frozen=True, eq=False)
class PackItem:
    """An item (a node) the pack creates."""

    ref: str
    type_ref: str
    name: str
    description: str | None = None
    attributes: dict[str, Any] = field(default_factory=dict)
    tags: tuple[str, ...] = ()
    extra_schema: dict[str, Any] | None = None


@dataclass(kw_only=True, frozen=True, eq=False)
class PackConnection:
    """A connection (an edge) between two pack items."""

    source_ref: str
    target_ref: str
    type_ref: str
    attributes: dict[str, Any] = field(default_factory=dict)


@dataclass(kw_only=True, frozen=True, eq=False)
class PackCollection:
    """A collection: a manual list of pack items, or a smart one with a `definition`.

    Exactly one of `item_refs` and `definition` is given. A definition is a query
    tree that names only things a pack can name stably.
    """

    ref: str
    name: str
    description: str | None = None
    item_refs: tuple[str, ...] = ()
    definition: Mapping[str, Any] | None = None
