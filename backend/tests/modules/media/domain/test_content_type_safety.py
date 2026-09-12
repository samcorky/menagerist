from app.modules.media.domain.content_type_safety import (
    guessed_type_matches,
    is_inline_safe,
    resolve_trusted_content_type,
)


def test_is_inline_safe() -> None:
    """Verify inline-safety allow-list rules."""
    assert is_inline_safe("image/jpeg") is True
    assert is_inline_safe("image/png") is True
    assert is_inline_safe("audio/mpeg") is True
    assert is_inline_safe("video/mp4") is True
    assert is_inline_safe("application/pdf") is True

    # Unsafe formats
    assert is_inline_safe("image/svg+xml") is False
    assert is_inline_safe("text/html") is False
    assert is_inline_safe("text/xml") is False
    assert is_inline_safe("application/javascript") is False
    assert is_inline_safe("application/octet-stream") is False


def test_guessed_type_matches() -> None:
    """Verify extension to MIME-type heuristic matching."""
    assert guessed_type_matches("photo.jpg", "image/jpeg") is True
    assert guessed_type_matches("document.pdf", "application/pdf") is True
    assert guessed_type_matches("unknown_ext.xyz123", "image/png") is True
    assert guessed_type_matches("photo.jpg", "text/html") is False


def test_resolve_trusted_content_type() -> None:
    """Verify MIME sniffing resolution and downgrade rules."""
    # Safe declared + matching sniff
    assert resolve_trusted_content_type("image/jpeg", "image/jpeg") == "image/jpeg"

    # Safe declared + mismatch sniff -> downgrade to octet-stream
    assert (
        resolve_trusted_content_type("image/jpeg", "application/octet-stream")
        == "application/octet-stream"
    )
    assert (
        resolve_trusted_content_type("image/jpeg", None) == "application/octet-stream"
    )
    assert (
        resolve_trusted_content_type("image/jpeg", "image/png")
        == "application/octet-stream"
    )

    # Non-inline-safe declared is kept as is (handled by is_inline_safe at streaming)
    assert resolve_trusted_content_type("text/html", None) == "text/html"
    assert (
        resolve_trusted_content_type("application/octet-stream", None)
        == "application/octet-stream"
    )
