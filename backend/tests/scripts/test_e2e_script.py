"""Tests for scripts/e2e.py: the --shard argument handed to Playwright."""

import importlib.util
import sys
from pathlib import Path
from typing import TYPE_CHECKING

import pytest

if TYPE_CHECKING:
    from types import ModuleType

SCRIPT = Path(__file__).resolve().parents[3] / "scripts" / "e2e.py"


def _load() -> ModuleType:
    spec = importlib.util.spec_from_file_location("e2e_script", SCRIPT)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules["e2e_script"] = module
    spec.loader.exec_module(module)
    return module


e2e = _load()


def test_no_shard_adds_no_argument() -> None:
    """Without a shard the whole suite runs."""
    assert e2e.shard_args(None) == []


@pytest.mark.parametrize("shard", ["1/1", "2/3", "3/3", "10/12"])
def test_a_valid_shard_becomes_the_playwright_flag(shard: str) -> None:
    """CURRENT/TOTAL is passed to Playwright unchanged."""
    assert e2e.shard_args(shard) == [f"--shard={shard}"]


@pytest.mark.parametrize(
    "shard", ["", "2", "0/3", "2/0", "4/3", "a/b", "1/2/3", "1/3 --x", "-1/3", "1.5/3"]
)
def test_a_malformed_shard_is_refused(shard: str) -> None:
    """Anything but CURRENT/TOTAL, with CURRENT at most TOTAL, stops the run."""
    with pytest.raises(SystemExit):
        e2e.shard_args(shard)


def test_setup_regenerates_the_client_first_by_default() -> None:
    """A local run refreshes the API client before anything else."""
    steps = e2e.setup_steps(skip_build=False, skip_generate=False)
    assert steps == [
        "generate-frontend-client",
        "sync-backend",
        "e2e-db-up",
        "e2e-build",
        "e2e-migrate",
    ]


def test_setup_can_skip_the_client_and_the_build() -> None:
    """CI reuses the client from sync-ci, and --skip-build reuses the build."""
    steps = e2e.setup_steps(skip_build=True, skip_generate=True)
    assert steps == ["sync-backend", "e2e-db-up", "e2e-migrate"]
