"""Tests for scripts/measure_image_size.py: the Docker image size measurement."""

import gzip
import importlib.util
import json
import subprocess
import sys
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from types import ModuleType

    import pytest

SCRIPT = Path(__file__).resolve().parents[3] / "scripts" / "measure_image_size.py"
PAYLOAD = b"layer data " * 50_000
SAVE_SCRIPT = (
    "import sys; sys.stdout.buffer.write(b'layer data ' * 50000); sys.exit({})"
)


def _load() -> ModuleType:
    spec = importlib.util.spec_from_file_location("measure_image_size", SCRIPT)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules["measure_image_size"] = module
    spec.loader.exec_module(module)
    return module


measure = _load()


def _fake_docker(monkeypatch: pytest.MonkeyPatch, save_code: int = 0) -> None:
    """Stand in for the docker CLI: ``save`` streams PAYLOAD, ``inspect`` answers."""
    real_popen = subprocess.Popen

    def popen(
        args: list[str],
        **kwargs: Any,  # noqa: ANN401
    ) -> subprocess.Popen[bytes]:
        code = SAVE_SCRIPT.format(save_code)
        return real_popen([sys.executable, "-c", code], **kwargs)

    def run(
        args: list[str],
        **_kwargs: Any,  # noqa: ANN401
    ) -> subprocess.CompletedProcess[str]:
        answer = "1234" if "{{.Size}}" in args else "abc123"
        return subprocess.CompletedProcess(args, 0, stdout=answer)

    monkeypatch.setattr(subprocess, "Popen", popen)
    monkeypatch.setattr(subprocess, "run", run)


def test_the_compressed_size_is_that_of_the_gzipped_save(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """It matches what ``docker save | gzip`` would produce."""
    _fake_docker(monkeypatch)

    size = measure.compressed_size("image")

    assert size == len(gzip.compress(PAYLOAD, compresslevel=6, mtime=0))


def test_a_failed_save_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    """A truncated save must not be reported as a size."""
    _fake_docker(monkeypatch, save_code=1)

    try:
        measure.compressed_size("image")
    except subprocess.CalledProcessError:
        return
    raise AssertionError("expected CalledProcessError")


def test_main_prints_the_sizes_and_revision(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """The output is the JSON the comment script reads."""
    _fake_docker(monkeypatch)
    monkeypatch.setattr(sys, "argv", ["measure_image_size.py", "image"])

    assert measure.main() == 0

    sizes = json.loads(capsys.readouterr().out)
    assert sizes["uncompressed"] == 1234
    assert sizes["commit"] == "abc123"
    assert sizes["compressed"] > 0


def test_main_needs_an_image_name(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """Without an image there is nothing to measure."""
    monkeypatch.setattr(sys, "argv", ["measure_image_size.py"])

    assert measure.main() == 2
    assert "usage" in capsys.readouterr().err
