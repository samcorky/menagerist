import uuid
from typing import TYPE_CHECKING, Any
from urllib.parse import parse_qs, urlparse

import pytest
from starlette.testclient import TestClient

from app.entrypoints.api import create_app
from app.entrypoints.api.shared.bridges.preset_usage import (
    GraphPresetUsage,
    get_preset_usage,
)
from app.modules.presets.adapters.api.dependencies import (
    get_preset_repos,
    get_preset_uow,
)
from app.modules.presets.adapters.api.preset.schemas import PresetResponse
from app.modules.presets.adapters.persistence.in_memory_preset_repository import (
    InMemoryPresetRepository,
)
from app.modules.presets.adapters.persistence.unit_of_work import (
    create_in_memory_preset_uow,
)
from app.modules.presets.application.list_presets import PresetSort
from app.modules.presets.ports.unit_of_work import PresetRepos

if TYPE_CHECKING:
    from collections.abc import Callable

    from fastapi import FastAPI


OWNER = uuid.uuid7()


class _NoUsage(GraphPresetUsage):
    """Reports that no item type links to any list, without touching the graph."""

    def __init__(self) -> None:
        pass

    async def types_using(self, preset_id: uuid.UUID) -> list[str]:
        return []


def _app_with_in_memory_presets(repos: PresetRepos | None = None) -> FastAPI:
    """Build the app with the presets module wired to an in-memory repository."""
    app = create_app()
    repos = repos or PresetRepos(presets=InMemoryPresetRepository())
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
        "/api/v1/presets",
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
    assert "builtin" not in preset

    get_response = client.get(f"/api/v1/presets/{preset['id']}")
    assert get_response.status_code == 200
    assert get_response.json() == preset

    list_response = client.get("/api/v1/presets")
    assert list_response.status_code == 200
    assert preset in list_response.json()

    missing_response = client.get(f"/api/v1/presets/{uuid.uuid4()}")
    assert missing_response.status_code == 404
    assert missing_response.json()["title"] == "PresetNotFoundError"


def test_create_preset_returns_400_on_a_malformed_definition() -> None:
    """POST with a definition that fails the shape check returns 400."""
    client = TestClient(_app_with_in_memory_presets())

    response = client.post(
        "/api/v1/presets",
        json={"kind": "field", "label": "Condition", "definition": {}},
    )

    assert response.status_code == 400


def test_list_presets_filters_by_kind_and_q() -> None:
    """`kind` and `q` query params narrow the listing."""
    client = TestClient(_app_with_in_memory_presets())
    client.post(
        "/api/v1/presets",
        json={
            "kind": "field",
            "label": "Condition",
            "definition": {"property": {"type": "string"}},
        },
    )
    client.post(
        "/api/v1/presets",
        json={
            "kind": "choice_list",
            "label": "Grades",
            "definition": {"options": ["Mint"]},
        },
    )

    by_kind = client.get("/api/v1/presets", params={"kind": "choice_list"}).json()
    assert [p["label"] for p in by_kind] == ["Grades"]

    by_q = client.get("/api/v1/presets", params={"q": "condition"}).json()
    assert [p["label"] for p in by_q] == ["Condition"]


def test_update_preset_bumps_version_and_returns_404_when_missing() -> None:
    """PATCH bumps version on a definition change; a missing id is 404."""
    client = TestClient(_app_with_in_memory_presets())
    preset = client.post(
        "/api/v1/presets",
        json={
            "kind": "field",
            "label": "Condition",
            "definition": {"property": {"type": "string"}},
        },
    ).json()

    update_response = client.patch(
        f"/api/v1/presets/{preset['id']}",
        json={"definition": {"property": {"type": "number"}}},
    )
    assert update_response.status_code == 200
    assert update_response.json()["version"] == 2

    missing_response = client.patch(
        f"/api/v1/presets/{uuid.uuid4()}", json={"label": "X"}
    )
    assert missing_response.status_code == 404


def test_delete_preset_then_get_and_list_no_longer_find_it() -> None:
    """DELETE removes the preset from GET and list results."""
    client = TestClient(_app_with_in_memory_presets())
    preset = client.post(
        "/api/v1/presets",
        json={
            "kind": "field",
            "label": "Condition",
            "definition": {"property": {"type": "string"}},
        },
    ).json()

    delete_response = client.delete(f"/api/v1/presets/{preset['id']}")
    assert delete_response.status_code == 204

    assert client.get(f"/api/v1/presets/{preset['id']}").status_code == 404
    assert preset not in client.get("/api/v1/presets").json()


