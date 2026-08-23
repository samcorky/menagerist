import re
import unicodedata

_SLUG_INVALID_CHARS = re.compile(r"[^a-z0-9]+")


def slugify(value: str) -> str:
    """Normalise a free-text value into a lowercase, hyphen-separated slug."""
    ascii_value = (
        unicodedata.normalize("NFKD", value).encode("ascii", "ignore").decode("ascii")
    )
    return _SLUG_INVALID_CHARS.sub("-", ascii_value.lower()).strip("-")
