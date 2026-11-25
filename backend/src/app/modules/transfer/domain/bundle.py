"""What a bundle is made of: the vocabulary targets create, inspect and remove."""

import re
from collections.abc import Mapping
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any, Final

from app.modules.transfer.domain.errors import InvalidBundleError

PRESET_MARKER = "$preset"

# The envelope of a bundle file a person exports and imports. Version 1 carries
# presets only; version 2 adds relationship types and item types; version 3 adds
# items, connections and collections. Export always writes the latest.
BUNDLE_FORMAT = "menagerist-bundle"
BUNDLE_VERSION = 3
PRESETS_ONLY_VERSION = 1
TYPES_VERSION = 2


# What one bundle may hold, whatever its source. Example packs have the same.
MAX_ITEMS = 500
MAX_CONNECTIONS = 2000
MAX_COLLECTIONS = 100
# Mirrors the collections module's name limit; transfer must not import it.
MAX_COLLECTION_NAME = 120

COVER_STYLES = ("sleeve", "poster", "box", "card")


REF_PATTERN = re.compile(r"^[a-z0-9][a-z0-9-]*\Z")


REF_RULE = "must be lowercase letters, digits and hyphens"
# Which end of a relationship holds the other; mirrors the graph's `HOLDERS`.
RELATIONSHIP_HOLDERS: Final = ("source", "target", "none")


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


def unportable_condition(node: object, path: str = "") -> tuple[str, str] | None:
    """Return the path and reason of the first condition a bundle cannot carry.

    Walks a smart collection's definition generically, as the graph query model
    is not this module's to import. A condition on another collection and a
    connection to one particular item name ids that a bundle cannot know.
    """
    if isinstance(node, dict):
        kind = node.get("kind")
        if kind == "collection":
            return path, "a collection condition cannot be in a bundle"
        if kind == "connection" and "item" in node:
            return path, "a connection to one item cannot be in a bundle"
        children = [(f"{path}.{k}" if path else str(k), v) for k, v in node.items()]
    elif isinstance(node, list):
        children = [(f"{path}[{i}]", v) for i, v in enumerate(node)]
    else:
        return None
    for child_path, child in children:
        found = unportable_condition(child, child_path)
        if found is not None:
            return found
    return None


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
    """A relationship type (an edge type) the pack creates.

    `holder` is which end holds the other (`source`, `target` or `none`), as on
    the graph's relationship types; the graph checks it again on creation.
    `source_types` and `target_types` list the item type slugs allowed at each
    end; empty means no limit.
    """

    ref: str
    slug: str
    label: str
    reverse_label: str | None = None
    description: str | None = None
    directional: bool = True
    attributes_schema: dict[str, Any] | None = None
    holder: str = "none"
    source_types: tuple[str, ...] = ()
    target_types: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        """Reject a holder outside the closed set."""
        if self.holder not in RELATIONSHIP_HOLDERS:
            raise InvalidBundleError(
                f"relationship type '{self.ref}' has unknown holder "
                + f"'{self.holder}'; use one of {', '.join(RELATIONSHIP_HOLDERS)}"
            )


@dataclass(kw_only=True, frozen=True, eq=False)
class BundleCover:
    """How the covers of a type's items are drawn."""

    style: str


@dataclass(kw_only=True, frozen=True, eq=False)
class BundleItemType:
    """An item type (a node type) the pack creates.

    `parent` is the ref of the item type this is a subtype of, in the same bundle.
    """

    ref: str
    slug: str
    label: str
    description: str | None = None
    attributes_schema: dict[str, Any] | None = None
    cover: BundleCover | None = None
    icon: str | None = None
    colour: str | None = None
    parent: str | None = None

    def __post_init__(self) -> None:
        """Reject a cover style outside the closed set."""
        if self.cover is not None and self.cover.style not in COVER_STYLES:
            raise InvalidBundleError(
                f"item type '{self.ref}' has unknown cover style "
                + f"'{self.cover.style}'; use one of {', '.join(COVER_STYLES)}"
            )


class NameLookup(StrEnum):
    """What happens to an item found by name when the person has none called that."""

    CREATE = "create"
    SKIP = "skip"


@dataclass(kw_only=True, frozen=True, eq=False)
class BundleItem:
    """An item (a node) the pack creates; `type_ref` is `None` for an untyped item.

    With `lookup`, the item is the person's own of its type with the same name, if
    there is exactly one; otherwise it is created or left out, as `lookup` says.
    """

    ref: str
    name: str
    type_ref: str | None = None
    description: str | None = None
    attributes: dict[str, Any] = field(default_factory=dict)
    tags: tuple[str, ...] = ()
    extra_schema: dict[str, Any] | None = None
    source_key: str | None = None
    lookup: NameLookup | None = None


@dataclass(kw_only=True, frozen=True, eq=False)
class BundleConnection:
    """A connection (an edge) between two pack items.

    A `source_key` links it, as an item's does, so importing it again finds it.
    """

    source_ref: str
    target_ref: str
    type_ref: str
    attributes: dict[str, Any] = field(default_factory=dict)
    source_key: str | None = None


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
class BundleSource:
    """A source whose rows can be imported again, such as a database or a sheet.

    `name` identifies the source in source links. `key_field` is the item field
    (`name` or an attribute key) that finds an item the person made by hand. With
    `require_keys`, an item without a source key is skipped rather than created.
    """

    name: str
    key_field: str | None = None
    require_keys: bool = False


