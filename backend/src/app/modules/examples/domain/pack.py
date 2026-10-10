import re
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

from app.modules.examples.domain.errors import InvalidPackError
from app.modules.examples.domain.installation import EntityKind
from app.shared_kernel.slug import slugify

if TYPE_CHECKING:
    from collections.abc import Mapping

PRESET_MARKER = "$preset"
MAX_PRESETS = 50
MAX_TYPES = 50
MAX_ITEMS = 500
MAX_CONNECTIONS = 2000

_REF = re.compile(r"^[a-z0-9][a-z0-9-]*\Z")
_REF_RULE = "must be lowercase letters, digits and hyphens"
# Mirrors the collections module's name limit; examples must not import it.
_MAX_COLLECTION_NAME = 120

COVER_STYLES = ("sleeve", "poster", "box", "card")


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
    if not _REF.match(pack_id) or not _REF.match(local):
        raise InvalidPackError(f"ref '{ref}' {_REF_RULE} on both sides of the colon")
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
    """A manual collection of pack items."""

    ref: str
    name: str
    description: str | None = None
    item_refs: tuple[str, ...] = ()


@dataclass(kw_only=True, frozen=True, eq=False)
class PackCounts:
    """How many entities of each kind a pack holds, creates, or removed."""

    presets: int = 0
    relationship_types: int = 0
    item_types: int = 0
    items: int = 0
    connections: int = 0
    collections: int = 0


@dataclass(kw_only=True, frozen=True, eq=False)
class PackSummary:
    """A catalogue entry: what the Examples page lists."""

    id: str
    name: str
    description: str
    counts: PackCounts
    requires: tuple[str, ...] = ()


def _check_refs(section: str, refs: list[str]) -> None:
    for ref in refs:
        if not _REF.match(ref):
            raise InvalidPackError(f"{section} ref '{ref}' {_REF_RULE}")
    if len(set(refs)) != len(refs):
        raise InvalidPackError(f"{section} refs must be unique")


