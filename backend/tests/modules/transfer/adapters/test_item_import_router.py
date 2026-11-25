"""The CSV item import routes: inspect, plan and run."""

import json
import uuid
from typing import TYPE_CHECKING, Any

from starlette.testclient import TestClient

from app.entrypoints.api import create_app
from app.entrypoints.api.shared.bridges.transfer_targets import (
    get_collection_pack_target,
    get_graph_pack_target,
    get_preset_pack_target,
)
from app.entrypoints.api.shared.dependencies import get_current_actor
from app.modules.presets.adapters.api.dependencies import get_preset_repos
from app.modules.transfer.adapters.api.dependencies import (
    get_transfer_repos,
    get_transfer_uow,
)
from app.modules.transfer.adapters.persistence.unit_of_work import (
    create_in_memory_transfer_uow,
)
from app.modules.transfer.domain.entity_kind import EntityKind
from app.modules.transfer.domain.tabular import MAX_IMPORT_BYTES
from app.shared_kernel.actor import Actor
from app.shared_kernel.content_filter import ContentFilter

if TYPE_CHECKING:
    from fastapi import FastAPI

    from tests.modules.conftest import Shared

ALICE = Actor(id=uuid.UUID(int=0xA1), roles=frozenset({"member"}))
READ_ONLY = Actor(
    id=uuid.UUID(int=0xA1),
    roles=frozenset({"member"}),
    grants=frozenset({"transfer:bundle:read"}),
)
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
MAPPING = [
    {"column": "title", "target": "name"},
    {"column": "signed_on", "target": "signed_on"},
    {"column": "authenticated", "target": "authenticated"},
]


def _client(shared: Shared, actor: Actor = ALICE) -> TestClient:
    app: FastAPI = create_app()
    targets = shared.targets(actor)
    app.dependency_overrides[get_preset_pack_target] = lambda: targets.presets
    app.dependency_overrides[get_graph_pack_target] = lambda: targets.graph
    app.dependency_overrides[get_collection_pack_target] = lambda: targets.collections
    app.dependency_overrides[get_preset_repos] = lambda: shared.preset_repos
    app.dependency_overrides[get_current_actor] = lambda: actor
    app.dependency_overrides[get_transfer_repos] = lambda: shared.transfer_repos
    app.dependency_overrides[get_transfer_uow] = lambda: create_in_memory_transfer_uow(
        shared.transfer_repos
    )
    return TestClient(app)


def _with_type(shared: Shared) -> TestClient:
    client = _client(shared)
    assert client.post("/api/v1/bundles/import", json=TYPE_FILE).status_code == 200
    return client


def _post(
    client: TestClient,
    path: str,
    data: bytes = CSV,
    mapping: object = MAPPING,
    **extra: str,
) -> Any:  # noqa: ANN401
    form = {"item_type": "signature", "mapping": json.dumps(mapping), **extra}
    return client.post(
        f"/api/v1/imports/items{path}",
        files={"file": ("signatures.csv", data, "text/csv")},
        data=form,
    )


def test_inspect_returns_headers_rows_and_suggestions(shared: Shared) -> None:
    """The first call describes the file and suggests a mapping."""
    client = _with_type(shared)

    response = _post(client, "/inspect")

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


def test_plan_for_a_good_file_is_ready_and_lists_items(shared: Shared) -> None:
    """A clean file previews as ready, with one entry per item."""
    client = _with_type(shared)

    response = _post(client, "/plan")

    body = response.json()
    assert response.status_code == 200
    assert body["ready"] is True
    assert [e["label"] for e in body["entities"]] == ["Alien #1", "Hulk 181"]
    assert {e["action"] for e in body["entities"]} == {"create"}


def test_plan_reports_problems_as_blockers_and_is_not_ready(shared: Shared) -> None:
    """A bad cell blocks the plan and names its row and field."""
    client = _with_type(shared)
    bad = b"title,signed_on,authenticated\nAlien,19th Aug,yes\n"

    response = _post(client, "/plan", data=bad)

    body = response.json()
    assert body["ready"] is False
    assert body["blockers"][0]["reason"].startswith("Row 2, Signed on: '19th Aug'")


