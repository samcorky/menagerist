import os
from typing import TYPE_CHECKING

import pytest

from app.platform.storage_probe import DirectoryState, hint, probe_directory

if TYPE_CHECKING:
    from pathlib import Path


def test_probe_reports_writable_directory_and_removes_probe_file(
    tmp_path: Path,
) -> None:
    """A successful probe writes and removes its temporary root-level file."""
    result = probe_directory(tmp_path)

    assert result.state == "writable"
    assert result.free_bytes is not None
    assert list(tmp_path.glob(".menagerist-write-test-*")) == []


def test_probe_reports_missing_directory(tmp_path: Path) -> None:
    """A path that is not a directory is reported as missing."""
    result = probe_directory(tmp_path / "missing")

    assert result.state == "missing"
    assert result.free_bytes is None


@pytest.mark.skipif(
    os.name != "posix" or getattr(os, "geteuid", lambda: 0)() == 0,
    reason="root or non-POSIX filesystems may ignore chmod permissions",
)
def test_probe_reports_directory_without_write_permission(tmp_path: Path) -> None:
    """The real write probe detects a directory without write permission."""
    tmp_path.chmod(0o555)
    try:
        result = probe_directory(tmp_path)
    finally:
        tmp_path.chmod(0o755)

    assert result.state == "not-writable"
    assert result.free_bytes is not None
    assert list(tmp_path.glob(".menagerist-write-test-*")) == []


@pytest.mark.parametrize(
    ("state", "expected"),
    [
        (
            "not-writable",
            "For a bind mount, run: chown 1000:1000 <host directory>.",
        ),
        ("missing", "Mount a volume or directory there."),
        ("writable", None),
    ],
)
def test_hint_matches_directory_state(
    tmp_path: Path, state: DirectoryState, expected: str | None
) -> None:
    """Hints explain the appropriate operator action for each state."""
    message = hint(tmp_path, state)

    if expected is None:
        assert message is None
    else:
        assert message is not None
        assert str(tmp_path) in message
        assert expected in message