def _field_keys(item_type: BundleItemType) -> set[str]:
    """The keys of the fields an item type's schema defines."""
    properties = (item_type.attributes_schema or {}).get("properties")
    return set(properties) if isinstance(properties, dict) else set()


@dataclass(kw_only=True, frozen=True, eq=False)
class Bundle:
    """What one import or install brings in, whatever its source.

    A source (a file, a catalogue entry) is decoded into a bundle, which is then
    planned and applied the same way. Refs are unique within each kind. A bundle
    with a `source` gives its items and connections `source_key`s, so they can be
    linked. A source that reads whole spreadsheets may raise `item_limit` and
    `connection_limit` above the defaults.
    """

    id: str
    source: BundleSource | None = None
    item_limit: int = MAX_ITEMS
    connection_limit: int = MAX_CONNECTIONS
    presets: tuple[BundlePreset, ...] = ()
    relationship_types: tuple[BundleRelationshipType, ...] = ()
    item_types: tuple[BundleItemType, ...] = ()
    items: tuple[BundleItem, ...] = ()
    connections: tuple[BundleConnection, ...] = ()
    collections: tuple[BundleCollection, ...] = ()

    def __post_init__(self) -> None:
        """Reject two entities of one kind sharing a ref.

        Raises:
            InvalidBundleError: if a ref repeats within a kind.
        """
        for name, specs in (
            ("preset", self.presets),
            ("relationship type", self.relationship_types),
            ("item type", self.item_types),
            ("item", self.items),
            ("collection", self.collections),
        ):
            refs = [s.ref for s in specs]
            if len(set(refs)) != len(refs):
                raise InvalidBundleError(f"each {name} needs its own ref")
        self._check_size()
        self._check_collections()
        self._check_lookups()
        self._check_source()
        self._check_parents()

    def _check_parents(self) -> None:
        """Each parent is another type here, one level deep, sharing no field key."""
        by_ref = {t.ref: t for t in self.item_types}
        for subtype in self.item_types:
            if subtype.parent is None:
                continue
            parent = by_ref.get(subtype.parent)
            where = f"item type '{subtype.ref}'"
            if subtype.parent == subtype.ref:
                raise InvalidBundleError(f"{where} cannot be its own parent")
            if parent is None:
                raise InvalidBundleError(
                    f"{where} names the parent '{subtype.parent}', "
                    + "which is not in the file"
                )
            if parent.parent is not None:
                raise InvalidBundleError(
                    f"{where} has the parent '{parent.ref}', which is itself a "
                    + "subtype; only one level of parent types is supported"
                )
            shared = _field_keys(subtype) & _field_keys(parent)
            if shared:
                raise InvalidBundleError(
                    f"{where} has fields its parent '{parent.ref}' already has: "
                    + ", ".join(sorted(shared))
                )

    def _check_lookups(self) -> None:
        for item in self.items:
            if item.lookup is None:
                continue
            if item.source_key is not None:
                raise InvalidBundleError(
                    f"item '{item.ref}': an item found by name has no source key"
                )
            if item.type_ref is None:
                raise InvalidBundleError(
                    f"item '{item.ref}': an item found by name needs a type"
                )

    def _check_source(self) -> None:
        source = self.source
        keyed: list[BundleItem | BundleConnection] = [*self.items, *self.connections]
        if source is None:
            if any(spec.source_key is not None for spec in keyed):
                raise InvalidBundleError(
                    "items or connections have source keys but there is no source"
                )
            return
        if not source.name.strip():
            raise InvalidBundleError("a source needs a name")
        if source.key_field is not None and not source.key_field.strip():
            raise InvalidBundleError("a source's key field cannot be blank")
        self._check_keys()

    def _check_keys(self) -> None:
        for item in self.items:
            if item.source_key is not None and not item.source_key.strip():
                raise InvalidBundleError(f"item '{item.ref}' has a blank source key")
        for n, connection in enumerate(self.connections):
            if connection.source_key is not None and not connection.source_key.strip():
                raise InvalidBundleError(f"connection {n} has a blank source key")

    def _check_size(self) -> None:
        for name, count, limit in (
            ("items", len(self.items), self.item_limit),
            ("connections", len(self.connections), self.connection_limit),
            ("collections", len(self.collections), MAX_COLLECTIONS),
        ):
            if count > limit:
                raise InvalidBundleError(f"a bundle may hold at most {limit} {name}")

    def _check_collections(self) -> None:
        for collection in self.collections:
            if not 1 <= len(collection.name.strip()) <= MAX_COLLECTION_NAME:
                raise InvalidBundleError(
                    f"collection '{collection.ref}' needs a name of "
                    + f"1 to {MAX_COLLECTION_NAME} characters"
                )
            if len(set(collection.item_refs)) != len(collection.item_refs):
                raise InvalidBundleError(
                    f"collection '{collection.ref}' lists an item twice"
                )
