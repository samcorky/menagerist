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


@pytest.mark.parametrize(
    "text", ["", "latest", "nightly", "v", "1..0", "1.0.0+", "1.0.x"]
)
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
    ("spelling", "canonical"),
    [
        ("1.0.0-rc.1", "1.0.0rc1"),
        ("1.0.0_beta2", "1.0.0b2"),
        ("1.0.0alpha", "1.0.0a0"),
        ("1.0.0.preview3", "1.0.0rc3"),
        ("1.0.0.post", "1.0.0.post0"),
        ("1.0.0.dev", "1.0.0.dev0"),
        ("1.0-1", "1.0.post1"),
        ("V1.2", "1.2"),
        (" 1.2 ", "1.2"),
    ],
)
def test_the_usual_spellings_read_as_the_same_version(
    spelling: str, canonical: str
) -> None:
    """Every spelling `packaging` reads is the version it names."""
    assert parse_version(spelling) == parse_version(canonical)
    assert parse_version(spelling) is not None


def test_an_epoch_and_a_local_part_are_read_and_ordered() -> None:
    """`packaging` reads both; a local part sorts after the same version without one."""
    base = parse_version("1.0.0")
    local = parse_version("1.0.0+local")
    next_release = parse_version("1.0.1")
    epoch = parse_version("1!0.1")
    older = parse_version("99.0")
    assert base is not None
    assert local is not None
    assert next_release is not None
    assert epoch is not None
    assert older is not None

    assert base < local < next_release
    assert epoch > older
