"""Router tests for smart collections on /api/v1/collection over in-memory adapters."""

import uuid
from dataclasses import dataclass
from datetime import datetime
from types import SimpleNamespace
from typing import Any

import pytest
from starlette.testclient import TestClient

from app.entrypoints.api import create_app
from app.entrypoints.api.shared.bridges.collection_definitions import (
    get_definition_checker,
)
from app.entrypoints.api.shared.bridges.collection_items import get_item_lookup
from app.modules.collections.adapters.api.dependencies import (
    get_collections_repos,
    get_collections_uow,
)
from app.modules.collections.adapters.persistence.in_memory_collection_repository import (  # noqa: E501
    InMemoryCollectionRepository,
)
from app.modules.collections.adapters.persistence.in_memory_definition_checker import (
    InMemoryDefinitionChecker,
)
from app.modules.collections.adapters.persistence.in_memory_item_lookup import (
    InMemoryItemLookup,
)
from app.modules.collections.adapters.persistence.in_memory_membership_repository import (  # noqa: E501
    InMemoryMembershipRepository,
)
from app.modules.collections.adapters.persistence.unit_of_work import (
    create_in_memory_collections_uow,
)
from app.modules.collections.application.get_collection import ITEM_COUNT_CAP
from app.modules.collections.domain.definition_warning import DefinitionWarning
from app.modules.collections.ports.unit_of_work import CollectionsRepos
from app.shared_kernel.etag import etag_from_entity

BASE = "/api/v1/collection"
DEFINITION: dict[str, Any] = {
    "v": 1,
    "where": {
        "op": "or",
        "children": [
            {"kind": "text", "q": "alien"},
            {"kind": "field", "type": "film", "key": "rating", "op": ">=", "value": 4},
        ],
    },
    "sort": [{"by": "name", "dir": "desc"}],
}


@dataclass
class Api:
    """A test client plus the controllable lookup and checker behind it."""

    client: TestClient
    items: InMemoryItemLookup
    checker: InMemoryDefinitionChecker

    def live_items(self, count: int) -> None:
        """Mark `count` fresh item ids live."""
        self.items.live.update(uuid.uuid7() for _ in range(count))

    def smart(self, name: str = "Aliens") -> dict[str, Any]:
        """Create a smart collection and return its JSON body."""
        response = self.client.post(BASE, json={"name": name, "definition": DEFINITION})
        assert response.status_code == 201, response.text
        body: dict[str, Any] = response.json()
        return body


@pytest.fixture
def api() -> Api:
    """Return an app wired to in-memory repositories, item lookup and checker."""
    app = create_app()
    collections = InMemoryCollectionRepository()
    repos = CollectionsRepos(
        collections=collections,
        memberships=InMemoryMembershipRepository(collections),
    )
    items = InMemoryItemLookup()
    checker = InMemoryDefinitionChecker()
    app.dependency_overrides[get_collections_uow] = lambda: (
        create_in_memory_collections_uow(repos)
    )
    app.dependency_overrides[get_collections_repos] = lambda: repos
    app.dependency_overrides[get_item_lookup] = lambda: items
    app.dependency_overrides[get_definition_checker] = lambda: checker
    return Api(client=TestClient(app), items=items, checker=checker)


def test_create_with_a_definition_is_a_smart_collection(api: Api) -> None:
    """POST with a definition gives kind dynamic, the definition as sent and a count."""
    api.live_items(3)

    body = api.smart()

    assert body["kind"] == "dynamic"
    assert body["definition"] == DEFINITION
    assert body["item_count"] == 3
    assert body["item_count_capped"] is False
    assert body["warnings"] == []
    assert api.client.get(f"{BASE}/{body['id']}").json() == body


def test_a_manual_collection_has_no_definition(api: Api) -> None:
    """Without a definition the collection is manual and shows none."""
    body = api.client.post(BASE, json={"name": "Shelf"}).json()

    assert body["kind"] == "manual"
    assert body["definition"] is None
    assert body["item_count_capped"] is False
    assert body["warnings"] == []


def test_create_with_an_invalid_definition_is_400_with_the_path(api: Api) -> None:
    """A malformed definition is refused with the path of the problem."""
    response = api.client.post(
        BASE, json={"name": "Bad", "definition": {"v": 1, "where": "all"}}
    )

    assert response.status_code == 400
    assert response.json()["title"] == "InvalidDefinitionError"
    assert response.json()["detail"].startswith("where: ")
    assert api.client.get(BASE).json() == []