async def test_run_creates_items_and_returns_counts(shared: Shared) -> None:
    """Running creates the items."""
    client = _with_type(shared)

    response = _post(client, "")

    assert response.status_code == 200
    assert response.json() == {"items_added": 2, "connections_added": 0}
    nodes = await shared.graph_repos.nodes.list(
        after=None, limit=10, scope=ContentFilter.everyone()
    )
    assert sorted(n.name for n in nodes) == ["Alien #1", "Hulk 181"]


def test_a_bad_file_is_not_run(shared: Shared) -> None:
    """A run of a file the plan refused is a conflict, and creates nothing."""
    client = _with_type(shared)
    bad = b"title,signed_on,authenticated\nAlien,soon,yes\n"

    response = _post(client, "", data=bad)

    assert response.status_code == 409


def test_mapping_that_is_not_json_is_refused(shared: Shared) -> None:
    """The mapping field must be JSON."""
    client = _with_type(shared)

    response = _post(client, "/plan", mapping="not json")

    assert response.status_code == 422


def test_a_mapping_naming_a_missing_column_is_refused(shared: Shared) -> None:
    """The problem names the column."""
    client = _with_type(shared)

    response = _post(client, "/plan", mapping=[{"column": "nope", "target": "name"}])

    assert response.status_code == 400
    assert "nope" in response.text


def test_a_file_over_the_limit_is_refused(shared: Shared) -> None:
    """A file over the byte limit is refused, naming it."""
    client = _with_type(shared)

    response = _post(client, "/inspect", data=b"t" * (MAX_IMPORT_BYTES + 1))

    assert response.status_code == 400
    assert "50 MB" in response.text


def test_a_token_without_import_permission_is_forbidden(shared: Shared) -> None:
    """Importing needs the import permission."""
    client = _client(shared, READ_ONLY)

    response = _post(client, "/plan")

    assert response.status_code == 403


def test_inspect_reads_an_excel_windows_1252_file(shared: Shared) -> None:
    """Accents from Excel's plain CSV come through, and the encoding is reported."""
    client = _with_type(shared)
    data = "title,signed_on\nRené,2019\n".encode("cp1252")

    body = _post(client, "/inspect", data=data).json()

    assert body["encoding"] == "windows_1252"
    assert body["sample_rows"][0]["title"] == "René"


def test_plan_reads_excel_dates_in_the_chosen_order(shared: Shared) -> None:
    """13/04/2019 is a date day first, and no date month first."""
    client = _with_type(shared)
    data = b"title,signed_on,authenticated\nAlien,13/04/2019,yes\nHulk,Oct-18,no\n"

    day_first = _post(client, "/plan", data=data, day_month_order="day_first")
    month_first = _post(client, "/plan", data=data, day_month_order="month_first")

    assert day_first.json()["ready"] is True
    assert month_first.json()["ready"] is False
    assert "Row 2, Signed on" in str(month_first.json())


def test_inspect_suggests_a_day_month_order(shared: Shared) -> None:
    """A value like 19/08/2019 proves day first; no such value suggests nothing."""
    client = _with_type(shared)
    data = b"title,signed_on,authenticated\nAlien,19/08/2019,yes\n"

    body = _post(client, "/inspect", data=data).json()
    plain = _post(client, "/inspect").json()

    assert (body["day_month_order"], body["day_month_order_certain"]) == (
        "day_first",
        True,
    )
    assert (plain["day_month_order"], plain["day_month_order_certain"]) == (None, False)


def test_inspect_suggests_a_kind_for_each_column(shared: Shared) -> None:
    """Each column's values suggest the kind it would be kept as."""
    client = _with_type(shared)

    response = _post(client, "/inspect")

    assert response.json()["column_kinds"] == {
        "title": "text",
        "signed_on": "partialdate",
        "authenticated": "boolean",
    }


