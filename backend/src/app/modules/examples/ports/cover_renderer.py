from typing import Protocol


class CoverRenderer(Protocol):
    """Draws a generated cover image for an example item."""

    def render(self, name: str, style: str) -> bytes:
        """Return PNG bytes for `name` in the given cover `style`.

        Raises:
            ValueError: If `style` is not a known cover style.
        """
        ...
