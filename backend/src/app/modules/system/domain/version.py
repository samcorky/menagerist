"""Release version ordering, for the CalVer tags this project publishes.

A small reading of PEP 440: a dotted release number with an optional pre-release
(`a`, `b`, `rc`), post-release and development part. A tag that does not fit is not a
version here, so it is skipped rather than compared as text.
"""

import re
from dataclasses import dataclass

_VERSION = re.compile(
    r"v?(?P<release>\d+(?:\.\d+)*)"
    + r"(?:[-_.]?(?P<pre_label>a|alpha|b|beta|c|rc|pre|preview)[-_.]?(?P<pre_n>\d*))?"
    + r"(?:[-_.]?(?:post|rev|r)[-_.]?(?P<post_n>\d*))?"
    + r"(?:[-_.]?dev[-_.]?(?P<dev_n>\d*))?",
    re.IGNORECASE,
)
_INF = float("inf")
_PRE_RANK = {"a": 0, "alpha": 0, "b": 1, "beta": 1}


@dataclass(frozen=True, kw_only=True)
class Version:
    """A parsed version that orders as PEP 440 does."""

    release: tuple[int, ...]
    pre: tuple[int, int] | None = None
    post: int | None = None
    dev: int | None = None

    @property
    def is_prerelease(self) -> bool:
        """Whether this is an alpha, beta or release candidate."""
        return self.pre is not None

    @property
    def is_devrelease(self) -> bool:
        """Whether this is a development build."""
        return self.dev is not None

    def _key(self) -> tuple[tuple[int, ...], float, float, float, float, float]:
        release = self.release
        while len(release) > 1 and release[-1] == 0:
            release = release[:-1]
        if self.pre is None and self.post is None and self.dev is not None:
            pre: tuple[float, float] = (-_INF, 0)
        elif self.pre is None:
            pre = (_INF, 0)
        else:
            pre = self.pre
        post = -_INF if self.post is None else self.post
        dev = _INF if self.dev is None else self.dev
        return (release, pre[0], pre[1], post, dev, 0)

    def __lt__(self, other: Version) -> bool:
        """Order by release, then pre-release, post-release and development part."""
        return self._key() < other._key()

    def __gt__(self, other: Version) -> bool:
        """Order by release, then pre-release, post-release and development part."""
        return self._key() > other._key()

    def __eq__(self, other: object) -> bool:
        """Equal when they order the same, so `1.0` and `1.0.0` are one version."""
        return isinstance(other, Version) and self._key() == other._key()

    def __hash__(self) -> int:
        """Hash what equality compares."""
        return hash(self._key())


def parse_version(text: str) -> Version | None:
    """Read a tag such as `v0.2026.11.0` or `0.2026.12.0rc1`, else `None`."""
    match = _VERSION.fullmatch(text.strip())
    if match is None:
        return None
    pre = None
    if match["pre_label"]:
        label = match["pre_label"].lower()
        pre = (_PRE_RANK.get(label, 2), int(match["pre_n"] or 0))
    return Version(
        release=tuple(int(part) for part in match["release"].split(".")),
        pre=pre,
        post=None if match["post_n"] is None else int(match["post_n"] or 0),
        dev=None if match["dev_n"] is None else int(match["dev_n"] or 0),
    )
