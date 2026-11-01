import re
import unicodedata
from dataclasses import dataclass

_SLUG_INVALID_CHARS = re.compile(r"[^a-z0-9]+")


def slugify(value: str) -> str:
    """Normalise a free-text value into a lowercase, hyphen-separated slug."""
    ascii_value = (
        unicodedata.normalize("NFKD", value).encode("ascii", "ignore").decode("ascii")
    )
    return _SLUG_INVALID_CHARS.sub("-", ascii_value.lower()).strip("-")


@dataclass(frozen=True)
class Slug:
    """Immutable, normalised slug value object."""

    value: str

    def __post_init__(self) -> None:
        """Validate and normalise the slug value."""
        if not self.value or not self.value.strip():
            raise ValueError("slug cannot be empty")
        object.__setattr__(self, "value", slugify(self.value))
        if not self.value:
            raise ValueError("slug cannot be empty after normalisation")

    def __str__(self) -> str:
        """Return the slug value as a plain string."""
        return self.value