def test_delete_preset_returns_404_when_missing() -> None:
    """DELETE on a nonexistent preset returns 404."""
    client = TestClient(_app_with_in_memory_presets())

    response = client.delete(f"/api/v1/presets/{uuid.uuid4()}")

    assert response.status_code == 404


def test_presets_are_private_to_their_owner(as_user: Callable[..., None]) -> None:
    """A second person cannot see, change or delete the first's preset."""
    repos = PresetRepos(presets=InMemoryPresetRepository())
    alice_app, bob_app = (_app_with_in_memory_presets(repos) for _ in range(2))
    as_user(alice_app, uuid.uuid7())
    as_user(bob_app, uuid.uuid7())
    alice, bob = TestClient(alice_app), TestClient(bob_app)
    created = alice.post(
        "/api/v1/presets",
        json={
            "kind": "choice_list",
            "label": "Grades",
            "definition": {"options": ["Mint"]},
        },
    ).json()
    url = f"/api/v1/presets/{created['id']}"

    assert bob.get(url).status_code == 404
    assert bob.get("/api/v1/presets").json() == []
    assert bob.patch(url, json={"label": "X"}).status_code == 404
    assert bob.delete(url).status_code == 404
    assert alice.get(url).json()["label"] == "Grades"


def _create(client: TestClient, label: str, kind: str = "field") -> dict[str, Any]:
    """Create a saved field or choice list and return its response body."""
    definition: dict[str, Any] = (
        {"options": ["Mint"]}
        if kind == "choice_list"
        else {"property": {"type": "string"}}
    )
    response = client.post(
        "/api/v1/presets",
        json={"kind": kind, "label": label, "definition": definition},
    )
    assert response.status_code == 201
    body: dict[str, Any] = response.json()
    return body


def _next_after(link: str) -> str:
    """The `after` cursor a `Link` header value points to."""
    url = link[link.index("<") + 1 : link.index(">")]
    return parse_qs(urlparse(url).query)["after"][0]


@pytest.mark.parametrize("order", ["asc", "desc"])
@pytest.mark.parametrize("sort", [key.value for key in PresetSort])
def test_list_walks_every_sort_key_to_the_end_in_order(sort: str, order: str) -> None:
    """Following `Link` visits each preset once, in the order the key gives."""
    client = TestClient(_app_with_in_memory_presets())
    labels = ["b", "A", "b", "c", "B", "a", "c"]
    created = [
        _create(client, label, "choice_list" if n % 2 else "field")
        for n, label in enumerate(labels)
    ]
    base = "/api/v1/presets"
    everything = client.get(
        base, params={"sort": sort, "order": order, "limit": 100}
    ).json()

    seen: list[dict[str, Any]] = []
    params: dict[str, Any] = {"sort": sort, "order": order, "limit": 2}
    while True:
        response = client.get(base, params=params)
        seen.extend(response.json())
        if "Link" not in response.headers:
            break
        params = {**params, "after": _next_after(response.headers["Link"])}

    assert [p["id"] for p in seen] == [p["id"] for p in everything]
    assert {p["id"] for p in seen} == {p["id"] for p in created}
    assert len(seen) == len(created)

    def key(preset: dict[str, Any]) -> str:
        value: str = preset[sort]
        return value.lower() if sort in {"label", "kind"} else value

    values = [key(p) for p in seen]
    assert values == sorted(values, reverse=order == "desc")


def test_the_sort_keys_a_route_declares_are_fields_of_the_preset() -> None:
    """The enum's keys are names in the response, so a client sorts by what it sees."""
    assert {key.value for key in PresetSort} <= set(PresetResponse.model_fields)


def test_list_q_ignores_case_and_accents() -> None:
    """`q=cafe` finds a saved field labelled Café."""
    client = TestClient(_app_with_in_memory_presets())
    _create(client, "Café au lait")
    _create(client, "Tea")

    found = client.get("/api/v1/presets", params={"q": "CAFE"}).json()

    assert [p["label"] for p in found] == ["Café au lait"]


def test_list_a_cursor_from_another_sort_is_a_400() -> None:
    """A label-sorted cursor does not resume an id-ordered list."""
    client = TestClient(_app_with_in_memory_presets())
    _create(client, "A")
    _create(client, "B")
    first = client.get("/api/v1/presets", params={"sort": "label", "limit": 1})

    response = client.get(
        "/api/v1/presets", params={"after": _next_after(first.headers["Link"])}
    )

    assert response.status_code == 400
    assert client.get("/api/v1/presets", params={"after": "nope"}).status_code == 400
