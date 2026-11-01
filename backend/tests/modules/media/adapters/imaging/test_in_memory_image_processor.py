from app.modules.media.adapters.imaging.in_memory_image_processor import (
    InMemoryImageProcessor,
)


def test_in_memory_image_processor_success() -> None:
    """InMemoryImageProcessor generates fake thumbnail result."""
    proc = InMemoryImageProcessor(fake_thumbnail_bytes=b"fake-bytes")
    res = proc.generate_thumbnail(b"anything", max_dimension=200)
    assert res is not None
    assert res.data == b"fake-bytes"
    assert res.width == 200
    assert res.height == 200


def test_in_memory_image_processor_disabled() -> None:
    """InMemoryImageProcessor can simulate failure or empty input."""
    proc = InMemoryImageProcessor(generate_result=False)
    assert proc.generate_thumbnail(b"anything") is None
    proc2 = InMemoryImageProcessor(generate_result=True)
    assert proc2.generate_thumbnail(b"") is None
