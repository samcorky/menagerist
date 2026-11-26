import re
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any, Final

from app.shared_kernel.errors import ValidationError
from app.shared_kernel.mixins import Identifiable, Owned, SoftDeletable
from app.shared_kernel.slug import Slug, slugify

# A fixed palette of theme-aware names rather than free colours, so every client can
# render them with the right contrast in light and dark mode.
TYPE_COLOURS: Final = (
    "gray",
    "red",
    "orange",
    "amber",
    "green",
    "teal",
    "blue",
    "violet",
    "pink",
)
MAX_ICON_LENGTH: Final = 64
# Only the shape is checked: the backend does not know which Lucide icons exist.
_ICON_NAME = re.compile(r"[a-z][a-z0-9]*(?:-[a-z0-9]+)*")


_ICON_MESSAGE: Final = (
    "icon must be a Lucide icon name in lower-case words joined by "
    + f"dashes, such as 'film' (at most {MAX_ICON_LENGTH} characters)"
)
_COLOUR_MESSAGE: Final = f"colour must be one of: {', '.join(TYPE_COLOURS)}"


def _clean_icon(icon: str | None) -> str | None:
    """Return a valid Lucide icon name, or `None` for a blank one."""
    if icon is None or not icon.strip():
        return None
    name = icon.strip()
    if len(name) > MAX_ICON_LENGTH or not _ICON_NAME.fullmatch(name):
        raise ValidationError(_ICON_MESSAGE)
    return name


def _clean_parent(parent: str, *, own_slug: str) -> str:
    """Return the parent's slug, or raise if it names nothing or the type itself."""
    slug = slugify(parent)
    if not slug:
        raise ValidationError("parent must name a type")
    if slug == own_slug:
        raise ValidationError("a type cannot be its own parent")
    return slug


def _clean_colour(colour: str | None) -> str | None:
    """Return a palette colour, or `None` for a blank one."""
    if colour is None or not colour.strip():
        return None
    name = colour.strip()
    if name not in TYPE_COLOURS:
        raise ValidationError(_COLOUR_MESSAGE)
    return name


@dataclass(kw_only=True, eq=False)
class NodeType(Identifiable, Owned, SoftDeletable):
    """A controlled vocabulary entry for the node type field, owned by one person."""

    slug: Slug
    label: str
    description: str | None = None
    attributes_schema: dict[str, Any] | None = None
    icon: str | None = None
    colour: str | None = None
    parent: str | None = None
    # Derived on read and never stored: the fields a subtype uses once its parent's
    # join its own (`attributes_schema` stays what the type itself defines), and when
    # the parent last changed, so a response's ETag follows a change to it.
    effective_schema: dict[str, Any] | None = field(default=None, repr=False)
    parent_updated_at: datetime | None = field(default=None, repr=False)

    def __post_init__(self) -> None:
        """Validate required fields after dataclass initialisation."""
        if not self.label or not self.label.strip():
            raise ValidationError("label must be provided")
        self.icon = _clean_icon(self.icon)
        self.colour = _clean_colour(self.colour)
        if self.parent is not None:
            self.parent = _clean_parent(self.parent, own_slug=str(self.slug))

    @classmethod
    def create(
        cls,
        *,
        owner_id: uuid.UUID,
        slug: str,
        label: str,
        description: str | None = None,
        attributes_schema: dict[str, Any] | None = None,
        icon: str | None = None,
        colour: str | None = None,
        parent: str | None = None,
    ) -> NodeType:
        """Create a new NodeType, generating its id and timestamps.

        `parent` is the slug of the type this is a subtype of; the domain checks only
        that it names something other than the type itself, and the use cases check
        the rest, which needs the other types.
        """
        now = datetime.now(UTC)
        return cls(
            id=uuid.uuid7(),
            owner_id=owner_id,
            slug=Slug(slug),
            label=label,
            description=description,
            attributes_schema=attributes_schema,
            icon=icon,
            colour=colour,
            parent=parent,
            created_at=now,
            updated_at=now,
        )

    def update(
        self,
        *,
        label: str | None = None,
        description: str | None = None,
        attributes_schema: dict[str, Any] | None = None,
        icon: str | None = None,
        colour: str | None = None,
        parent: str | None = None,
    ) -> None:
        """Apply partial changes to editable fields. Slug is immutable.

        `None` leaves a field unchanged. An `icon` or `colour` is replaced by a
        valid value; a blank one is an error, and `clear_icon` / `clear_colour`
        remove them. A `parent` replaces the parent (`clear_parent` removes it).
        """
        new_parent = (
            None if parent is None else _clean_parent(parent, own_slug=str(self.slug))
        )
        if label is not None:
            if not label.strip():
                raise ValidationError("label must be provided")
            self.label = label
        if description is not None:
            self.description = description
        if attributes_schema is not None:
            self.attributes_schema = attributes_schema
        self._set_appearance(icon=icon, colour=colour)
        if new_parent is not None:
            self.parent = new_parent
        self.touch()

    def _set_appearance(self, *, icon: str | None, colour: str | None) -> None:
        """Replace the icon and colour that are given; a blank one is an error.

        Both are checked before either changes, so a bad value changes nothing.
        """
        new_icon = _clean_icon(icon)
        new_colour = _clean_colour(colour)
        if icon is not None and new_icon is None:
            raise ValidationError(_ICON_MESSAGE)
        if colour is not None and new_colour is None:
            raise ValidationError(_COLOUR_MESSAGE)
        if new_icon is not None:
            self.icon = new_icon
        if new_colour is not None:
            self.colour = new_colour

    def clear_icon(self) -> None:
        """Remove the icon."""
        self.icon = None
        self.touch()

    def clear_colour(self) -> None:
        """Remove the colour."""
        self.colour = None
        self.touch()

    def clear_parent(self) -> None:
        """Make the type top-level again."""
        self.parent = None
        self.touch()
