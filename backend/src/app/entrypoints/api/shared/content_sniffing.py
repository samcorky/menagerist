from typing import TYPE_CHECKING

import filetype  # type: ignore[import-untyped]

if TYPE_CHECKING:
    from collections.abc import AsyncGenerator, AsyncIterator


async def sniff_and_rechain(
    stream: AsyncIterator[bytes],
) -> tuple[str | None, AsyncIterator[bytes]]:
    """Peek the first chunk of an upload stream to identify its MIME type.

    Returns:
        Tuple of sniffed MIME type (or None) and the unconsumed stream.
    """
    first_chunk = b""
    async for chunk in stream:
        first_chunk = chunk
        break

    kind = filetype.guess(first_chunk)
    sniffed_content_type = kind.mime if kind else None

    async def _rechained() -> AsyncGenerator[bytes]:
        if first_chunk:
            yield first_chunk
        async for chunk in stream:
            yield chunk

    return sniffed_content_type, _rechained()
