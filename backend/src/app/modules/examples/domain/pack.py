import re
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

from app.modules.examples.domain.errors import InvalidPackError
from app.shared_kernel.slug import slugify

if TYPE_CHECKING:
    from collections.abc import Mapping

PRESET_MARKER = "$preset"
MAX_PRESETS = 50
MAX_TYPES = 50
MAX_ITEMS = 500
MAX_CONNECTIONS = 2000

_REF = re.compile(r"^[a-z0-9][a-z0-9-]*$")
_REF_RULE = "must be lowercase letters, digits and hyphens"


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
class PackItemType:
    """An item type (a node type) the pack creates."""

    ref: str
    slug: str
    label: str
    description: str | None = None
    attributes_schema: dict[str, Any] | None = None


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
class PackCounts:
    """How many entities of each kind a pack holds, creates, or removed."""

    presets: int = 0
    relationship_types: int = 0
    item_types: int = 0
    items: int = 0
    connections: int = 0


@dataclass(kw_only=True, frozen=True, eq=False)
class PackSummary:
    """A catalogue entry: what the Examples page lists."""

    id: str
    name: str
    description: str
    counts: PackCounts


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

    def __post_init__(self) -> None:
        """Reject a pack whose references do not resolve or that is too large."""
        if not _REF.match(self.id):
            raise InvalidPackError(f"pack id '{self.id}' {_REF_RULE}")
        self._check_limits()
        _check_refs("preset", [p.ref for p in self.presets])
        _check_refs("relationship type", [t.ref for t in self.relationship_types])
        _check_refs("item type", [t.ref for t in self.item_types])
        _check_refs("item", [i.ref for i in self.items])
        self._check_slugs()
        self._check_links()
        self._check_presets()

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
            if item.type_ref not in item_type_refs:
                raise InvalidPackError(
                    f"item '{item.ref}' has unknown type '{item.type_ref}'"
                )
        for c in self.connections:
            if c.source_ref not in item_refs or c.target_ref not in item_refs:
                raise InvalidPackError(
                    "a connection joins two items that are not in the pack"
                )
            if c.source_ref == c.target_ref:
                raise InvalidPackError("a connection cannot join an item to itself")
            if c.type_ref not in relationship_refs:
                raise InvalidPackError(f"connection has unknown type '{c.type_ref}'")

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
        )
