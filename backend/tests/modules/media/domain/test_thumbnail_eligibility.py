from app.modules.media.domain.thumbnail_eligibility import is_thumbnailable_image


def test_is_thumbnailable_image() -> None:
    """Verify which MIME types are eligible for thumbnail rendering."""
    assert is_thumbnailable_image("image/jpeg") is True
    assert is_thumbnailable_image("image/png") is True
    assert is_thumbnailable_image("image/webp") is True
    assert is_thumbnailable_image("image/gif") is True

    # Ineligible
    assert is_thumbnailable_image("image/svg+xml") is False
    assert is_thumbnailable_image("application/pdf") is False
    assert is_thumbnailable_image("text/plain") is False
    assert is_thumbnailable_image("video/mp4") is False
    assert is_thumbnailable_image("application/octet-stream") is False
