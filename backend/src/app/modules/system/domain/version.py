"""Release version ordering, which is `packaging`'s own.

The versions this project publishes and reports (`0.2026.11.2`, `0.2026.11.3.dev62`) are
written by `packaging`, through `calver-scm` and `setuptools-scm`, so they are read and
ordered by it too. A tag that is not a version is not one here either, and release
selection skips it instead of comparing it as text.
"""

from packaging.version import InvalidVersion, Version

__all__ = ["Version", "parse_version"]


def parse_version(text: str) -> Version | None:
    """Read a tag such as `v0.2026.11.0` or `0.2026.12.0rc1`, else `None`."""
    try:
        return Version(text)
    except InvalidVersion:
        return None
