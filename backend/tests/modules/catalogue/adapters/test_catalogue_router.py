import uuid
from typing import TYPE_CHECKING

from starlette.testclient import TestClient

from app.entrypoints.api import create_app
from app.entrypoints.api.shared.bridges.transfer_targets import (
    get_graph_pack_target,
    get_preset_pack_target,
)
from app.entrypoints.api.shared.dependencies import get_current_actor
from app.modules.catalogue.adapters.api.dependencies import get_entry_catalogue
from app.shared_kernel.actor import Actor

if TYPE_CHECKING:
    from fastapi import FastAPI

    from tests.modules.catalogue.conftest import Shared

ALICE = Actor(id=uuid.UUID(int=0xA1), roles=frozenset({"member"}))
BOB = Actor(id=uuid.UUID(int=0xB2), roles=frozenset({"member"}))


def _client(shared: Shared) -> TestClient:
    app: FastAPI = create_app()
    targets = shared.targets(ALICE)
    app.dependency_overrides[get_entry_catalogue] = lambda: shared.catalogue
    app.dependency_overrides[get_preset_pack_target] = lambda: targets.presets
    app.dependency_overrides[get_graph_pack_target] = lambda: targets.graph
    app.dependency_overrides[get_current_actor] = lambda: ALICE
    return TestClient(app)


def test_list_returns_every_entry_not_yet_installed(shared: Shared) -> None:
    """List returns every entry not yet installed."""
    response = _client(shared).get("/api/v1/catalogue")

    assert response.status_code == 200
    body = response.json()
    assert len(body) == 14
    grades = next(e for e in body if e["id"] == "condition-grades")
    assert grades["installed"] is False
    assert (grades["present"], grades["total"]) == (0, 1)
    assert grades["section"] == "choice_list"
    assert grades["contents"] == ["Condition grades"]


def test_installing_reports_counts_and_the_list_then_shows_it(shared: Shared) -> None:
    """Installing reports counts and the list then shows it."""
    client = _client(shared)

    put = client.put("/api/v1/catalogue/condition-grades/installation")
    again = client.put("/api/v1/catalogue/condition-grades/installation")
    listed = client.get("/api/v1/catalogue").json()

    assert put.status_code == 200
    assert put.json()["presets_created"] == 1
    assert again.json()["presets_created"] == 0
    assert again.json()["presets_skipped"] == 1
    assert next(e for e in listed if e["id"] == "condition-grades")["installed"] is True


def test_an_unknown_entry_is_a_404_problem(shared: Shared) -> None:
    """An unknown entry is a 404 problem."""
    response = _client(shared).put("/api/v1/catalogue/nope/installation")

    assert response.status_code == 404
    assert response.headers["content-type"].startswith("application/problem+json")
