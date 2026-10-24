from typing import TYPE_CHECKING, Annotated
from uuid import uuid7

import pytest
from fastapi import Depends, FastAPI
from starlette.testclient import TestClient

from app.entrypoints.api import create_app
from app.entrypoints.api.shared.backup_dependencies import (
    get_media_files,
    get_setup_gate,
    get_user_media_files,
)
from app.entrypoints.api.shared.bridges.backup_setup_gate import first_run_restore_slot
from app.entrypoints.api.shared.dependencies import get_current_actor
from app.modules.backup.adapters.api.dependencies import (
    get_backup_store,
    get_backup_workspace,
    get_database_restorer,
    get_database_snapshot,
)
from app.modules.backup.adapters.api.user_dependencies import (
    get_user_backup_store,
    get_user_database_restorer,
    get_user_database_snapshot,
)
from app.modules.backup.adapters.media.in_memory_media_files import InMemoryMediaFiles
from app.modules.backup.adapters.persistence.in_memory_database_restorer import (
    InMemoryDatabaseRestorer,
)
from app.modules.backup.adapters.persistence.in_memory_database_snapshot import (
    InMemoryDatabaseSnapshot,
)
from app.modules.backup.adapters.persistence.in_memory_setup_gate import (
    InMemorySetupGate,
)
from app.modules.backup.adapters.persistence.in_memory_user_database_restorer import (
    InMemoryUserDatabaseRestorer,
)
from app.modules.backup.adapters.persistence.in_memory_user_database_snapshot import (
    InMemoryUserDatabaseSnapshot,
)
from app.modules.backup.adapters.storage.in_memory_backup_store import (
    InMemoryBackupStore,
)
from app.modules.backup.adapters.storage.in_memory_backup_workspace import (
    InMemoryBackupWorkspace,
)
from app.shared_kernel.actor import Actor

if TYPE_CHECKING:
    from collections.abc import Iterator

    from app.modules.backup.ports.backup_store import BackupStore


@pytest.fixture
def client() -> Iterator[TestClient]:
    """Build an isolated API client using in-memory backup adapters."""
    app = create_app()
    store = InMemoryBackupStore()
    target = InMemoryDatabaseRestorer("revision")
    app.dependency_overrides.update(
        {
            get_current_actor: lambda: Actor(id=uuid7(), roles=frozenset({"admin"})),
            get_backup_store: lambda: store,
            first_run_restore_slot: lambda: None,
            get_backup_workspace: InMemoryBackupWorkspace,
            get_database_snapshot: lambda: InMemoryDatabaseSnapshot(
                "revision", {"data/users.ndjson": b"{}\n"}
            ),
            get_database_restorer: lambda: target,
            get_media_files: InMemoryMediaFiles,
            get_setup_gate: InMemorySetupGate,
        }
    )
    with TestClient(app) as test_client:
        yield test_client


def test_backup_create_verify_download_upload_delete(client: TestClient) -> None:
    """Administrative routes drive the same verified archive use cases."""
    created = client.post("/api/v1/backup", json={})
    assert created.status_code == 201, created.text
    backup_id = created.json()["id"]
    listing = client.get("/api/v1/backup")
    assert [row["id"] for row in listing.json()] == [backup_id]
    verified = client.post(f"/api/v1/backup/{backup_id}/verify")
    assert verified.status_code == 200
    assert verified.json()["findings"] == []
    download = client.get(f"/api/v1/backup/{backup_id}/download")
    assert download.status_code == 200
    assert download.headers["content-type"] == "application/gzip"
    uploaded = client.post(
        "/api/v1/backup/upload",
        content=download.content,
        headers={"Content-Type": "application/gzip"},
    )
    assert uploaded.status_code == 201, uploaded.text
    assert uploaded.json()["id"] != backup_id
    assert client.delete(f"/api/v1/backup/{backup_id}").status_code == 204
    assert client.get(f"/api/v1/backup/{backup_id}/download").status_code == 404


def test_backup_member_is_forbidden(client: TestClient) -> None:
    """An ordinary member cannot list or create instance archives."""
    assert isinstance(client.app, FastAPI)
    client.app.dependency_overrides[get_current_actor] = lambda: Actor(
        id=uuid7(), roles=frozenset({"member"})
    )
    assert client.get("/api/v1/backup").status_code == 403
    assert client.post("/api/v1/backup", json={}).status_code == 403


@pytest.mark.parametrize(
    ("label", "slug"),
    [
        ("Before upgrade", "before-upgrade"),
        ("Café / Photos", "cafe-photos"),
        ("📚", "backup"),
        ('a"\r\nb', "a-b"),
    ],
)
def test_backup_download_filename(client: TestClient, label: str, slug: str) -> None:
    """Downloads have a safe label, creation date and unique archive id."""
    created = client.post("/api/v1/backup", json={"label": label}).json()
    response = client.get(f"/api/v1/backup/{created['id']}/download")
    expected = f"menagerist-{slug}-{created['created_at'][:10]}-{created['id']}.tar.gz"
    assert (
        response.headers["content-disposition"] == f'attachment; filename="{expected}"'
    )


