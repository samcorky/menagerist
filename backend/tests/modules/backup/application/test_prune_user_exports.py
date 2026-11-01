"""Hourly export expiry never touches instance backup retention."""

from dataclasses import replace
from datetime import UTC, datetime, timedelta
from uuid import uuid7

import pytest

from app.entrypoints.api.shared.access_guard import get_access_guard
from app.modules.backup.adapters.storage.in_memory_backup_store import (
    InMemoryBackupStore,
)
from app.modules.backup.application.prune_user_exports import (
    PruneUserExports,
    PruneUserExportsCommand,
)
from app.modules.backup.domain.backup import BackupSummary
from app.shared_kernel.actor import SYSTEM_ACTOR, Actor
from app.shared_kernel.errors import ForbiddenError


async def test_only_expired_exports_are_removed() -> None:
    """The hourly job expires exports on the configured TTL and nothing else."""
    backup_id = uuid7()
    owner_store = InMemoryBackupStore()
    owner_store.summaries[backup_id] = BackupSummary(
        id=backup_id,
        label="user-export",
        size=1,
        created_at=datetime.now(UTC),
        alembic_revision="head",
        app_version="test",
    )
    owner_store.archives[backup_id] = b""
    instance = InMemoryBackupStore()
    instance.user_stores[uuid7()] = owner_store
    prune = PruneUserExports(instance, get_access_guard(), user_export_ttl_hours=24)
    assert await prune.handle(PruneUserExportsCommand(), SYSTEM_ACTOR) == []
    owner_store.summaries[backup_id] = replace(
        owner_store.summaries[backup_id],
        created_at=datetime.now(UTC) - timedelta(hours=25),
    )
    removed = await prune.handle(PruneUserExportsCommand(), SYSTEM_ACTOR)
    assert len(removed) == 1
    assert await owner_store.list() == []


async def test_requires_the_delete_permission() -> None:
    """Ordinary actors cannot trigger instance-wide cleanup."""
    prune = PruneUserExports(InMemoryBackupStore(), get_access_guard())
    with pytest.raises(ForbiddenError):
        await prune.handle(PruneUserExportsCommand(), Actor(id=uuid7()))