async def test_run_keeps_a_column_as_each_item_s_own_field(shared: Shared) -> None:
    """A column with `extra` becomes a field on each item, not on the type."""
    client = _with_type(shared)
    mapping = [
        {"column": "title", "target": "name"},
        {
            "column": "authenticated",
            "extra": {"key": "checked", "title": "Checked", "kind": "boolean"},
        },
    ]

    response = _post(client, "", mapping=mapping)

    assert response.status_code == 200, response.text
    nodes = await shared.graph_repos.nodes.list(
        after=None, limit=10, scope=ContentFilter.everyone()
    )
    alien = next(n for n in nodes if n.name == "Alien #1")
    assert alien.attributes == {"checked": True}
    assert alien.extra_schema is not None
    assert alien.extra_schema["properties"]["checked"]["title"] == "Checked"


def test_an_extra_field_with_an_unknown_kind_is_a_422(shared: Shared) -> None:
    """The kinds an import can keep are listed in the contract."""
    client = _with_type(shared)
    mapping = [
        {"column": "title", "target": "name"},
        {"column": "signed_on", "extra": {"key": "s", "title": "S", "kind": "money"}},
    ]

    assert _post(client, "/plan", mapping=mapping).status_code == 422


KEYED = b"title,signed_on,authenticated\nAlien #1,2019-08,yes\n"


def test_plan_with_a_key_column_reports_recognised_rows(shared: Shared) -> None:
    """Planning again with a key column names the item each row matched."""
    client = _with_type(shared)
    assert _post(client, "", data=KEYED, key_field="name").status_code == 200
    changed = b"title,signed_on,authenticated\nAlien #1,2019-09,yes\n"

    response = _post(client, "/plan", data=changed, key_field="name")

    (entity,) = response.json()["entities"]
    assert entity["action"] == "unchanged"
    assert entity["matched_name"] == "Alien #1"
    assert uuid.UUID(entity["matched_id"])
    assert entity["changed"] == ["attributes.signed_on"]


async def test_restore_is_read_as_json(shared: Shared) -> None:
    """Keys to restore arrive as a JSON list and bring a deleted row back."""
    client = _with_type(shared)
    assert _post(client, "", data=KEYED, key_field="name").status_code == 200
    (node,) = await shared.graph_repos.nodes.list(
        after=None, limit=10, scope=ContentFilter.everyone()
    )
    await shared.targets(ALICE).graph.remove(EntityKind.ITEM, node.id)

    kept = _post(client, "/plan", data=KEYED, key_field="name").json()
    restored = _post(
        client, "/plan", data=KEYED, key_field="name", restore=json.dumps(["Alien #1"])
    ).json()

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
    shared: Shared,
) -> None:
    """A connection column joins each row to the person it names, made once."""
    client = _client(shared)
    assert client.post("/api/v1/bundles/import", json=CONNECT_FILE).status_code == 200
    connections = [
        {
            "column": "signer",
            "relationship_type": "signed",
            "item_type": "person",
            "row_end": "target",
        }
    ]

    plan = _post(
        client,
        "/plan",
        data=SIGNED,
        mapping=[{"column": "title", "target": "name"}],
        connections=json.dumps(connections),
    )
    response = _post(
        client,
        "",
        data=SIGNED,
        mapping=[{"column": "title", "target": "name"}],
        connections=json.dumps(connections),
    )

    kinds = [e["kind"] for e in plan.json()["entities"]]
    assert kinds.count("connection") == 2
    assert "relationship_type" not in kinds
    assert response.json() == {"items_added": 3, "connections_added": 2}


def test_an_unknown_row_end_is_a_422(shared: Shared) -> None:
    """A connection column must say which end the row is."""
    client = _with_type(shared)
    connections = [
        {
            "column": "title",
            "relationship_type": "signed",
            "item_type": "person",
            "row_end": "middle",
        }
    ]

    response = _post(client, "/plan", connections=json.dumps(connections))

    assert response.status_code == 422
