from typing import TYPE_CHECKING

from app.modules.transfer.domain.errors import UnknownFormatError

if TYPE_CHECKING:
    from collections.abc import Iterable

    from app.modules.transfer.ports.codec import BundleCodec


class CodecRegistry:
    """The file formats this server reads and writes, by format id.

    Filled once at the composition root; adding a format is adding a codec.
    """

    def __init__(self, codecs: Iterable[BundleCodec]) -> None:
        """Register `codecs`; two with one format id is a programming error."""
        self._codecs: dict[str, BundleCodec] = {}
        for codec in codecs:
            if codec.format in self._codecs:
                msg = f"two codecs for format '{codec.format}'"
                raise ValueError(msg)
            self._codecs[codec.format] = codec

    @property
    def formats(self) -> tuple[str, ...]:
        """The format ids registered, sorted."""
        return tuple(sorted(self._codecs))

    def get(self, format_id: object) -> BundleCodec:
        """Return the codec for `format_id`.

        Raises:
            UnknownFormatError: no codec reads or writes it.
        """
        codec = self._codecs.get(format_id) if isinstance(format_id, str) else None
        if codec is None:
            names = ", ".join(f"'{f}'" for f in self.formats)
            raise UnknownFormatError(f"format must be one of {names}")
        return codec