def test_public_first_run_restore_then_closed_gate(client: TestClient) -> None:
    """Restored accounts close the anonymous restore path with no live restore API."""
    created = client.post("/api/v1/backup", json={}).json()
    archive = client.get(f"/api/v1/backup/{created['id']}/download").content
    response = client.post(
        "/api/v1/backup/first-run-restore",
        content=archive,
        headers={"Content-Type": "application/gzip"},
    )
    assert response.status_code == 204, response.text
    assert (
        client.post(
            "/api/v1/backup/first-run-restore",
            content=archive,
            headers={"Content-Type": "application/gzip"},
        ).status_code
        == 409
    )
    assert client.post(f"/api/v1/backup/{created['id']}/restore").status_code == 404


def test_cross_site_first_run_restore_is_refused(client: TestClient) -> None:
    """A third-party site cannot claim an empty instance through restoration."""
    assert (
        client.post(
            "/api/v1/backup/first-run-restore",
            content=b"unused",
            headers={
                "Origin": "https://foreign.example",
                "Sec-Fetch-Site": "cross-site",
            },
        ).status_code
        == 403
    )


def test_prune_has_explicit_preview(client: TestClient) -> None:
    """Preview retention without deleting archives."""
    for _ in range(3):
        assert client.post("/api/v1/backup", json={}).status_code == 201
    preview = client.post(
        "/api/v1/backup/prune", json={"keep_last": 1, "dry_run": True}
    )
    assert preview.status_code == 200, preview.text
    assert len(preview.json()["deleted"]) == 2
    assert len(client.get("/api/v1/backup").json()) == 3


def test_personal_export_download_isolation_and_import(client: TestClient) -> None:
    """Members can move their own content without reaching another user's archive."""
    assert isinstance(client.app, FastAPI)
    alice, bob = Actor(id=uuid7()), Actor(id=uuid7())
    node_id = uuid7()
    current = alice
    stores: dict[object, InMemoryBackupStore] = {}
    target = InMemoryUserDatabaseRestorer("revision")

    def personal_store(
        actor: Annotated[Actor, Depends(get_current_actor)],
    ) -> BackupStore:
        return stores.setdefault(actor.id, InMemoryBackupStore())

    client.app.dependency_overrides.update(
        {
            get_current_actor: lambda: current,
            get_user_backup_store: personal_store,
            get_user_database_snapshot: lambda: InMemoryUserDatabaseSnapshot(
                "revision",
                {
                    "nodes": [
                        {"id": node_id, "owner_id": alice.id, "name": "Alice's item"}
                    ],
                },
            ),
            get_user_database_restorer: lambda: target,
            get_user_media_files: InMemoryMediaFiles,
        }
    )
    exported = client.post("/api/v1/me/export")
    assert exported.status_code == 201, exported.text
    backup_id = exported.json()["id"]
    path = f"/api/v1/me/export/{backup_id}/download"
    downloaded = client.get(path)
    assert downloaded.status_code == 200
    current = bob
    assert client.get(path).status_code == 404
    imported = client.post(
        "/api/v1/me/import",
        content=downloaded.content,
        headers={"Content-Type": "application/gzip"},
    )
    assert imported.status_code == 204, imported.text
    assert str(target.tables["nodes"][0]["owner_id"]) == str(bob.id)
    assert str(target.tables["nodes"][0]["id"]) == str(node_id)
    assert (
        client.post(
            "/api/v1/me/import",
            content=downloaded.content,
            headers={"Content-Type": "application/gzip"},
        ).status_code
        == 409
    )
    assert stores[bob.id].summaries == {}


def test_personal_exports_are_listed_and_deleted_per_account(
    client: TestClient,
) -> None:
    """Each account lists and deletes only its own exports."""
    assert isinstance(client.app, FastAPI)
    alice, bob = Actor(id=uuid7()), Actor(id=uuid7())
    current = alice
    stores: dict[object, InMemoryBackupStore] = {}

    def personal_store(
        actor: Annotated[Actor, Depends(get_current_actor)],
    ) -> BackupStore:
        return stores.setdefault(actor.id, InMemoryBackupStore())

    client.app.dependency_overrides.update(
        {
            get_current_actor: lambda: current,
            get_user_backup_store: personal_store,
            get_user_database_snapshot: lambda: InMemoryUserDatabaseSnapshot(
                "revision", {}
            ),
            get_user_media_files: InMemoryMediaFiles,
        }
    )
    assert client.get("/api/v1/me/exports").json() == []
    first = client.post("/api/v1/me/export").json()["id"]
    second = client.post("/api/v1/me/export").json()["id"]

    listed = client.get("/api/v1/me/exports")
    assert listed.status_code == 200
    assert [row["id"] for row in listed.json()] == [second, first]
    assert set(listed.json()[0]) == {"id", "size", "created_at", "expires_at"}

    current = bob
    assert client.get("/api/v1/me/exports").json() == []
    other = client.delete(f"/api/v1/me/export/{first}")
    assert other.status_code == 404
    assert other.headers["content-type"] == "application/problem+json"

    current = alice
    assert client.delete(f"/api/v1/me/export/{first}").status_code == 204
    assert [row["id"] for row in client.get("/api/v1/me/exports").json()] == [second]
    assert client.get(f"/api/v1/me/export/{first}/download").status_code == 404
    assert client.delete(f"/api/v1/me/export/{first}").status_code == 404
