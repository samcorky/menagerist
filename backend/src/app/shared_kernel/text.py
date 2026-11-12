"""Text comparison shared by modules."""

import unicodedata


def fold(text: str) -> str:
    """Casefold `text` and strip combining accents, so `Café` matches `cafe`."""
    decomposed = unicodedata.normalize("NFD", text)
    return "".join(c for c in decomposed if not unicodedata.combining(c)).casefold()