def test_definition_must_be_an_object(api: Api) -> None:
    """A definition that is not a JSON object fails request validation."""
    response = api.client.post(BASE, json={"name": "Bad", "definition": [1]})

    assert response.status_code == 422


def test_patch_replaces_the_definition(api: Api) -> None:
    """PATCH stores the new definition as sent and returns the fresh count."""
    created = api.smart()
    api.live_items(2)
    replacement = {"v": 1, "where": None}

    response = api.client.patch(
        f"{BASE}/{created['id']}", json={"definition": replacement}
    )

    assert response.status_code == 200
    assert response.json()["definition"] == replacement
    assert response.json()["kind"] == "dynamic"
    assert response.json()["item_count"] == 2
    assert (
        response.headers["ETag"]
        == (api.client.get(f"{BASE}/{created['id']}").headers["ETag"])
    )


def test_patch_with_an_invalid_definition_is_400(api: Api) -> None:
    """An invalid replacement is refused and the stored one kept."""
    created = api.smart()

    response = api.client.patch(
        f"{BASE}/{created['id']}", json={"definition": {"v": 1, "where": 3}}
    )

    assert response.status_code == 400
    assert response.json()["detail"].startswith("where: ")
    assert api.client.get(f"{BASE}/{created['id']}").json()["definition"] == (
        DEFINITION
    )


def test_patch_definition_on_a_manual_collection_is_409(api: Api) -> None:
    """The kind is fixed at creation: a manual collection takes no definition."""
    created = api.client.post(BASE, json={"name": "Shelf"}).json()

    response = api.client.patch(
        f"{BASE}/{created['id']}", json={"definition": DEFINITION}
    )

    assert response.status_code == 409
    assert response.json()["title"] == "CollectionKindError"


def test_adding_or_removing_items_on_a_smart_collection_is_409(api: Api) -> None:
    """Membership of a smart collection follows its definition, not edits."""
    created = api.smart()
    item = uuid.uuid7()
    api.items.live.add(item)
    url = f"{BASE}/{created['id']}/item"

    added = api.client.put(url, json={"item_ids": [str(item)]})
    removed = api.client.delete(f"{url}/{item}")

    assert added.status_code == 409
    assert added.headers["content-type"] == "application/problem+json"
    assert added.json()["title"] == "CollectionKindError"
    assert removed.status_code == 409
    assert removed.json()["title"] == "CollectionKindError"


def test_get_shows_stale_warnings(api: Api) -> None:
    """GET lists the parts of the definition that no longer apply."""
    created = api.smart()
    api.checker.warnings = [
        DefinitionWarning(path="where.children[1]", message="The field was removed.")
    ]

    body = api.client.get(f"{BASE}/{created['id']}").json()

    assert body["warnings"] == [
        {"path": "where.children[1]", "message": "The field was removed."}
    ]


def test_list_shows_capped_counts_and_no_warnings(api: Api) -> None:
    """The list carries the capped count and flag, but leaves warnings to GET."""
    api.smart()
    api.live_items(ITEM_COUNT_CAP + 1)
    api.checker.warnings = [DefinitionWarning(path="where", message="Gone.")]

    [listed] = api.client.get(BASE).json()

    assert listed["item_count"] == ITEM_COUNT_CAP
    assert listed["item_count_capped"] is True
    assert listed["warnings"] == []


def _etag(api: Api, collection_id: str) -> str:
    return api.client.get(f"{BASE}/{collection_id}").headers["ETag"]


def test_etag_changes_when_an_item_starts_matching(api: Api) -> None:
    """A newly matching item moves the ETag without a collection write."""
    created = api.smart()
    url = f"{BASE}/{created['id']}"
    old = _etag(api, created["id"])
    api.live_items(1)

    stale = api.client.get(url, headers={"If-None-Match": old})

    assert stale.status_code == 200
    assert stale.json()["item_count"] == 1
    assert stale.json()["updated_at"] == created["updated_at"]
    assert stale.headers["ETag"] != old
    current = api.client.get(url, headers={"If-None-Match": stale.headers["ETag"]})
    assert current.status_code == 304


