import pytest

from app.shared_kernel.slug import slugify


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("film", "film"),
        ("   film   ", "film"),
        ("Film", "film"),
        ("   Film   ", "film"),
        ("Science Fiction Film", "science-fiction-film"),
        ("sci-fi!!!!", "sci-fi"),
        ("sci--fi", "sci-fi"),
        ("   ", ""),
    ],
)
def test_slugify(value: str, expected: str) -> None:
    """Slugify normalises free text into a lowercase, hyphen-separated slug."""
    assert slugify(value) == expected
