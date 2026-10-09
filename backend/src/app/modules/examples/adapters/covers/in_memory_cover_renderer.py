import base64
import hashlib

from app.modules.examples.domain.pack import COVER_STYLES

# 1x1 PNG, used as the base so the output is always a valid image.
_PNG = base64.b64decode(
    "".join(
        (
            "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR4nGP4z8DwHwAFAAH/",
            "iZk9HQAAAABJRU5ErkJggg==",
        )
    )
)


class InMemoryCoverRenderer:
    """Fake renderer: a tiny valid PNG, deterministic per (name, style)."""

    def render(self, name: str, style: str) -> bytes:
        """Return a tiny PNG whose trailing bytes vary with `name` and `style`."""
        if style not in COVER_STYLES:
            raise ValueError(f"unknown cover style '{style}'")
        # Bytes after IEND are ignored by decoders but make outputs distinct.
        digest = hashlib.sha256(f"{style}\0{name}".encode()).digest()[:8]
        return _PNG + digest
