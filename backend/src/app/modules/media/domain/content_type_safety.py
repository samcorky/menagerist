import mimetypes

# SVG is excluded because it is scriptable and can execute when rendered inline.
_INLINE_SAFE_PREFIXES = ("image/", "audio/", "video/")
_INLINE_UNSAFE_EXACT = {"image/svg+xml"}
_INLINE_SAFE_EXACT = {"application/pdf"}


def is_inline_safe(content_type: str) -> bool:
    """Determine whether content type may be served inline safely."""
    if content_type in _INLINE_UNSAFE_EXACT:
        return False
    if content_type in _INLINE_SAFE_EXACT:
        return True
    return content_type.startswith(_INLINE_SAFE_PREFIXES)


def guessed_type_matches(filename: str, declared_content_type: str) -> bool:
    """Determine whether filename extension matches declared content type."""
    guessed, _ = mimetypes.guess_type(filename)
    if guessed is None:
        return True
    return guessed == declared_content_type


def resolve_trusted_content_type(declared: str, sniffed: str | None) -> str:
    """Resolve trusted content type based on declared and sniffed MIME types."""
    if not is_inline_safe(declared):
        return declared
    if sniffed != declared:
        return "application/octet-stream"
    return declared
