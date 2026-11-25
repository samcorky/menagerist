import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any, Final, Literal

from app.shared_kernel.errors import ValidationError
from app.shared_kernel.mixins import Identifiable, Owned, SoftDeletable
from app.shared_kernel.slug import Slug, slugify

if TYPE_CHECKING:
    from collections.abc import Iterable

type Holder = Literal["source", "target", "none"]
HOLDERS: Final[tuple[Holder, ...]] = ("source", "target", "none")


def _clean_optional(slugs: Iterable[str] | None) -> tuple[str, ...] | None:
    return None if slugs is None else _clean_item_types(slugs)


def _within(allowed: tuple[str, ...], item_type: str | None) -> bool:
    return not allowed or (item_type is not None and item_type in allowed)


def _check_holder(holder: str, *, directional: bool) -> None:
    if holder not in HOLDERS:
        raise ValidationError(f"holder must be one of: {', '.join(HOLDERS)}")
    if holder != "none" and not directional:
        raise ValidationError("A connection with no direction cannot hold items")


MAX_ITEM_TYPES: Final = 50


def _clean_item_types(slugs: Iterable[str]) -> tuple[str, ...]:
    """Slugify, drop repeats (keeping order) and bound a list of item types."""
    cleaned: dict[str, None] = {}
    for raw in slugs:
        slug = slugify(raw)
        if not slug:
            raise ValidationError("an item type in a limit must not be blank")
        cleaned[slug] = None
    if len(cleaned) > MAX_ITEM_TYPES:
        raise ValidationError(f"a limit takes at most {MAX_ITEM_TYPES} item types")
    return tuple(cleaned)


@dataclass(kw_only=True, eq=False)
class EdgeType(Identifiable, Owned, SoftDeletable):
    """A controlled vocabulary entry for edge relationships, owned by one person.

    `holder` says which end of a connection holds the other, for an item's
    contents and path: `source` for "Contains" (the box is the source), `target`
    for "Located in" (the box is the target), `none` when neither holds the
    other ("Published by"). Only a relationship with a direction can hold.
    """

    slug: Slug
    label: str
    reverse_label: str | None = None
    description: str | None = None
    directional: bool = True
    attributes_schema: dict[str, Any] | None = None
    holder: Holder = "none"
    source_types: tuple[str, ...] = ()
    target_types: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        """Validate required fields after dataclass initialisation."""
        if not self.label or not self.label.strip():
            raise ValidationError("label must be provided")
        _check_holder(self.holder, directional=self.directional)
        self.source_types = _clean_item_types(self.source_types)
        self.target_types = _clean_item_types(self.target_types)

    def fits(self, *, source_type: str | None, target_type: str | None) -> bool:
        """Whether items of these types may be joined by this connection type.

        An empty limit allows any item, untyped ones included; a non-empty one
        allows only the listed types, so an untyped item never satisfies it.
        """
        return _within(self.source_types, source_type) and _within(
            self.target_types, target_type
        )

    @classmethod
    def create(
        cls,
        *,
        owner_id: uuid.UUID,
        slug: str,
        label: str,
        reverse_label: str | None = None,
        description: str | None = None,
        directional: bool = True,
        attributes_schema: dict[str, Any] | None = None,
        holder: Holder = "none",
        source_types: Iterable[str] = (),
        target_types: Iterable[str] = (),
    ) -> EdgeType:
        """Create a new EdgeType, generating its id and timestamps."""
        now = datetime.now(UTC)
        return cls(
            id=uuid.uuid7(),
            owner_id=owner_id,
            slug=Slug(slug),
            label=label,
            reverse_label=reverse_label,
            description=description,
            directional=directional,
            attributes_schema=attributes_schema,
            holder=holder,
            source_types=tuple(source_types),
            target_types=tuple(target_types),
            created_at=now,
            updated_at=now,
        )

    def update(
        self,
        *,
        label: str | None = None,
        reverse_label: str | None = None,
        description: str | None = None,
        directional: bool | None = None,
        attributes_schema: dict[str, Any] | None = None,
        holder: Holder | None = None,
        source_types: Iterable[str] | None = None,
        target_types: Iterable[str] | None = None,
    ) -> None:
        """Apply partial changes. Slug is immutable.

        An empty `source_types` or `target_types` removes that limit.

        Raises:
            ValidationError: For a blank label, a holder on a connection
                with no direction, or a blank or too long list of item types.
        """
        new_source = _clean_optional(source_types)
        new_target = _clean_optional(target_types)
        _check_holder(
            self.holder if holder is None else holder,
            directional=self.directional if directional is None else directional,
        )
        if label is not None:
            if not label.strip():
                raise ValidationError("label must be provided")
            self.label = label
        if reverse_label is not None:
            self.reverse_label = reverse_label
        if description is not None:
            self.description = description
        if directional is not None:
            self.directional = directional
        if attributes_schema is not None:
            self.attributes_schema = attributes_schema
        if holder is not None:
            self.holder = holder
        self.source_types = self.source_types if new_source is None else new_source
        self.target_types = self.target_types if new_target is None else new_target
        self.touch()
