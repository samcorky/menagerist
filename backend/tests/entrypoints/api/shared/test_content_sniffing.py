from typing import TYPE_CHECKING

from app.entrypoints.api.shared.content_sniffing import sniff_and_rechain

if TYPE_CHECKING:
    from collections.abc import AsyncIterator


async def _stream(*chunks: bytes) -> AsyncIterator[bytes]:
    for chunk in chunks:
        yield chunk


async def test_sniff_and_rechain_detects_jpeg() -> None:
    """Sniffing identifies JPEG magic header while preserving the stream untouched."""
    jpeg_header = (
        bytes.fromhex(
            "ffd8ffe000104a46494600010101004800480000ffdb00430008060607060508070707"
        )
        + b"\x00" * 300
    )
    sniffed, full_stream = await sniff_and_rechain(
        _stream(jpeg_header[:50], jpeg_header[50:])
    )

    assert sniffed == "image/jpeg"
    reconstructed = b""
    async for chunk in full_stream:
        reconstructed += chunk
    assert reconstructed == jpeg_header


async def test_sniff_and_rechain_empty_or_text() -> None:
    """Sniffing returns None on plain text while preserving the stream."""
    text_data = b"plain text data without magic bytes"
    sniffed, full_stream = await sniff_and_rechain(_stream(text_data))

    assert sniffed is None
    reconstructed = b""
    async for chunk in full_stream:
        reconstructed += chunk
    assert reconstructed == text_data
