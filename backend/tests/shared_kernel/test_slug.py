import pytest

from app.shared_kernel.slug import Slug, slugify


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


def test_slug_normalises_value() -> None:
    """Slug stores the normalised (slugified) form of the input."""
    s = Slug("Hello World")
    assert s.value == "hello-world"
    assert str(s) == "hello-world"


@pytest.mark.parametrize("bad", ["", "   "])
def test_slug_raises_on_empty_or_whitespace(bad: str) -> None:
    """Slug rejects empty strings and whitespace-only strings."""
    with pytest.raises(ValueError, match="slug cannot be empty"):
        Slug(bad)


def test_slug_raises_when_empty_after_normalisation() -> None:
    """Slug rejects values that produce an empty string after slugification."""
    with pytest.raises(ValueError, match="slug cannot be empty after normalisation"):
        Slug("!!!!")
