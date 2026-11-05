#!/usr/bin/env python3
"""Print the size of a local Docker image as JSON.

The output is ``{"compressed", "uncompressed", "commit"}``, sizes in bytes. Uncompressed
is the size of the saved image with its layers unpacked and compressed is that gzipped,
an estimate of the pull size. Both are measured the same way for the pull request's
image and the published ``edge`` one, whichever Docker image store holds them.
Commit is the image's revision label, empty when it has none. It uses only the standard
library and the ``docker`` CLI, so it runs on any platform the CLI does.
"""

import json
import subprocess
import sys
import tarfile
import zlib
from typing import IO, TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Iterator

CHUNK = 1024 * 1024
GZIP_WINDOW = 31  # zlib wbits for a gzip stream, as `gzip` writes
GZIP_MAGIC = bytes([0x1F, 0x8B])
REVISION_LABEL = "org.opencontainers.image.revision"


def _revision(image: str) -> str:
    result = subprocess.run(
        [
            "docker",
            "image",
            "inspect",
            image,
            "--format",
            f'{{{{index .Config.Labels "{REVISION_LABEL}"}}}}',
        ],
        capture_output=True,
        check=True,
        text=True,
    )
    return result.stdout.strip()


def _chunks(source: IO[bytes]) -> Iterator[bytes]:
    """Yield a saved file's content, unzipped when the image stored it gzipped."""
    first = source.read(CHUNK)
    if not first.startswith(GZIP_MAGIC):
        chunk = first
        while chunk:
            yield chunk
            chunk = source.read(CHUNK)
        return
    inflater = zlib.decompressobj(wbits=GZIP_WINDOW)
    chunk = first
    while chunk:
        yield inflater.decompress(chunk)
        chunk = source.read(CHUNK)
    yield inflater.flush()


def sizes(image: str) -> tuple[int, int]:
    """Return the image's ``(compressed, uncompressed)`` size in bytes.

    ``docker save`` stores layers gzipped or not depending on the image store and on
    where the image came from, and ``docker image inspect`` reports whichever it holds.
    Unpacking every file and gzipping it afresh gives the same answer for any of them.
    """
    compressor = zlib.compressobj(wbits=GZIP_WINDOW)
    compressed = uncompressed = 0
    with subprocess.Popen(["docker", "save", image], stdout=subprocess.PIPE) as save:
        assert save.stdout is not None
        with tarfile.open(fileobj=save.stdout, mode="r|") as archive:
            for member in archive:
                source = archive.extractfile(member) if member.isfile() else None
                if source is None:
                    continue
                for chunk in _chunks(source):
                    uncompressed += len(chunk)
                    compressed += len(compressor.compress(chunk))
        while save.stdout.read(CHUNK):  # the tar's padding, so docker can finish
            pass
    compressed += len(compressor.flush())
    if save.returncode:
        raise subprocess.CalledProcessError(save.returncode, save.args)
    return compressed, uncompressed


def measure(image: str) -> dict[str, int | str]:
    """Return the sizes and revision of ``image``."""
    compressed, uncompressed = sizes(image)
    return {
        "compressed": compressed,
        "uncompressed": uncompressed,
        "commit": _revision(image),
    }


def main() -> int:
    """Measure the image named on the command line and print the JSON."""
    if len(sys.argv) != 2:
        print("usage: measure_image_size.py IMAGE", file=sys.stderr)
        return 2
    print(json.dumps(measure(sys.argv[1])))
    return 0


if __name__ == "__main__":
    sys.exit(main())
