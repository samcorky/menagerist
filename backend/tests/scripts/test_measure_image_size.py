"""Tests for scripts/measure_image_size.py: the Docker image size measurement."""

import gzip
import importlib.util
import io
import json
import subprocess
import sys
import tarfile
import zlib
from pathlib import Path
from typing import TYPE_CHECKING, Any

import pytest

if TYPE_CHECKING:
    from types import ModuleType

SCRIPT = Path(__file__).resolve().parents[3] / "scripts" / "measure_image_size.py"
LAYER = b"layer data " * 50_000
OTHER = b"another layer " * 20_000


def _load() -> ModuleType:
    spec = importlib.util.spec_from_file_location("measure_image_size", SCRIPT)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules["measure_image_size"] = module
    spec.loader.exec_module(module)
    return module


measure = _load()


def _saved_image(path: Path) -> None:
    """Write a tar like ``docker save``: one gzipped layer, one plain, a directory."""
    with tarfile.open(path, "w") as archive:
        directory = tarfile.TarInfo("blobs")
        directory.type = tarfile.DIRTYPE
        archive.addfile(directory)
        for name, data in (("blobs/gzipped", gzip.compress(LAYER)), ("plain", OTHER)):
            info = tarfile.TarInfo(name)
            info.size = len(data)
            archive.addfile(info, io.BytesIO(data))


def _fake_docker(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, save_code: int = 0
) -> None:
    """Stand in for the docker CLI: ``save`` streams a tar, ``inspect`` answers."""
    saved = tmp_path / "saved.tar"
    _saved_image(saved)
    real_popen = subprocess.Popen

    def popen(
        args: list[str],
        **kwargs: Any,  # noqa: ANN401
    ) -> subprocess.Popen[bytes]:
        code = "; ".join(
            [
                "import sys",
                "sys.stdout.buffer.write(open(sys.argv[1], 'rb').read())",
                f"sys.exit({save_code})",
            ]
        )
        return real_popen([sys.executable, "-c", code, str(saved)], **kwargs)

    def run(
        args: list[str],
        **_kwargs: Any,  # noqa: ANN401
    ) -> subprocess.CompletedProcess[str]:
        return subprocess.CompletedProcess(args, 0, stdout="abc123\n")

    monkeypatch.setattr(subprocess, "Popen", popen)
    monkeypatch.setattr(subprocess, "run", run)


def test_uncompressed_counts_the_unpacked_layers(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """A gzipped layer counts at its unpacked size, a plain one as it is."""
    _fake_docker(monkeypatch, tmp_path)

    _, uncompressed = measure.sizes("image")

    assert uncompressed == len(LAYER) + len(OTHER)


def test_compressed_is_the_unpacked_layers_gzipped_afresh(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """How the image stored its layers does not change the compressed size."""
    _fake_docker(monkeypatch, tmp_path)
    expected = zlib.compressobj(wbits=31)
    size = len(expected.compress(LAYER + OTHER)) + len(expected.flush())

    compressed, _ = measure.sizes("image")

    # zlib may end a block differently depending on how the input is split.
    assert compressed == pytest.approx(size, abs=16)


def test_a_failed_save_raises(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """A truncated save must not be reported as a size."""
    _fake_docker(monkeypatch, tmp_path, save_code=1)

    with pytest.raises(subprocess.CalledProcessError):
        measure.sizes("image")


def test_main_prints_the_sizes_and_revision(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """The output is the JSON the comment script reads."""
    _fake_docker(monkeypatch, tmp_path)
    monkeypatch.setattr(sys, "argv", ["measure_image_size.py", "image"])

    assert measure.main() == 0

    result = json.loads(capsys.readouterr().out)
    assert result["uncompressed"] == len(LAYER) + len(OTHER)
    assert result["commit"] == "abc123"
    assert 0 < result["compressed"] < result["uncompressed"]


def test_main_needs_an_image_name(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """Without an image there is nothing to measure."""
    monkeypatch.setattr(sys, "argv", ["measure_image_size.py"])

    assert measure.main() == 2
    assert "usage" in capsys.readouterr().err
