from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True, kw_only=True)
class AppInfo:
    """Public version and build provenance of the running instance."""

    name: str
    version: str
    commit_sha: str | None = None
    short_sha: str | None = None
    branch: str | None = None
    dirty: bool | None = None
    build_timestamp: datetime | None = None
    migration_head: tuple[str, ...]
