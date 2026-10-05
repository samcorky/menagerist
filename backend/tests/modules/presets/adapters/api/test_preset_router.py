import uuid
from typing import TYPE_CHECKING

from starlette.testclient import TestClient

from app.entrypoints.api import create_app
from app.entrypoints.api.shared.preset_usage import GraphPresetUsage, get_preset_usage
from app.modules.presets.adapters.api.dependencies import (
    get_preset_repos,
    get_preset_uow,
)
from app.modules.presets.adapters.persistence.in_memory_preset_repository import (
    InMemoryPresetRepository,
)
from app.modules.presets.adapters.persistence.unit_of_work import (
    create_in_memory_preset_uow,
)
from app.modules.presets.domain.preset import Preset
from app.modules.presets.ports.unit_of_work import PresetRepos

if TYPE_CHECKING:
    from fastapi import FastAPI


class _NoUsage(GraphPresetUsage):
    """Reports that no item type links to any list, without touching the graph."""

    def __init__(self) -> None:
        pass

    async def types_using(self, preset_id: uuid.UUID) -> list[str]:
        return []


def _app_with_in_memory_presets() -> FastAPI:
    """Build the app with the presets module wired to a fresh in-memory repository."""
    app = create_app()
    repos = PresetRepos(presets=InMemoryPresetRepository())
    app.dependency_overrides[get_preset_uow] = lambda: create_in_memory_preset_uow(
        repos
    )
    app.dependency_overrides[get_preset_repos] = lambda: repos
    app.dependency_overrides[get_preset_usage] = _NoUsage
    return app


def test_create_get_list_and_404_round_trip() -> None:
    """A preset created via the API can be fetched and listed; a miss is 404."""
    client = TestClient(_app_with_in_memory_presets())

    create_response = client.post(
        "/api/v1/preset",
        json={
            "kind": "field",
            "label": "Condition",
            "definition": {"property": {"type": "string"}},
        },
    )
    assert create_response.status_code == 201
    preset = create_response.json()
    assert preset["kind"] == "field"
    assert preset["label"] == "Condition"
    assert preset["version"] == 1
    assert preset["builtin"] is False

    get_response = client.get(f"/api/v1/preset/{preset['id']}")
    assert get_response.status_code == 200
    assert get_response.json() == preset

    list_response = client.get("/api/v1/preset")
    assert list_response.status_code == 200
    assert preset in list_response.json()

    missing_response = client.get(f"/api/v1/preset/{uuid.uuid4()}")
    assert missing_response.status_code == 404
    assert missing_response.json()["title"] == "PresetNotFoundError"


def test_create_preset_returns_400_on_a_malformed_definition() -> None:
    """POST with a definition that fails the shape check returns 400."""
    client = TestClient(_app_with_in_memory_presets())

    response = client.post(
        "/api/v1/preset", json={"kind": "field", "label": "Condition", "definition": {}}
    )

    assert response.status_code == 400


def test_list_presets_filters_by_kind_and_q() -> None:
    """`kind` and `q` query params narrow the listing."""
    client = TestClient(_app_with_in_memory_presets())
    client.post(
        "/api/v1/preset",
        json={
            "kind": "field",
            "label": "Condition",
            "definition": {"property": {"type": "string"}},
        },
    )
    client.post(
        "/api/v1/preset",
        json={
            "kind": "choice_list",
            "label": "Grades",
            "definition": {"options": ["Mint"]},
        },
    )

    by_kind = client.get("/api/v1/preset", params={"kind": "choice_list"}).json()
    assert [p["label"] for p in by_kind] == ["Grades"]

    by_q = client.get("/api/v1/preset", params={"q": "condition"}).json()
    assert [p["label"] for p in by_q] == ["Condition"]


