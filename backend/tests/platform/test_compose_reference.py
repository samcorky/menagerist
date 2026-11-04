"""The Compose variables in the generated reference follow the Compose files."""

from pathlib import Path

import pytest

from app.platform.config import ALL_SETTINGS
from app.platform.config._compose import (
    COMPOSE_FILES,
    DESCRIPTIONS,
    compose_defaults,
    read_compose_files,
)
from app.platform.config._reference import IMAGE_VALUES, build_sections, reference_files

REPO = Path(__file__).resolve().parents[3]
FULL = {
    "compose.yaml": "".join(f"x: ${{{name}:-1}}\n" for name in DESCRIPTIONS),
}


def test_every_variable_in_the_real_compose_files_is_described() -> None:
    """Adding a `${VAR}` to a Compose file fails here until it has a description."""
    texts = read_compose_files(REPO)
    # The override is git-ignored (a local development file), so CI has only the first.
    assert "compose.yaml" in texts
    assert set(texts) <= set(COMPOSE_FILES)
    assert set(compose_defaults(texts)) == set(DESCRIPTIONS)
    assert reference_files(ALL_SETTINGS, texts)


def test_the_compose_section_lists_names_defaults_and_descriptions() -> None:
    """The section is built from the files: names in file order, defaults as written."""
    section = build_sections(ALL_SETTINGS, read_compose_files(REPO))[-1]
    assert section.group == "compose"
    entries = {e.env_name: e for e in section.entries}
    assert list(entries) == list(DESCRIPTIONS)
    assert entries["POSTGRES_MEM_LIMIT"].default == "512m"
    assert entries["MENAGERIST_IMAGE"].default == "ghcr.io/samcorky/menagerist:latest"
    assert entries["POSTGRES_WORK_MEM"].description == DESCRIPTIONS["POSTGRES_WORK_MEM"]


def test_a_variable_without_a_description_fails_generation() -> None:
    """A new `${VAR}` cannot reach the docs undescribed."""
    texts = {"compose.yaml": FULL["compose.yaml"] + "y: ${NEW_THING:-2}\n"}
    with pytest.raises(ValueError, match="no description for NEW_THING"):
        build_sections([], texts)


def test_a_description_for_a_removed_variable_fails_generation() -> None:
    """Deleting a `${VAR}` from the files leaves a stale description to remove."""
    texts = {"compose.yaml": FULL["compose.yaml"].replace("POSTGRES_WORK_MEM", "X")}
    with pytest.raises(ValueError, match="described but not in a Compose file"):
        build_sections([], {"compose.yaml": texts["compose.yaml"]})


def test_the_first_file_with_a_default_wins_and_no_default_is_none() -> None:
    """`compose.yaml` outranks the override; `${VAR}` and `${VAR-x}` are handled."""
    texts = {
        "compose.yaml": "a: ${ONE:-from-main}\nb: ${TWO}\nc: ${THREE-three}\n",
        "compose.override.yml": "a: ${ONE:-from-override}\nb: ${TWO:-two}\n",
    }
    assert compose_defaults(texts) == {
        "ONE": "from-main",
        "TWO": "two",
        "THREE": "three",
    }


def test_the_dockerfile_still_sets_the_values_the_header_says_it_does() -> None:
    """The generated note about the image must match the final stage's `ENV`."""
    dockerfile = (REPO / "Dockerfile").read_text(encoding="utf-8")
    for name, value in IMAGE_VALUES.items():
        assert f"{name}={value}" in dockerfile
