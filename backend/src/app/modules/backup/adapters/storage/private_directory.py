"""Check that a staging folder is a real directory only this user can reach."""

import os
import stat
import sys
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from pathlib import Path


def require_private_directory(path: Path) -> None:
    """Raise `OSError` unless `path` is a real, private directory.

    It matters when the folder sits in a shared directory such as /tmp, where another
    user could pre-create the name as a symlink, a Windows junction or a directory
    they own. A link is refused without being followed.
    """
    status = path.lstat()
    reparse = getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0)
    attributes = getattr(status, "st_file_attributes", 0)
    if not stat.S_ISDIR(status.st_mode) or attributes & reparse:
        raise OSError("Staging path is not a real directory.")
    if sys.platform != "win32" and (
        status.st_uid != os.getuid() or status.st_mode & 0o077
    ):
        raise OSError("Staging path is not private to this user.")
