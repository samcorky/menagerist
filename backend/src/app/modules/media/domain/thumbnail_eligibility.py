_NON_THUMBNAILABLE_IMAGE_TYPES = {"image/svg+xml"}


def is_thumbnailable_image(content_type: str) -> bool:
    """Whether a raster thumbnail should be generated for this content type.

    Image-only: audio embedded cover art and video frame extraction are
    explicitly out of scope (no driver for either yet). SVG is excluded —
    it's vector, nothing to raster-decode, and is already forced to
    attachment-only elsewhere due to XSS risk (see content_type_safety.py)
    — never worth opening in an image decoder.

    `content_type` should be the *trusted* (post-sniffing) type — see
    content_type_safety.resolve_trusted_content_type — not the raw,
    unverified client-declared value, otherwise this gate inherits the
    same spoofing problem that motivated adding sniffing in the first
    place.
    """
    return (
        content_type.startswith("image/")
        and content_type not in _NON_THUMBNAILABLE_IMAGE_TYPES
    )
