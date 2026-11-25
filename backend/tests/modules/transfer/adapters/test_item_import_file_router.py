"""The routes for CSV files uploaded once and imported by id on the worker."""

import uuid
from typing import TYPE_CHECKING, Any

import pytest
from starlette.testclient import TestClient

from app.entrypoints.api import create_app
from app.entrypoints.api.shared.bridges.job_queue import get_job_queue
from app.entrypoints.api.shared.bridges.transfer_targets import (
    get_collection_pack_target,
    get_graph_pack_target,
    get_preset_pack_target,
)
from app.entrypoints.api.shared.dependencies import get_current_actor
from app.modules.presets.adapters.api.dependencies import get_preset_repos
from app.modules.transfer.adapters.api.dependencies import (
    get_import_file_store,
    get_transfer_repos,
    get_transfer_uow,
)
from app.modules.transfer.adapters.persistence.unit_of_work import (
    create_in_memory_transfer_uow,
)
from app.modules.transfer.adapters.storage.in_memory_import_files import (
    InMemoryImportFileStore,
)
from app.modules.transfer.application.stored_imports import ITEM_IMPORTS_JOB
from app.modules.transfer.domain.tabular import MAX_IMPORT_BYTES
from app.shared_kernel.actor import Actor
from app.shared_kernel.job_queue import InMemoryJobQueue

if TYPE_CHECKING:
    from fastapi import FastAPI

    from tests.modules.conftest import Shared

ALICE = Actor(id=uuid.UUID(int=0xA1), roles=frozenset({"member"}))
BOB = Actor(id=uuid.UUID(int=0xB2), roles=frozenset({"member"}))
FILES = "/api/v1/imports/items/files"
TYPE_FILE: dict[str, Any] = {
    "format": "menagerist-bundle",
    "version": 2,
    "presets": [],
    "relationship_types": [],
    "item_types": [
        {
            "ref": "signature",
            "slug": "signature",
            "label": "Signature",
            "attributes_schema": {
                "type": "object",
                "properties": {
                    "signed_on": {
                        "type": "string",
                        "title": "Signed on",
                        "pattern": "^[0-9]{4}(-[0-9]{2})?(-[0-9]{2})?$",
                        "x-menagerist": {"kind": "partialdate"},
                    }
                },
            },
        }
    ],
}
CSV = b"title,signed_on\nAlien #1,2019-08\nHulk 181,2021\n"
OPTIONS: dict[str, Any] = {
    "item_type": "signature",
    "mapping": [
        {"column": "title", "target": "name"},
        {"column": "signed_on", "target": "signed_on"},
    ],
}


class Instance:
    """One server's imports, files and worker queue, with a client per person."""

    def __init__(self, shared: Shared) -> None:
        self.shared = shared
        self.store = InMemoryImportFileStore()
        self.jobs = InMemoryJobQueue()

    def client(self, actor: Actor = ALICE) -> TestClient:
        """A client acting as `actor` on this instance."""
        app: FastAPI = create_app()
        targets = self.shared.targets(actor)
        overrides = app.dependency_overrides
        overrides[get_preset_pack_target] = lambda: targets.presets
        overrides[get_graph_pack_target] = lambda: targets.graph
        overrides[get_collection_pack_target] = lambda: targets.collections
        overrides[get_preset_repos] = lambda: self.shared.preset_repos
        overrides[get_current_actor] = lambda: actor
        overrides[get_transfer_repos] = lambda: self.shared.transfer_repos
        overrides[get_transfer_uow] = lambda: create_in_memory_transfer_uow(
            self.shared.transfer_repos
        )
        overrides[get_import_file_store] = lambda: self.store
        overrides[get_job_queue] = lambda: self.jobs
        return TestClient(app)


@pytest.fixture
def instance(shared: Shared) -> Instance:
    """A fresh instance over the shared repositories."""
    return Instance(shared)


def _upload(client: TestClient, data: bytes = CSV) -> Any:  # noqa: ANN401
    return client.post(
        FILES,
        content=data,
        headers={"Content-Type": "text/csv", "X-Filename": "signatures.csv"},
    )


def _with_type(instance: Instance) -> TestClient:
    client = instance.client()
    assert client.post("/api/v1/bundles/import", json=TYPE_FILE).status_code == 200
    return client


def test_an_upload_is_created_and_read_back(instance: Instance) -> None:
    """The new file is listed and readable by its id."""
    client = instance.client()
    created = _upload(client)
    assert created.status_code == 201
    body = created.json()
    assert body["filename"] == "signatures.csv"
    assert body["size"] == len(CSV)
    assert body["status"] == "uploaded"
    assert body["ahead"] is None
    read = client.get(f"{FILES}/{body['id']}")
    assert read.status_code == 200
    assert read.json()["id"] == body["id"]
    assert [f["id"] for f in client.get(FILES).json()] == [body["id"]]


def test_an_upload_over_the_limit_is_refused(instance: Instance) -> None:
    """The upload limit stops a file over 50 MB before it is read."""
    response = _upload(instance.client(), b"t" * (MAX_IMPORT_BYTES + 1))
    assert response.status_code == 413
    assert not instance.store.files


def test_a_file_is_inspected_previewed_and_queued(instance: Instance) -> None:
    """The file goes once; the rest is JSON naming it."""
    client = _with_type(instance)
    file_id = _upload(client).json()["id"]
    inspected = client.post(
        f"{FILES}/{file_id}/inspect", json={"item_type": "signature"}
    )
    assert inspected.status_code == 200
    assert inspected.json()["row_count"] == 2
    planned = client.post(f"{FILES}/{file_id}/plan", json=OPTIONS)
    assert planned.status_code == 200
    assert planned.json()["ready"] is True
    queued = client.post(f"{FILES}/{file_id}/import", json=OPTIONS)
    assert queued.status_code == 202
    assert queued.json()["status"] == "queued"
    assert queued.json()["ahead"] == 0
    assert instance.jobs.requests == [(ITEM_IMPORTS_JOB, ALICE.id)]


def test_a_file_is_queued_once(instance: Instance) -> None:
    """A second request is a clash."""
    client = instance.client()
    file_id = _upload(client).json()["id"]
    assert client.post(f"{FILES}/{file_id}/import", json=OPTIONS).status_code == 202
    again = client.post(f"{FILES}/{file_id}/import", json=OPTIONS)
    assert again.status_code == 409


def test_someone_else_s_file_is_not_found(instance: Instance) -> None:
    """Every route answers 404 for a file that is not the person's."""
    file_id = _upload(instance.client()).json()["id"]
    bob = instance.client(BOB)
    assert bob.get(f"{FILES}/{file_id}").status_code == 404
    assert bob.delete(f"{FILES}/{file_id}").status_code == 404
    assert (
        bob.post(f"{FILES}/{file_id}/inspect", json={"item_type": "x"}).status_code
        == 404
    )
    assert bob.post(f"{FILES}/{file_id}/plan", json=OPTIONS).status_code == 404
    assert bob.post(f"{FILES}/{file_id}/import", json=OPTIONS).status_code == 404
    assert bob.get(FILES).json() == []


def test_deleting_a_file_removes_it(instance: Instance) -> None:
    """The record and the stored bytes both go."""
    client = instance.client()
    file_id = _upload(client).json()["id"]
    assert client.delete(f"{FILES}/{file_id}").status_code == 204
    assert client.get(f"{FILES}/{file_id}").status_code == 404
    assert not instance.store.files