def test_etag_changes_when_a_used_field_goes_stale(api: Api) -> None:
    """Archiving or deleting a used field moves the ETag at the same count."""
    created = api.smart()
    api.live_items(2)
    before = api.client.get(f"{BASE}/{created['id']}")
    api.checker.warnings = [
        DefinitionWarning(path="where.children[1]", message="The field was removed.")
    ]

    after = api.client.get(f"{BASE}/{created['id']}")

    assert after.json()["item_count"] == before.json()["item_count"] == 2
    assert after.json()["updated_at"] == before.json()["updated_at"]
    assert after.headers["ETag"] != before.headers["ETag"]


def test_etag_ignores_the_order_of_warnings(api: Api) -> None:
    """The same warnings in another order give the same ETag."""
    created = api.smart()
    one = DefinitionWarning(path="where.children[0]", message="A")
    two = DefinitionWarning(path="where.children[1]", message="B")
    api.checker.warnings = [one, two]
    first = _etag(api, created["id"])
    api.checker.warnings = [two, one]

    assert _etag(api, created["id"]) == first


def test_etag_is_stable_above_the_cap(api: Api) -> None:
    """Above the cap the body does not change, and neither does the ETag."""
    created = api.smart()
    api.live_items(ITEM_COUNT_CAP + 1)
    at_cap_plus_one = api.client.get(f"{BASE}/{created['id']}")
    api.live_items(4)

    at_cap_plus_five = api.client.get(f"{BASE}/{created['id']}")

    assert at_cap_plus_one.json() == at_cap_plus_five.json()
    assert at_cap_plus_one.json()["item_count_capped"] is True
    assert at_cap_plus_one.headers["ETag"] == at_cap_plus_five.headers["ETag"]


def test_etag_differs_at_the_cap_once_capped(api: Api) -> None:
    """Exactly the cap and more than the cap show different bodies and ETags."""
    created = api.smart()
    api.live_items(ITEM_COUNT_CAP)
    exact = _etag(api, created["id"])
    api.live_items(1)

    assert _etag(api, created["id"]) != exact


def test_manual_etag_is_unchanged(api: Api) -> None:
    """A manual collection's ETag is still built from its id, time and count."""
    created = api.client.post(BASE, json={"name": "Shelf"}).json()
    entity = SimpleNamespace(
        id=uuid.UUID(created["id"]),
        updated_at=datetime.fromisoformat(created["updated_at"]),
    )

    response = api.client.get(f"{BASE}/{created['id']}")

    assert response.headers["ETag"] == etag_from_entity(entity, "0")
    assert "Last-Modified" in response.headers


def test_smart_collection_ignores_if_modified_since(api: Api) -> None:
    """updated_at does not cover a smart collection's count, so no 304 on dates."""
    created = api.smart()
    first = api.client.get(f"{BASE}/{created['id']}")
    api.live_items(1)

    response = api.client.get(
        f"{BASE}/{created['id']}",
        headers={"If-Modified-Since": first.headers["Last-Modified"]},
    )

    assert response.status_code == 200
    assert response.json()["item_count"] == 1


def test_patch_if_match_uses_the_smart_etag(api: Api) -> None:
    """PATCH checks If-Match against the count- and warning-aware ETag."""
    created = api.smart()
    url = f"{BASE}/{created['id']}"
    old = _etag(api, created["id"])
    api.checker.warnings = [DefinitionWarning(path="where", message="Gone.")]
    fresh = _etag(api, created["id"])

    stale = api.client.patch(url, json={"name": "A"}, headers={"If-Match": old})
    ok = api.client.patch(url, json={"name": "B"}, headers={"If-Match": fresh})

    assert stale.status_code == 412
    assert stale.headers["ETag"] == fresh
    assert ok.status_code == 200
    assert ok.headers["ETag"] == api.client.get(url).headers["ETag"]


def test_smart_collection_resolves_by_slug_and_edits_its_slug(api: Api) -> None:
    """A smart collection is found by slug, and its slug can change."""
    created = api.smart("Smart")

    got = api.client.get(f"{BASE}/smart")
    patched = api.client.patch(f"{BASE}/smart", json={"slug": "clever"})

    assert got.json()["id"] == created["id"]
    assert got.json()["kind"] == "dynamic"
    assert patched.json()["slug"] == "clever"
    assert api.client.get(f"{BASE}/clever").status_code == 200
    assert api.client.get(f"{BASE}/smart").status_code == 404
