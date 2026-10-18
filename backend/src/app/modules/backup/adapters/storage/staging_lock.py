import sys
from typing import TYPE_CHECKING, BinaryIO

if TYPE_CHECKING:
    from pathlib import Path

if sys.platform == "win32":
    import msvcrt
else:
    import fcntl


def lock_staging(path: Path) -> BinaryIO | None:
    """Hold an operation lease until its returned handle is closed."""
    stream = path.open("a+b")
    if stream.tell() == 0:
        stream.write(b"0")
        stream.flush()
    stream.seek(0)
    try:
        if sys.platform == "win32":
            msvcrt.locking(stream.fileno(), msvcrt.LK_NBLCK, 1)
        else:
            fcntl.flock(stream.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError:
        stream.close()
        return None
    return stream
