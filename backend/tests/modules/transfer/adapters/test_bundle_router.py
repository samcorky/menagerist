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
from app.shared_kernel.actor import Actor

if TYPE_CHECKING:
    from fastapi import FastAPI

    from tests.modules.conftest import Shared

ALICE = Actor(id=uuid.UUID(int=0xA1), roles=frozenset({"member"}))
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


def _client(shared: Shared) -> TestClient:
    app: FastAPI = create_app()
    targets = shared.targets(ALICE)
    app.dependency_overrides[get_preset_pack_target] = lambda: targets.presets
    app.dependency_overrides[get_graph_pack_target] = lambda: targets.graph
    app.dependency_overrides[get_preset_repos] = lambda: shared.preset_repos
    app.dependency_overrides[get_current_actor] = lambda: ALICE
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
    assert (body["format"], body["version"]) == ("menagerist-bundle", 1)
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


def test_export_needs_at_least_one_preset(shared: Shared) -> None:
    """An export with no ids is a request error, and a missing id is a 404."""
    client = _client(shared)

    assert client.get("/api/v1/bundles/export").status_code == 422
    missing = client.get(
        "/api/v1/bundles/export", params={"preset_ids": str(uuid.uuid7())}
    )
    assert missing.status_code == 404
