from urllib.parse import unquote

import pytest

from app.modules.media.adapters.api.media.content_disposition import content_disposition


def test_plain_ascii_name_has_no_extended_parameter() -> None:
    """The common case stays the simple form."""
    assert content_disposition("inline", "f.jpg") == 'inline; filename="f.jpg"'


@pytest.mark.parametrize(
    "name",
    [
        "☃ Snow (sleeve).png",
        "映画.png",
        "Łódź 🎵.png",
        'a"b.png',
        "a\\b.png",
        "a\nb.png",
    ],
)
def test_awkward_names_get_a_latin1_safe_fallback_and_utf8_name(name: str) -> None:
    """The header encodes as latin-1, has no breaks or quotes, and keeps the name."""
    header = content_disposition("attachment", name)

    header.encode("latin-1")
    assert "\n" not in header
    fallback = header.split('filename="')[1].split('"')[0]
    assert '"' not in fallback
    assert "\\" not in fallback
    assert unquote(header.split("UTF-8''")[1]) == name


def test_empty_name_falls_back_to_download() -> None:
    """Nothing usable left still gives a name."""
    assert content_disposition("inline", "") == 'inline; filename="download"'


def test_a_very_long_name_is_truncated() -> None:
    """The header stays a sane size."""
    header = content_disposition("inline", "x" * 5000)

    assert len(header) < 300
