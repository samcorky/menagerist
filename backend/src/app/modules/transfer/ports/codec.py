from collections.abc import Mapping  # noqa: TC003
from typing import Any, Protocol

from app.modules.transfer.domain.bundle import Bundle  # noqa: TC001


class BundleCodec(Protocol):
    """Reads one file format into a `Bundle`, and writes a `Bundle` in it."""

    @property
    def format(self) -> str:
        """The format id a file names in its `format` field."""
        ...

    def decode(self, data: Mapping[str, Any]) -> Bundle:
        """Read a parsed file into a bundle.

        Raises:
            InvalidBundleError: the file is not valid in this format.
        """
        ...

    def encode(self, bundle: Bundle) -> dict[str, Any]:
        """Write a bundle as a file in this format, ready to serialise as JSON."""
        ...
