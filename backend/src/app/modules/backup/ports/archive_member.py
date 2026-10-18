from collections.abc import AsyncIterator
from dataclasses import dataclass


@dataclass(frozen=True, kw_only=True)
class ArchiveMember:
    """Named uncompressed byte stream, consumed before the next member."""

    name: str
    chunks: AsyncIterator[bytes]
