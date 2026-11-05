#!/usr/bin/env python3
"""Print the size of a local Docker image as JSON.

The output is ``{"compressed", "uncompressed", "commit"}``, sizes in bytes. Compressed
is the saved image gzipped, an estimate of the pull size that is measured the same way
for the pull request's image and the published ``edge`` one, so the two compare.
Commit is the image's revision label, empty when it has none. It uses only the standard
library and the ``docker`` CLI, so it runs on any platform the CLI does.
"""

import json
import subprocess
import sys
import zlib

CHUNK = 1024 * 1024
GZIP_WINDOW = 31  # zlib wbits for a gzip stream, as `gzip` writes
REVISION_LABEL = "org.opencontainers.image.revision"


def _inspect(image: str, template: str) -> str:
    result = subprocess.run(
        ["docker", "image", "inspect", image, "--format", template],
        capture_output=True,
        check=True,
        text=True,
    )
    return result.stdout.strip()


def compressed_size(image: str) -> int:
    """Return the gzipped size of ``docker save`` without holding it in memory."""
    compressor = zlib.compressobj(wbits=GZIP_WINDOW)
    total = 0
    with subprocess.Popen(["docker", "save", image], stdout=subprocess.PIPE) as save:
        assert save.stdout is not None
        while chunk := save.stdout.read(CHUNK):
            total += len(compressor.compress(chunk))
        total += len(compressor.flush())
    if save.returncode:
        raise subprocess.CalledProcessError(save.returncode, save.args)
    return total


def measure(image: str) -> dict[str, int | str]:
    """Return the sizes and revision of ``image``."""
    return {
        "compressed": compressed_size(image),
        "uncompressed": int(_inspect(image, "{{.Size}}")),
        "commit": _inspect(image, f'{{{{index .Config.Labels "{REVISION_LABEL}"}}}}'),
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
