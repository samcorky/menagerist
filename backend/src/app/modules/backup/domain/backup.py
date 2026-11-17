from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum
from uuid import UUID


class BackupScope(StrEnum):
    """Content included in an archive."""

    INSTANCE = "instance"
    USER = "user"


@dataclass(frozen=True, kw_only=True)
class TableDigest:
    """Integrity and row count of an exported table."""

    name: str
    rows: int
    sha256: str


@dataclass(frozen=True, kw_only=True)
class MediaFileRef:
    """Original media file and its lifecycle bucket."""

    asset_id: UUID
    status: str
    size: int
    sha256: str


# The square sizes an account picture is stored at; identity's `AVATAR_SIZES`,
# repeated because backups import no other module (a bridge test keeps them equal).
PICTURE_SIZES: frozenset[int] = frozenset({64, 128, 256})


@dataclass(frozen=True, kw_only=True)
class PictureFileRef:
    """One stored size of an account picture: whose, which version, how big."""

    user_id: UUID
    version: str
    pixels: int
    size: int
    sha256: str

    @property
    def member(self) -> str:
        """Where the file sits inside an archive."""
        return f"avatars/{self.user_id}/{self.version}-{self.pixels}.webp"


@dataclass(frozen=True, kw_only=True)
class BackupManifest:
    """Versioned description of an instance archive's contents."""

    app_version: str
    alembic_revision: str
    label: str
    created_at: datetime
    created_by: UUID
    owner_id: UUID | None = None
    format: str = "ndjson"
    format_version: int = 1
    scope: BackupScope | str = BackupScope.INSTANCE
    tables: list[TableDigest] = field(default_factory=list)
    media: list[MediaFileRef] = field(default_factory=list)
    media_missing: list[UUID] = field(default_factory=list)
    pictures: list[PictureFileRef] = field(default_factory=list)
    from_revision: str | None = None
    to_revision: str | None = None


@dataclass(frozen=True, kw_only=True)
class BackupSummary:
    """Committed archive metadata used without opening the archive."""

    id: UUID
    label: str
    size: int
    created_at: datetime
    alembic_revision: str
    app_version: str


@dataclass(frozen=True, kw_only=True)
class StoredBackup:
    """Completed archive and its compressed-byte digest."""

    summary: BackupSummary
    sha256: str


@dataclass(frozen=True, kw_only=True)
class MemberDigest:
    """Integrity and newline count of uncompressed member bytes."""

    size: int
    sha256: str
    lines: int
