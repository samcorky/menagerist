from datetime import datetime, timedelta
from typing import TYPE_CHECKING
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.modules.backup.application.create_backup import CreateBackupCommand
from app.modules.backup.application.prune_backups import PruneBackupsCommand
from app.modules.backup.domain.verification import FindingKind
from app.platform.request_model import RequestModel

if TYPE_CHECKING:
    from app.modules.backup.application.list_user_exports import UserExport


class CreateBackupRequest(RequestModel):
    """Options for a verified instance archive."""

    model_config = ConfigDict(json_schema_extra={"examples": [{"label": "manual"}]})

    label: str = Field(default="manual", min_length=1, max_length=120)

    def to_command(self) -> CreateBackupCommand:
        """Translate validated request values into a use-case command."""
        return CreateBackupCommand(label=self.label)


class BackupResponse(BaseModel):
    """Committed archive metadata."""

    model_config = ConfigDict(
        from_attributes=True,
        json_schema_extra={
            "examples": [
                {
                    "id": "0199ec2d-f086-7000-8000-000000000001",
                    "label": "manual",
                    "size": 1048576,
                    "created_at": "2026-10-19T12:00:00Z",
                    "alembic_revision": "a1b2c3d4e5f6",
                    "app_version": "0.1.0",
                }
            ]
        },
    )
    id: UUID
    label: str
    size: int
    created_at: datetime
    alembic_revision: str
    app_version: str


class UserExportResponse(BaseModel):
    """A personal export and when it expires."""

    model_config = ConfigDict(
        json_schema_extra={
            "examples": [
                {
                    "id": "0199ec2d-f086-7000-8000-000000000001",
                    "size": 1048576,
                    "created_at": "2026-10-24T12:00:00Z",
                    "expires_at": "2026-10-25T12:00:00Z",
                }
            ]
        }
    )
    id: UUID
    size: int
    created_at: datetime
    expires_at: datetime

    @classmethod
    def from_export(cls, export: UserExport) -> UserExportResponse:
        """Build the response from a listed export."""
        return cls(
            id=export.summary.id,
            size=export.summary.size,
            created_at=export.summary.created_at,
            expires_at=export.expires_at,
        )


class FindingResponse(BaseModel):
    """One archive integrity finding."""

    model_config = ConfigDict(
        from_attributes=True,
        json_schema_extra={
            "examples": [
                {
                    "kind": "checksum_mismatch",
                    "member": "data/nodes.ndjson",
                    "expected": "a" * 64,
                    "actual": "b" * 64,
                }
            ]
        },
    )
    kind: FindingKind
    member: str
    expected: str | None
    actual: str | None


class VerificationResponse(BaseModel):
    """All integrity findings for an archive."""

    model_config = ConfigDict(
        from_attributes=True, json_schema_extra={"examples": [{"findings": []}]}
    )
    findings: list[FindingResponse]


class PruneBackupsRequest(RequestModel):
    """Retention overrides and an explicit preview flag."""

    model_config = ConfigDict(
        json_schema_extra={
            "examples": [
                {
                    "keep_last": 7,
                    "older_than_days": 30,
                    "pre_migration_keep": 3,
                    "dry_run": True,
                }
            ]
        }
    )

    keep_last: int | None = Field(default=None, ge=0)
    older_than_days: int | None = Field(default=None, ge=0)
    pre_migration_keep: int | None = Field(default=None, ge=0)
    dry_run: bool = False

    def to_command(self) -> PruneBackupsCommand:
        """Translate validated request values into a use-case command."""
        return PruneBackupsCommand(
            keep_last=self.keep_last,
            older_than=None
            if self.older_than_days is None
            else timedelta(days=self.older_than_days),
            pre_migration_keep=self.pre_migration_keep,
            dry_run=self.dry_run,
        )


class PruneResponse(BaseModel):
    """Retention decisions and reclaimed storage."""

    model_config = ConfigDict(
        from_attributes=True,
        json_schema_extra={
            "examples": [
                {
                    "deleted": [],
                    "kept": ["0199ec2d-f086-7000-8000-000000000001"],
                    "freed_bytes": 0,
                    "orphans_removed": [],
                    "unreadable": [],
                    "user_exports_removed": [],
                }
            ]
        },
    )
    deleted: list[str]
    kept: list[str]
    freed_bytes: int
    orphans_removed: list[str]
    unreadable: list[str]
    user_exports_removed: list[str]
