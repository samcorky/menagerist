"""The CSV item import routes: upload once, then inspect, preview and import by id.

An import runs on the worker; these tests run the worker's drain themselves.
"""

import uuid
from typing import TYPE_CHECKING, Any
from urllib.parse import quote

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
from app.modules.transfer.application.item_import import ImportItems
from app.modules.transfer.application.stored_imports import (
    ITEM_IMPORTS_JOB,
    RunQueuedImports,
    RunQueuedImportsCommand,
)
from app.modules.transfer.domain.entity_kind import EntityKind
from app.modules.transfer.domain.tabular import MAX_IMPORT_BYTES
from app.shared_kernel.access_guard import InMemoryAccessGuard
from app.shared_kernel.actor import SYSTEM_ACTOR, Actor
from app.shared_kernel.content_filter import ContentFilter
from app.shared_kernel.job_queue import InMemoryJobQueue
from app.shared_kernel.progress import NULL_PROGRESS

if TYPE_CHECKING:
    from fastapi import FastAPI

    from app.modules.transfer.ports.unit_of_work import TransferUnitOfWork
    from app.shared_kernel.progress import ProgressReporter
    from tests.modules.conftest import Shared

ALICE = Actor(id=uuid.UUID(int=0xA1), roles=frozenset({"member"}))
BOB = Actor(id=uuid.UUID(int=0xB2), roles=frozenset({"member"}))
READ_ONLY = Actor(
    id=uuid.UUID(int=0xA1),
    roles=frozenset({"member"}),
    grants=frozenset({"transfer:bundle:read"}),
)
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
                    },
                    "authenticated": {
                        "type": "boolean",
                        "title": "Authenticated",
                        "x-menagerist": {"kind": "boolean"},
                    },
                },
            },
        }
    ],
}
CSV = b"title,signed_on,authenticated\nAlien #1,2019-08,yes\nHulk 181,2021,no\n"
OPTIONS: dict[str, Any] = {
    "item_type": "signature",
    "mapping": [
        {"column": "title", "target": "name"},
        {"column": "signed_on", "target": "signed_on"},
        {"column": "authenticated", "target": "authenticated"},
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

    def _uow(self) -> TransferUnitOfWork:
        return create_in_memory_transfer_uow(self.shared.transfer_repos)

    async def actor_for(
        self, owner_id: uuid.UUID, grants: frozenset[str] | None
    ) -> Actor | None:
        """Every owner can still import, as the member they were."""
        return Actor(id=owner_id, roles=frozenset({"member"}), grants=grants)

    async def drain(self) -> None:
        """Run the worker's job over this instance's queue."""

        def importer(actor: Actor, progress: ProgressReporter) -> ImportItems:
            targets = self.shared.targets(actor)
            return ImportItems(
                self._uow(),
                InMemoryAccessGuard(),
                targets.presets,
                targets.graph,
                progress,
            )

        await RunQueuedImports(
            self._uow,
            InMemoryAccessGuard(),
            self.store,
            self,
            importer,
            lambda _: NULL_PROGRESS,
        ).handle(RunQueuedImportsCommand(), SYSTEM_ACTOR)


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


def _with_type(instance: Instance, bundle: dict[str, Any] = TYPE_FILE) -> TestClient:
    client = instance.client()
    assert client.post("/api/v1/bundles/import", json=bundle).status_code == 200
    return client


def _uploaded(client: TestClient, data: bytes) -> str:
    created = _upload(client, data)
    assert created.status_code == 201, created.text
    return str(created.json()["id"])


def _inspect(client: TestClient, data: bytes = CSV) -> Any:  # noqa: ANN401
    file_id = _uploaded(client, data)
    return client.post(f"{FILES}/{file_id}/inspect", json={"item_type": "signature"})


def _plan(client: TestClient, data: bytes = CSV, **options: object) -> Any:  # noqa: ANN401
    file_id = _uploaded(client, data)
    return client.post(f"{FILES}/{file_id}/plan", json={**OPTIONS, **options})


async def _run(
    instance: Instance, client: TestClient, data: bytes = CSV, **options: object
) -> dict[str, Any]:
    """Upload, queue and run the import; what reading the file back says."""
    file_id = _uploaded(client, data)
    queued = client.post(f"{FILES}/{file_id}/import", json={**OPTIONS, **options})
    assert queued.status_code == 202, queued.text
    await instance.drain()
    body: dict[str, Any] = client.get(f"{FILES}/{file_id}").json()
    return body


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


def test_the_filename_arrives_percent_encoded(instance: Instance) -> None:
    """A header holds only Latin-1, so any other name comes encoded."""
    response = instance.client().post(
        FILES,
        content=CSV,
        headers={"Content-Type": "text/csv", "X-Filename": quote("signés ✓.csv")},
    )
    assert response.json()["filename"] == "signés ✓.csv"


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


def test_inspect_returns_headers_rows_and_suggestions(instance: Instance) -> None:
    """Inspecting describes the file and suggests a mapping."""
    response = _inspect(_with_type(instance))

    assert response.status_code == 200
    body = response.json()
    assert body["headers"] == ["title", "signed_on", "authenticated"]
    assert body["row_count"] == 2
    assert body["encoding"] == "utf_8"
    assert body["sample_rows"][0] == {
        "title": "Alien #1",
        "signed_on": "2019-08",
        "authenticated": "yes",
    }
    assert {f["key"] for f in body["fields"]} == {"signed_on", "authenticated"}
    assert {m["column"]: m["target"] for m in body["suggested_mapping"]} == {
        "title": "name",
        "signed_on": "signed_on",
        "authenticated": "authenticated",
    }
    assert body["column_kinds"] == {
        "title": "text",
        "signed_on": "partialdate",
        "authenticated": "boolean",
    }


def test_inspect_reads_an_excel_windows_1252_file(instance: Instance) -> None:
    """Accents from Excel's plain CSV come through, and the encoding is reported."""
    data = "title,signed_on\nRené,2019\n".encode("cp1252")

    body = _inspect(_with_type(instance), data).json()

    assert body["encoding"] == "windows_1252"
    assert body["sample_rows"][0]["title"] == "René"


def test_inspect_suggests_a_day_month_order(instance: Instance) -> None:
    """A value like 19/08/2019 proves day first; no such value suggests nothing."""
    client = _with_type(instance)

    body = _inspect(client, b"title,signed_on\nAlien,19/08/2019\n").json()
    plain = _inspect(client).json()

    assert (body["day_month_order"], body["day_month_order_certain"]) == (
        "day_first",
        True,
    )
    assert (plain["day_month_order"], plain["day_month_order_certain"]) == (None, False)


def test_plan_for_a_good_file_is_ready_and_lists_items(instance: Instance) -> None:
    """A clean file previews as ready, with one entry per item."""
    body = _plan(_with_type(instance)).json()

    assert body["ready"] is True
    assert [e["label"] for e in body["entities"]] == ["Alien #1", "Hulk 181"]
    assert {e["action"] for e in body["entities"]} == {"create"}


def test_plan_reports_problems_as_blockers_and_is_not_ready(instance: Instance) -> None:
    """A bad cell blocks the plan and names its row and field."""
    bad = b"title,signed_on,authenticated\nAlien,19th Aug,yes\n"

    body = _plan(_with_type(instance), bad).json()

    assert body["ready"] is False
    assert body["blockers"][0]["reason"].startswith("Row 2, Signed on: '19th Aug'")


def test_plan_reads_excel_dates_in_the_chosen_order(instance: Instance) -> None:
    """13/04/2019 is a date day first, and no date month first."""
    client = _with_type(instance)
    data = b"title,signed_on,authenticated\nAlien,13/04/2019,yes\nHulk,Oct-18,no\n"

    day_first = _plan(client, data, day_month_order="day_first").json()
    month_first = _plan(client, data, day_month_order="month_first").json()

    assert day_first["ready"] is True
    assert month_first["ready"] is False
    assert "Row 2, Signed on" in str(month_first)


def test_a_mapping_naming_a_missing_column_is_refused(instance: Instance) -> None:
    """The problem names the column."""
    response = _plan(
        _with_type(instance), mapping=[{"column": "nope", "target": "name"}]
    )

    assert response.status_code == 400
    assert "nope" in response.text


def test_an_extra_field_with_an_unknown_kind_is_a_422(instance: Instance) -> None:
    """The kinds an import can keep are listed in the contract."""
    mapping = [
        {"column": "title", "target": "name"},
        {"column": "signed_on", "extra": {"key": "s", "title": "S", "kind": "money"}},
    ]

    assert _plan(_with_type(instance), mapping=mapping).status_code == 422


def test_an_unknown_row_end_is_a_422(instance: Instance) -> None:
    """A connection column must say which end the row is."""
    connections = [
        {
            "column": "title",
            "relationship_type": "signed",
            "item_type": "person",
            "row_end": "middle",
        }
    ]

    assert _plan(_with_type(instance), connections=connections).status_code == 422


def test_a_token_without_import_permission_is_forbidden(instance: Instance) -> None:
    """Uploading to import needs the import permission."""
    assert _upload(instance.client(READ_ONLY)).status_code == 403


async def test_a_run_creates_the_items_and_says_so(
    instance: Instance, shared: Shared
) -> None:
    """The worker adds the items, and the file reports what it added."""
    body = await _run(instance, _with_type(instance))

    assert body["status"] == "succeeded"
    assert body["result"] == {"items_added": 2, "connections_added": 0}
    nodes = await shared.graph_repos.nodes.list(
        after=None, limit=10, scope=ContentFilter.everyone()
    )
    assert sorted(n.name for n in nodes) == ["Alien #1", "Hulk 181"]
    assert not instance.store.files


async def test_a_bad_file_fails_and_adds_nothing(
    instance: Instance, shared: Shared
) -> None:
    """A run the plan would refuse fails, naming why."""
    bad = b"title,signed_on,authenticated\nAlien,soon,yes\n"

    body = await _run(instance, _with_type(instance), bad)

    assert body["status"] == "failed"
    assert "Row 2, Signed on" in body["failure"]
    assert not await shared.graph_repos.nodes.list(
        after=None, limit=10, scope=ContentFilter.everyone()
    )


async def test_a_run_keeps_a_column_as_each_item_s_own_field(
    instance: Instance, shared: Shared
) -> None:
    """A column with `extra` becomes a field on each item, not on the type."""
    mapping = [
        {"column": "title", "target": "name"},
        {
            "column": "authenticated",
            "extra": {"key": "checked", "title": "Checked", "kind": "boolean"},
        },
    ]

    body = await _run(instance, _with_type(instance), mapping=mapping)

    assert body["status"] == "succeeded", body
    nodes = await shared.graph_repos.nodes.list(
        after=None, limit=10, scope=ContentFilter.everyone()
    )
    alien = next(n for n in nodes if n.name == "Alien #1")
    assert alien.attributes == {"checked": True}
    assert alien.extra_schema is not None
    assert alien.extra_schema["properties"]["checked"]["title"] == "Checked"


KEYED = b"title,signed_on,authenticated\nAlien #1,2019-08,yes\n"


async def test_plan_with_a_key_column_reports_recognised_rows(
    instance: Instance,
) -> None:
    """Planning again with a key column names the item each row matched."""
    client = _with_type(instance)
    await _run(instance, client, KEYED, key_field="name")
    changed = b"title,signed_on,authenticated\nAlien #1,2019-09,yes\n"

    (entity,) = _plan(client, changed, key_field="name").json()["entities"]

    assert entity["action"] == "unchanged"
    assert entity["matched_name"] == "Alien #1"
    assert uuid.UUID(entity["matched_id"])
    assert entity["changed"] == ["attributes.signed_on"]


async def test_restore_brings_a_deleted_row_back(
    instance: Instance, shared: Shared
) -> None:
    """A row deleted after importing it is kept out unless its key is restored."""
    client = _with_type(instance)
    await _run(instance, client, KEYED, key_field="name")
    (node,) = await shared.graph_repos.nodes.list(
        after=None, limit=10, scope=ContentFilter.everyone()
    )
    await shared.targets(ALICE).graph.remove(EntityKind.ITEM, node.id)

    kept = _plan(client, KEYED, key_field="name").json()
    restored = _plan(client, KEYED, key_field="name", restore=["Alien #1"]).json()

    assert kept["entities"][0]["reason"] == "You deleted this after importing it."
    assert restored["entities"][0]["action"] == "create"


CONNECT_FILE: dict[str, Any] = {
    **TYPE_FILE,
    "relationship_types": [{"ref": "signed", "slug": "signed", "label": "Signed"}],
    "item_types": [
        *TYPE_FILE["item_types"],
        {"ref": "person", "slug": "person", "label": "Person"},
    ],
}
SIGNED = b"title,signer\nAlien #1,Sigourney Weaver\nAliens,sigourney weaver\n"


async def test_an_import_with_a_connection_column_reports_connections_added(
    instance: Instance,
) -> None:
    """A connection column joins each row to the person it names, made once."""
    client = _with_type(instance, CONNECT_FILE)
    options: dict[str, Any] = {
        "mapping": [{"column": "title", "target": "name"}],
        "connections": [
            {
                "column": "signer",
                "relationship_type": "signed",
                "item_type": "person",
                "row_end": "target",
            }
        ],
    }

    plan = _plan(client, SIGNED, **options).json()
    body = await _run(instance, client, SIGNED, **options)

    kinds = [e["kind"] for e in plan["entities"]]
    assert kinds.count("connection") == 2
    assert "relationship_type" not in kinds
    assert body["result"] == {"items_added": 3, "connections_added": 2}