def test_update_preset_bumps_version_and_returns_404_when_missing() -> None:
    """PATCH bumps version on a definition change; a missing id is 404."""
    client = TestClient(_app_with_in_memory_presets())
    preset = client.post(
        "/api/v1/preset",
        json={
            "kind": "field",
            "label": "Condition",
            "definition": {"property": {"type": "string"}},
        },
    ).json()

    update_response = client.patch(
        f"/api/v1/preset/{preset['id']}",
        json={"definition": {"property": {"type": "number"}}},
    )
    assert update_response.status_code == 200
    assert update_response.json()["version"] == 2

    missing_response = client.patch(
        f"/api/v1/preset/{uuid.uuid4()}", json={"label": "X"}
    )
    assert missing_response.status_code == 404


async def test_update_preset_returns_409_for_a_builtin_preset() -> None:
    """PATCH on a built-in preset is rejected with 409."""
    repos = PresetRepos(presets=InMemoryPresetRepository())
    builtin = Preset.create(
        kind="field",
        label="Country",
        definition={"property": {"type": "string"}},
        builtin=True,
    )
    await repos.presets.add(builtin)
    app = create_app()
    app.dependency_overrides[get_preset_uow] = lambda: create_in_memory_preset_uow(
        repos
    )
    app.dependency_overrides[get_preset_repos] = lambda: repos
    client = TestClient(app)

    response = client.patch(f"/api/v1/preset/{builtin.id}", json={"label": "X"})

    assert response.status_code == 409


def test_delete_preset_then_get_and_list_no_longer_find_it() -> None:
    """DELETE removes the preset from GET and list results."""
    client = TestClient(_app_with_in_memory_presets())
    preset = client.post(
        "/api/v1/preset",
        json={
            "kind": "field",
            "label": "Condition",
            "definition": {"property": {"type": "string"}},
        },
    ).json()

    delete_response = client.delete(f"/api/v1/preset/{preset['id']}")
    assert delete_response.status_code == 204

    assert client.get(f"/api/v1/preset/{preset['id']}").status_code == 404
    assert preset not in client.get("/api/v1/preset").json()


def test_delete_preset_returns_404_when_missing() -> None:
    """DELETE on a nonexistent preset returns 404."""
    client = TestClient(_app_with_in_memory_presets())

    response = client.delete(f"/api/v1/preset/{uuid.uuid4()}")

    assert response.status_code == 404


def test_export_then_import_into_a_fresh_store_reproduces_the_presets() -> None:
    """A pack exported from one store imports into another and dedupes on repeat."""
    source = TestClient(_app_with_in_memory_presets())
    created = source.post(
        "/api/v1/preset",
        json={
            "kind": "choice_list",
            "label": "Condition grades",
            "definition": {"options": ["Mint", "Good"]},
        },
    ).json()

    export = source.get("/api/v1/preset/export", params={"ids": created["id"]})
    assert export.status_code == 200
    pack = export.json()
    assert pack["format"] == "menagerist-presets"
    assert pack["version"] == 1
    assert pack["items"] == [
        {
            "kind": "choice_list",
            "label": "Condition grades",
            "description": None,
            "definition": {"options": ["Mint", "Good"]},
        }
    ]

    target = TestClient(_app_with_in_memory_presets())
    first = target.post("/api/v1/preset/import", json=pack)
    assert first.status_code == 200
    assert first.json() == {"created": 1, "skipped": 0}
    second = target.post("/api/v1/preset/import", json=pack)
    assert second.json() == {"created": 0, "skipped": 1}


def test_export_of_a_missing_id_is_404() -> None:
    """Exporting an id that is not stored returns 404."""
    client = TestClient(_app_with_in_memory_presets())

    response = client.get("/api/v1/preset/export", params={"ids": str(uuid.uuid7())})

    assert response.status_code == 404


def test_export_requires_at_least_one_id() -> None:
    """An export with no ids is rejected rather than returning an empty pack."""
    client = TestClient(_app_with_in_memory_presets())

    assert client.get("/api/v1/preset/export").status_code == 422


def test_import_rejects_an_unknown_format() -> None:
    """A body that is not a menagerist-presets pack is refused with 400."""
    client = TestClient(_app_with_in_memory_presets())

    response = client.post(
        "/api/v1/preset/import", json={"format": "other", "version": 1, "items": []}
    )

    assert response.status_code == 400
