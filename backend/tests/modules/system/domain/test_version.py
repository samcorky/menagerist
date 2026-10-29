from itertools import pairwise

import pytest

from app.modules.system.domain.version import parse_version

# Written lowest to highest; PEP 440 puts a development build of a release before its
# alpha, and a post-release after the final.
ORDERED = [
    "0.2026.10.0.dev1",
    "0.2026.10.0a1",
    "0.2026.10.0b2",
    "0.2026.10.0rc1",
    "0.2026.10.0",
    "0.2026.10.0.post1",
    "0.2026.10.1.dev3",
    "0.2026.10.1",
    "0.2026.11.0",
    "1.0.0",
    "1.2.0",
    "1.10.0",
]


def test_versions_order_as_pep_440_does() -> None:
    """Each version sorts after the one before it."""
    parsed = [parse_version(text) for text in ORDERED]

    assert None not in parsed
    for lower, higher in pairwise(parsed):
        assert lower is not None
        assert higher is not None
        assert lower < higher
        assert higher > lower
        assert lower != higher


def test_trailing_zeros_and_a_leading_v_do_not_change_a_version() -> None:
    """`v1.0` and `1.0.0` are the same release."""
    assert parse_version("v1.0") == parse_version("1.0.0")
    assert hash(parse_version("1.0")) == hash(parse_version("1.0.0.0"))
    assert parse_version("1.0") != "1.0"


@pytest.mark.parametrize("text", ["", "latest", "nightly", "1.0.0+local", "v", "1..0"])
def test_a_tag_that_is_not_a_version_is_refused(text: str) -> None:
    """Such a tag is skipped by release selection."""
    assert parse_version(text) is None


def test_the_kind_of_build_is_reported() -> None:
    """Pre-release and development builds are told apart from finals."""
    final = parse_version("1.0.0")
    candidate = parse_version("1.0.0rc1")
    dev = parse_version("1.0.0.dev2")
    assert final is not None
    assert candidate is not None
    assert dev is not None

    assert not final.is_prerelease
    assert not final.is_devrelease
    assert candidate.is_prerelease
    assert dev.is_devrelease


@pytest.mark.parametrize(
    "text",
    [
        "1.0.0-rc.1",
        "1.0.0_beta2",
        "1.0.0alpha",
        "1.0.0.preview3",
        "1.0.0.post",
        "1.0.0.dev",
        "V1.2",
    ],
)
def test_the_usual_spellings_read_as_packaging_reads_them(text: str) -> None:
    """Agree with `packaging` on how every spelling orders against a neighbour."""
    packaging = pytest.importorskip("packaging.version")
    mine = parse_version(text)
    assert mine is not None
    for other in ORDERED:
        theirs = packaging.Version(other)
        reference = packaging.Version(text.lstrip("vV"))
        ours = parse_version(other)
        assert ours is not None
        assert (mine < ours) == (reference < theirs), (text, other)
        assert (mine > ours) == (reference > theirs), (text, other)
