"""Text comparison shared by modules."""

import unicodedata


def matches_text(q: str | None, *fields: str | None) -> bool:
    """Whether `q` is blank or any field contains it, ignoring case and accents."""
    needle = fold((q or "").strip())
    return not needle or any(needle in fold(field) for field in fields if field)


def fold(text: str) -> str:
    """Casefold `text` and strip combining accents, so `Café` matches `cafe`."""
    decomposed = unicodedata.normalize("NFD", text)
    return "".join(c for c in decomposed if not unicodedata.combining(c)).casefold()
