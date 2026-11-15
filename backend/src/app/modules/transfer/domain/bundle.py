"""What a bundle is made of: the vocabulary targets create, inspect and remove."""

import re
from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any

from app.modules.transfer.domain.errors import InvalidBundleError

PRESET_MARKER = "$preset"

# The envelope of a bundle file a person exports and imports. Version 1 carries
# presets only; types, items and collections join it in later versions.
BUNDLE_FORMAT = "menagerist-bundle"
BUNDLE_VERSION = 1


COVER_STYLES = ("sleeve", "poster", "box", "card")


REF_PATTERN = re.compile(r"^[a-z0-9][a-z0-9-]*\Z")


REF_RULE = "must be lowercase letters, digits and hyphens"


def split_ref(ref: str) -> tuple[str | None, str]:
    """Split a `pack:ref` reference into its pack id and local ref.

    A ref without a colon is local and returns `(None, ref)`.

    Raises:
        InvalidBundleError: If the ref has more than one colon or a malformed part.
    """
    if ":" not in ref:
        return None, ref
    parts = ref.split(":")
    if len(parts) != 2:
        raise InvalidBundleError(f"ref '{ref}': pack:ref needs exactly one colon")
    pack_id, local = parts
    if not REF_PATTERN.match(pack_id) or not REF_PATTERN.match(local):
        raise InvalidBundleError(f"ref '{ref}' {REF_RULE} on both sides of the colon")
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
                raise InvalidBundleError(f"unknown preset '{ref}'")
            return ids[ref]
        return {k: resolve_preset_refs(v, ids) for k, v in value.items()}
    if isinstance(value, list):
        return [resolve_preset_refs(v, ids) for v in value]
    return value


@dataclass(kw_only=True, frozen=True, eq=False)
class BundlePreset:
    """A saved field, field group or choice list the pack creates."""

    ref: str
    kind: str
    label: str
    description: str | None = None
    definition: dict[str, Any] = field(default_factory=dict)


@dataclass(kw_only=True, frozen=True, eq=False)
class BundleRelationshipType:
    """A relationship type (an edge type) the pack creates."""

    ref: str
    slug: str
    label: str
    reverse_label: str | None = None
    description: str | None = None
    directional: bool = True
    attributes_schema: dict[str, Any] | None = None


@dataclass(kw_only=True, frozen=True, eq=False)
class BundleCover:
    """How the covers of a type's items are drawn."""

    style: str


@dataclass(kw_only=True, frozen=True, eq=False)
class BundleItemType:
    """An item type (a node type) the pack creates."""

    ref: str
    slug: str
    label: str
    description: str | None = None
    attributes_schema: dict[str, Any] | None = None
    cover: BundleCover | None = None
    icon: str | None = None
    colour: str | None = None

    def __post_init__(self) -> None:
        """Reject a cover style outside the closed set."""
        if self.cover is not None and self.cover.style not in COVER_STYLES:
            raise InvalidBundleError(
                f"item type '{self.ref}' has unknown cover style "
                + f"'{self.cover.style}'; use one of {', '.join(COVER_STYLES)}"
            )


@dataclass(kw_only=True, frozen=True, eq=False)
class BundleItem:
    """An item (a node) the pack creates."""

    ref: str
    type_ref: str
    name: str
    description: str | None = None
    attributes: dict[str, Any] = field(default_factory=dict)
    tags: tuple[str, ...] = ()
    extra_schema: dict[str, Any] | None = None


@dataclass(kw_only=True, frozen=True, eq=False)
class BundleConnection:
    """A connection (an edge) between two pack items."""

    source_ref: str
    target_ref: str
    type_ref: str
    attributes: dict[str, Any] = field(default_factory=dict)


@dataclass(kw_only=True, frozen=True, eq=False)
class BundleCollection:
    """A collection: a manual list of pack items, or a smart one with a `definition`.

    Exactly one of `item_refs` and `definition` is given. A definition is a query
    tree that names only things a pack can name stably.
    """

    ref: str
    name: str
    description: str | None = None
    item_refs: tuple[str, ...] = ()
    definition: Mapping[str, Any] | None = None


@dataclass(kw_only=True, frozen=True, eq=False)
class Bundle:
    """What one import or install brings in, whatever its source.

    A source (a file, a catalogue entry) is decoded into a bundle, which is then
    planned and applied the same way. Refs are unique within each kind.
    """

    id: str
    presets: tuple[BundlePreset, ...] = ()
    relationship_types: tuple[BundleRelationshipType, ...] = ()
    item_types: tuple[BundleItemType, ...] = ()

    def __post_init__(self) -> None:
        """Reject two entities of one kind sharing a ref.

        Raises:
            InvalidBundleError: if a ref repeats within a kind.
        """
        for name, specs in (
            ("preset", self.presets),
            ("relationship type", self.relationship_types),
            ("item type", self.item_types),
        ):
            refs = [s.ref for s in specs]
            if len(set(refs)) != len(refs):
                raise InvalidBundleError(f"each {name} needs its own ref")