@dataclass(kw_only=True, frozen=True, eq=False)
class ExamplePack:
    """A pack's content. Validates its own references on construction."""

    id: str
    presets: tuple[PackPreset, ...] = ()
    relationship_types: tuple[PackRelationshipType, ...] = ()
    item_types: tuple[PackItemType, ...] = ()
    items: tuple[PackItem, ...] = ()
    connections: tuple[PackConnection, ...] = ()
    collections: tuple[PackCollection, ...] = ()
    requires: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        """Reject a pack whose references do not resolve or that is too large."""
        if not _REF.match(self.id):
            raise InvalidPackError(f"pack id '{self.id}' {_REF_RULE}")
        self._check_requires()
        self._check_limits()
        _check_refs("preset", [p.ref for p in self.presets])
        _check_refs("relationship type", [t.ref for t in self.relationship_types])
        _check_refs("item type", [t.ref for t in self.item_types])
        _check_refs("item", [i.ref for i in self.items])
        _check_refs("collection", [c.ref for c in self.collections])
        self._check_slugs()
        self._check_links()
        self._check_collections()
        self._check_presets()

    def _check_requires(self) -> None:
        for pack_id in self.requires:
            if not _REF.match(pack_id):
                raise InvalidPackError(f"required pack id '{pack_id}' {_REF_RULE}")
            if pack_id == self.id:
                raise InvalidPackError(f"pack '{self.id}' cannot require itself")
        for pack_id in set(self.requires):
            if self.requires.count(pack_id) > 1:
                raise InvalidPackError(f"requires lists '{pack_id}' more than once")

    def _external(self, ref: str) -> tuple[str, str] | None:
        """Return `(pack id, local ref)` for a prefixed ref, else None."""
        pack_id, local = split_ref(ref)
        if pack_id is None:
            return None
        if pack_id not in self.requires:
            raise InvalidPackError(
                f"ref '{ref}' names pack '{pack_id}', which is not in requires"
            )
        return pack_id, local

    def external_refs(self) -> frozenset[tuple[EntityKind, str, str]]:
        """Return every cross-pack reference as (kind, pack id, local ref)."""
        found: set[tuple[EntityKind, str, str]] = set()

        def add(kind: EntityKind, ref: str) -> None:
            external = self._external(ref)
            if external is not None:
                found.add((kind, *external))

        for item in self.items:
            add(EntityKind.ITEM_TYPE, item.type_ref)
        for c in self.connections:
            add(EntityKind.ITEM, c.source_ref)
            add(EntityKind.ITEM, c.target_ref)
            add(EntityKind.RELATIONSHIP_TYPE, c.type_ref)
        for collection in self.collections:
            for ref in collection.item_refs:
                add(EntityKind.ITEM, ref)
        return frozenset(found)

    def _check_limits(self) -> None:
        limits = (
            ("presets", len(self.presets), MAX_PRESETS),
            ("relationship types", len(self.relationship_types), MAX_TYPES),
            ("item types", len(self.item_types), MAX_TYPES),
            ("items", len(self.items), MAX_ITEMS),
            ("connections", len(self.connections), MAX_CONNECTIONS),
        )
        for name, count, limit in limits:
            if count > limit:
                raise InvalidPackError(f"a pack may hold at most {limit} {name}")

    def _check_slugs(self) -> None:
        for types in (self.relationship_types, self.item_types):
            slugs = [t.slug for t in types]
            if any(slugify(s) != s or s == "" for s in slugs):
                raise InvalidPackError(f"type slugs {_REF_RULE}")
            if len(set(slugs)) != len(slugs):
                raise InvalidPackError("type slugs must be unique within a pack")

    def _check_links(self) -> None:
        item_type_refs = {t.ref for t in self.item_types}
        item_refs = {i.ref for i in self.items}
        relationship_refs = {t.ref for t in self.relationship_types}
        for item in self.items:
            if self._external(item.type_ref) is None and (
                item.type_ref not in item_type_refs
            ):
                raise InvalidPackError(
                    f"item '{item.ref}' has unknown type '{item.type_ref}'"
                )
        for c in self.connections:
            if any(
                self._external(r) is None and r not in item_refs
                for r in (c.source_ref, c.target_ref)
            ):
                raise InvalidPackError(
                    "a connection joins two items that are not in the pack"
                )
            if c.source_ref == c.target_ref:
                raise InvalidPackError("a connection cannot join an item to itself")
            if self._external(c.type_ref) is None and (
                c.type_ref not in relationship_refs
            ):
                raise InvalidPackError(f"connection has unknown type '{c.type_ref}'")

    def _check_collections(self) -> None:
        item_refs = {i.ref for i in self.items}
        for collection in self.collections:
            if not 1 <= len(collection.name.strip()) <= _MAX_COLLECTION_NAME:
                raise InvalidPackError(
                    f"collection '{collection.ref}' needs a name of "
                    + f"1 to {_MAX_COLLECTION_NAME} characters"
                )
            refs = collection.item_refs
            if not refs:
                raise InvalidPackError(f"collection '{collection.ref}' has no items")
            if len(set(refs)) != len(refs):
                raise InvalidPackError(
                    f"collection '{collection.ref}' lists an item twice"
                )
            unknown = [
                r for r in refs if self._external(r) is None and r not in item_refs
            ]
            if unknown:
                raise InvalidPackError(
                    f"collection '{collection.ref}' has unknown item '{unknown[0]}'"
                )

    def _check_presets(self) -> None:
        used: set[str] = set()
        for schema in (
            *(t.attributes_schema for t in self.item_types),
            *(t.attributes_schema for t in self.relationship_types),
        ):
            used |= preset_refs(schema)
        missing = used - {p.ref for p in self.presets}
        if missing:
            raise InvalidPackError(f"unknown preset '{sorted(missing)[0]}'")

    @property
    def counts(self) -> PackCounts:
        """Counts of each section."""
        return PackCounts(
            presets=len(self.presets),
            relationship_types=len(self.relationship_types),
            item_types=len(self.item_types),
            items=len(self.items),
            connections=len(self.connections),
            collections=len(self.collections),
        )


def _defined_refs(pack: ExamplePack) -> dict[EntityKind, set[str]]:
    return {
        EntityKind.ITEM_TYPE: {t.ref for t in pack.item_types},
        EntityKind.RELATIONSHIP_TYPE: {t.ref for t in pack.relationship_types},
        EntityKind.ITEM: {i.ref for i in pack.items},
    }


def _check_cycles(packs: Mapping[str, ExamplePack]) -> None:
    done: set[str] = set()

    def visit(pack_id: str, path: list[str]) -> None:
        if pack_id in path:
            cycle = [*path[path.index(pack_id) :], pack_id]
            raise InvalidPackError(f"pack dependency cycle: {' -> '.join(cycle)}")
        if pack_id in done:
            return
        for required in packs[pack_id].requires:
            visit(required, [*path, pack_id])
        done.add(pack_id)

    for pack_id in packs:
        visit(pack_id, [])


def validate_catalogue(packs: Mapping[str, ExamplePack]) -> None:
    """Check the references between packs.

    Every required pack must be present, requirements must not form a cycle, and
    every cross-pack reference must name something that pack defines, of that kind.

    Raises:
        InvalidPackError: If any check fails.
    """
    for pack in packs.values():
        for required in pack.requires:
            if required not in packs:
                raise InvalidPackError(
                    f"pack {pack.id} requires {required}, which is not available"
                )
    _check_cycles(packs)
    defined = {pack_id: _defined_refs(pack) for pack_id, pack in packs.items()}
    for pack in packs.values():
        for kind, pack_id, ref in sorted(pack.external_refs()):
            if ref not in defined[pack_id][kind]:
                noun = kind.value.replace("_", " ")
                article = "an" if noun[0] == "i" else "a"
                what = f"pack {pack.id} refers to {pack_id}:{ref}"
                raise InvalidPackError(
                    f"{what}, which {pack_id} does not define as {article} {noun}"
                )
