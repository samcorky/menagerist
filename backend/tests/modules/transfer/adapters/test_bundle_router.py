import uuid
from typing import TYPE_CHECKING, Any

from starlette.testclient import TestClient

from app.entrypoints.api import create_app
from app.entrypoints.api.shared.bridges.transfer_targets import (
    get_graph_pack_target,
    get_preset_pack_target,
)
from app.entrypoints.api.shared.dependencies import get_current_actor
from app.modules.presets.adapters.api.dependencies import get_preset_repos
from app.modules.transfer.domain.bundle import (
    BundleItemType,
    BundlePreset,
    BundleRelationshipType,
)
from app.modules.transfer.domain.entity_kind import EntityKind
from app.shared_kernel.actor import Actor

if TYPE_CHECKING:
    from fastapi import FastAPI

    from tests.modules.conftest import Shared

ALICE = Actor(id=uuid.UUID(int=0xA1), roles=frozenset({"member"}))
BOB = Actor(id=uuid.UUID(int=0xB2), roles=frozenset({"member"}))
FILE: dict[str, Any] = {
    "format": "menagerist-bundle",
    "version": 1,
    "presets": [
        {
            "ref": "grades",
            "kind": "choice_list",
            "label": "Condition grades",
            "description": None,
            "definition": {"options": ["Mint", "Good"]},
        }
    ],
}


def _client(shared: Shared, actor: Actor = ALICE) -> TestClient:
    app: FastAPI = create_app()
    targets = shared.targets(actor)
    app.dependency_overrides[get_preset_pack_target] = lambda: targets.presets
    app.dependency_overrides[get_graph_pack_target] = lambda: targets.graph
    app.dependency_overrides[get_preset_repos] = lambda: shared.preset_repos
    app.dependency_overrides[get_current_actor] = lambda: actor
    return TestClient(app)


def test_plan_import_and_export_round_trip(shared: Shared) -> None:
    """Plan, import, export, then plan the export: it is all unchanged."""
    client = _client(shared)

    plan = client.post("/api/v1/bundles/import/plan", json=FILE)
    first = client.post("/api/v1/bundles/import", json=FILE)
    second = client.post("/api/v1/bundles/import", json=FILE)
    ids = [p["id"] for p in client.get("/api/v1/presets").json()]
    exported = client.get("/api/v1/bundles/export", params={"preset_ids": ids})
    replanned = client.post("/api/v1/bundles/import/plan", json=exported.json())

    assert plan.status_code == 200
    assert plan.json() == {
        "ready": True,
        "blockers": [],
        "entities": [
            {
                "kind": "preset",
                "ref": "grades",
                "label": "Condition grades",
                "action": "create",
                "reason": None,
            }
        ],
    }
    assert first.json() == {
        "created": 1,
        "skipped": 0,
        "presets_created": 1,
        "presets_skipped": 0,
    }
    assert (second.json()["created"], second.json()["skipped"]) == (0, 1)
    assert exported.status_code == 200
    body = exported.json()
    assert (body["format"], body["version"]) == ("menagerist-bundle", 2)
    assert (body["relationship_types"], body["item_types"]) == ([], [])
    assert [p["ref"] for p in body["presets"]] == ids
    assert [e["action"] for e in replanned.json()["entities"]] == ["unchanged"]


def test_a_bad_file_is_refused_before_anything_is_made(shared: Shared) -> None:
    """An unknown format or a bad preset is a 400 problem; a missing field is 422."""
    client = _client(shared)
    mystery = {**FILE["presets"][0], "kind": "mystery"}

    unknown = client.post(
        "/api/v1/bundles/import", json={**FILE, "format": "menagerist-presets"}
    )
    invalid = client.post(
        "/api/v1/bundles/import/plan", json={**FILE, "presets": [mystery]}
    )
    incomplete = client.post(
        "/api/v1/bundles/import", json={**FILE, "presets": [{"ref": "x"}]}
    )

    assert unknown.status_code == 400
    assert unknown.json()["title"] == "UnknownFormatError"
    assert invalid.status_code == 400
    assert invalid.json()["title"] == "InvalidPresetDefinitionError"
    assert incomplete.status_code == 422
    assert client.get("/api/v1/presets").json() == []


def test_export_needs_something_to_export(shared: Shared) -> None:
    """An export with no ids is refused, and a missing id is a 404."""
    client = _client(shared)

    nothing = client.get("/api/v1/bundles/export")
    assert nothing.status_code == 400
    assert nothing.json()["title"] == "InvalidBundleError"
    missing = client.get(
        "/api/v1/bundles/export", params={"preset_ids": str(uuid.uuid7())}
    )
    assert missing.status_code == 404


_RECORD_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "condition": {
            "type": "string",
            "title": "Condition",
            "x-menagerist": {"kind": "choice", "list": {"$preset": "grades"}},
        }
    },
}


async def test_an_item_type_travels_with_the_lists_it_uses(shared: Shared) -> None:
    """Exporting a type brings its list; another person imports both, and only once."""
    alice = shared.targets(ALICE)
    preset = await alice.presets.ensure(
        [
            BundlePreset(
                ref="grades",
                kind="choice_list",
                label="Condition grades",
                definition={"options": ["Mint", "Good"]},
            )
        ]
    )
    record = await alice.graph.create_item_type(
        BundleItemType(
            ref="record",
            slug="record",
            label="Record",
            attributes_schema=_RECORD_SCHEMA,
            icon="disc",
            colour="blue",
        ),
        {"grades": preset[0].entity_id},
    )
    wrote = await alice.graph.create_relationship_type(
        BundleRelationshipType(
            ref="wrote", slug="wrote", label="Wrote", reverse_label="Written by"
        ),
        {},
    )
    list_id = str(preset[0].entity_id)

    exported = _client(shared).get(
        "/api/v1/bundles/export",
        params={
            "item_type_ids": str(record.entity_id),
            "relationship_type_ids": str(wrote.entity_id),
        },
    )

    assert exported.status_code == 200
    file = exported.json()
    assert file["version"] == 2
    assert [p["ref"] for p in file["presets"]] == [list_id]
    assert [t["ref"] for t in file["item_types"]] == [str(record.entity_id)]
    assert file["item_types"][0]["attributes_schema"]["properties"]["condition"][
        "x-menagerist"
    ]["list"] == {"$preset": list_id}
    assert file["relationship_types"][0]["reverse_label"] == "Written by"

    bob = _client(shared, BOB)
    plan = bob.post("/api/v1/bundles/import/plan", json=file)
    first = bob.post("/api/v1/bundles/import", json=file)
    second = bob.post("/api/v1/bundles/import", json=file)

    assert [(e["kind"], e["action"]) for e in plan.json()["entities"]] == [
        ("preset", "create"),
        ("relationship_type", "create"),
        ("item_type", "create"),
    ]
    assert first.json()["created"] == 3
    assert second.json()["created"] == 0
    bobs = shared.targets(BOB)
    assert await bobs.graph.slug_taken(EntityKind.ITEM_TYPE, "record")
    assert len(await bobs.presets.existing(_presets_in(file))) == 1


def _presets_in(file: dict[str, Any]) -> list[BundlePreset]:
    """The presets of an exported file, as bundle presets."""
    return [
        BundlePreset(
            ref=p["ref"], kind=p["kind"], label=p["label"], definition=p["definition"]
        )
        for p in file["presets"]
    ]
