"""Router tests for /api/v1/collection over in-memory adapters."""

import uuid
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

import pytest
from starlette.testclient import TestClient

from app.entrypoints.api import create_app
from app.entrypoints.api.shared.collection_items import get_item_lookup
from app.modules.collections.adapters.api.dependencies import (
    get_collections_repos,
    get_collections_uow,
)
from app.modules.collections.adapters.persistence.in_memory_collection_repository import (  # noqa: E501
    InMemoryCollectionRepository,
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
from app.modules.collections.ports.unit_of_work import CollectionsRepos

if TYPE_CHECKING:
    from collections.abc import Callable

BASE = "/api/v1/collection"


@dataclass
class Api:
    """A test client plus the controllable item lookup behind it."""

    client: TestClient
    items: InMemoryItemLookup

    def live_item(self) -> str:
        """Mark a fresh item id live and return it."""
        item_id = uuid.uuid7()
        self.items.live.add(item_id)
        return str(item_id)

    def create(self, name: str = "Shelf", **extra: str) -> dict[str, Any]:
        """Create a collection and return its JSON body."""
        response = self.client.post(BASE, json={"name": name, **extra})
        assert response.status_code == 201
        body: dict[str, Any] = response.json()
        return body


@pytest.fixture
def api() -> Api:
    """Return an app wired to in-memory repositories and a settable item lookup."""
    app = create_app()
    repos = CollectionsRepos(
        collections=InMemoryCollectionRepository(),
        memberships=InMemoryMembershipRepository(),
    )
    items = InMemoryItemLookup()
    app.dependency_overrides[get_collections_uow] = lambda: (
        create_in_memory_collections_uow(repos)
    )
    app.dependency_overrides[get_collections_repos] = lambda: repos
    app.dependency_overrides[get_item_lookup] = lambda: items
    return Api(client=TestClient(app), items=items)


def test_create_returns_201_with_derived_slug_and_exact_body(api: Api) -> None:
    """POST creates a manual private collection with a derived slug."""
    response = api.client.post(
        BASE, json={"name": "  Weekend Watchlist ", "description": "Soon."}
    )

    assert response.status_code == 201
    body = response.json()
    assert set(body) == {
        "id",
        "name",
        "slug",
        "description",
        "kind",
        "visibility",
        "item_count",
        "created_at",
        "updated_at",
    }
    assert body["name"] == "Weekend Watchlist"
    assert body["slug"] == "weekend-watchlist"
    assert body["description"] == "Soon."
    assert body["kind"] == "manual"
    assert body["visibility"] == "private"
    assert body["item_count"] == 0
    assert api.client.get(f"{BASE}/{body['id']}").json() == body


def test_create_with_explicit_slug_and_conflict_is_409(api: Api) -> None:
    """An explicit slug is used; reusing a live slug is a 409 problem."""
    created = api.create("Films", slug="movies")
    assert created["slug"] == "movies"

    response = api.client.post(BASE, json={"name": "Other", "slug": "movies"})

    assert response.status_code == 409
    assert response.json()["title"] == "ConflictError"


def test_create_blank_name_is_rejected(api: Api) -> None:
    """A blank name is refused by the domain as a validation problem (400)."""
    response = api.client.post(BASE, json={"name": "   "})

    assert response.status_code == 400
    assert response.json()["title"] == "InvalidCollectionError"


def test_create_overlong_name_is_422(api: Api) -> None:
    """A name over 120 characters fails request validation."""
    response = api.client.post(BASE, json={"name": "x" * 121})

    assert response.status_code == 422


def test_get_returns_collection_and_404_when_unknown(api: Api) -> None:
    """GET returns the collection with an ETag; an unknown id is a 404."""
    created = api.create("Shelf")

    response = api.client.get(f"{BASE}/{created['id']}")
    missing = api.client.get(f"{BASE}/{uuid.uuid4()}")

    assert response.status_code == 200
    assert response.json() == created
    assert response.headers["ETag"].startswith('W/"')
    assert missing.status_code == 404
    assert missing.json()["title"] == "CollectionNotFoundError"


def test_get_with_matching_etag_is_304(api: Api) -> None:
    """GET with If-None-Match of the current ETag returns 304."""
    created = api.create()
    etag = api.client.get(f"{BASE}/{created['id']}").headers["ETag"]

    response = api.client.get(
        f"{BASE}/{created['id']}", headers={"If-None-Match": etag}
    )

    assert response.status_code == 304


def test_patch_changes_name_and_description_keeps_slug(api: Api) -> None:
    """PATCH renames and sets a description; the slug is untouched."""
    created = api.create("Shelf")

    response = api.client.patch(
        f"{BASE}/{created['id']}", json={"name": "Renamed", "description": "Notes"}
    )

    assert response.status_code == 200
    body = response.json()
    assert body["name"] == "Renamed"
    assert body["description"] == "Notes"
    assert body["slug"] == "shelf"
    assert body["id"] == created["id"]
    assert body["updated_at"] > created["updated_at"]
    assert response.headers["ETag"] != ""


def test_patch_blank_description_clears_it_and_omitted_is_unchanged(api: Api) -> None:
    """A blank description clears; omitting it leaves it as it was."""
    created = api.create("Shelf", description="Notes")

    unchanged = api.client.patch(f"{BASE}/{created['id']}", json={"name": "Shelf 2"})
    cleared = api.client.patch(f"{BASE}/{created['id']}", json={"description": ""})

    assert unchanged.json()["description"] == "Notes"
    assert cleared.json()["description"] is None


def test_patch_keeps_item_count(api: Api) -> None:
    """PATCH responds with the current live item count."""
    created = api.create()
    api.client.put(f"{BASE}/{created['id']}/item", json={"item_ids": [api.live_item()]})

    response = api.client.patch(f"{BASE}/{created['id']}", json={"name": "New"})

    assert response.json()["item_count"] == 1


def test_patch_if_match_current_etag_succeeds_and_stale_is_412(api: Api) -> None:
    """PATCH honours If-Match: the current ETag passes, a stale one is a 412."""
    created = api.create()
    url = f"{BASE}/{created['id']}"
    etag = api.client.get(url).headers["ETag"]

    ok = api.client.patch(url, json={"name": "One"}, headers={"If-Match": etag})
    stale = api.client.patch(url, json={"name": "Two"}, headers={"If-Match": etag})

    assert ok.status_code == 200
    assert ok.headers["ETag"] != etag
    assert stale.status_code == 412
    assert stale.headers["ETag"] == ok.headers["ETag"]
    assert api.client.get(url).json()["name"] == "One"


def test_patch_without_if_match_is_allowed(api: Api) -> None:
    """Like other entities, PATCH without a precondition header proceeds."""
    created = api.create()

    response = api.client.patch(f"{BASE}/{created['id']}", json={"name": "Free"})

    assert response.status_code == 200


def test_patch_unknown_is_404_and_blank_name_is_400(api: Api) -> None:
    """PATCH on a missing collection is 404; a blank name is a validation problem."""
    created = api.create()

    missing = api.client.patch(f"{BASE}/{uuid.uuid4()}", json={"name": "x"})
    blank = api.client.patch(f"{BASE}/{created['id']}", json={"name": " "})

    assert missing.status_code == 404
    assert blank.status_code == 400


def test_patch_rejects_slug_field(api: Api) -> None:
    """The slug cannot be changed; unknown fields are 422."""
    created = api.create()

    response = api.client.patch(f"{BASE}/{created['id']}", json={"slug": "new"})

    assert response.status_code == 422


def test_delete_returns_204_then_404_and_frees_the_slug(api: Api) -> None:
    """DELETE soft-deletes; GET is then 404 and the slug can be reused."""
    created = api.create("Shelf")

    deleted = api.client.delete(f"{BASE}/{created['id']}")
    after = api.client.get(f"{BASE}/{created['id']}")
    again = api.client.post(BASE, json={"name": "Other", "slug": "shelf"})

    assert deleted.status_code == 204
    assert deleted.content == b""
    assert after.status_code == 404
    assert again.status_code == 201
    assert api.client.delete(f"{BASE}/{created['id']}").status_code == 404


def test_list_pages_with_link_header_and_counts(api: Api) -> None:
    """GET list returns exact counts and a Link header while more pages remain."""
    first = api.create("A")
    second = api.create("B")
    third = api.create("C")
    api.client.put(
        f"{BASE}/{second['id']}/item",
        json={"item_ids": [api.live_item(), api.live_item()]},
    )

    page_one = api.client.get(BASE, params={"limit": 2})

    assert page_one.status_code == 200
    assert [c["id"] for c in page_one.json()] == [first["id"], second["id"]]
    assert [c["item_count"] for c in page_one.json()] == [0, 2]
    link = page_one.headers["Link"]
    assert 'rel="next"' in link
    assert f"after={second['id']}" in link

    page_two = api.client.get(BASE, params={"limit": 2, "after": second["id"]})

    assert [c["id"] for c in page_two.json()] == [third["id"]]
    assert "Link" not in page_two.headers


def test_list_empty_and_no_link_when_all_fit(api: Api) -> None:
    """An empty list is []; an exact fit has no Link header."""
    assert api.client.get(BASE).json() == []
    api.create("A")

    response = api.client.get(BASE, params={"limit": 1})

    assert len(response.json()) == 1
    assert "Link" not in response.headers


def test_list_item_id_filter_returns_only_shelves_holding_it(api: Api) -> None:
    """?item_id= lists only the collections that hold the item."""
    holding = api.create("Holding")
    api.create("Empty")
    item = api.live_item()
    api.client.put(f"{BASE}/{holding['id']}/item", json={"item_ids": [item]})

    response = api.client.get(BASE, params={"item_id": item})

    assert [c["id"] for c in response.json()] == [holding["id"]]
    assert response.json()[0]["item_count"] == 1


def test_list_q_returns_only_matching_collections(api: Api) -> None:
    """?q= keeps collections whose name contains the text."""
    api.create("Tapes")
    api.create("Vinyl")

    response = api.client.get(BASE, params={"q": "ta"})

    assert [c["name"] for c in response.json()] == ["Tapes"]


def test_list_whitespace_q_is_unfiltered(api: Api) -> None:
    """A whitespace-only ?q= behaves as no filter."""
    api.create("Tapes")
    api.create("Vinyl")

    response = api.client.get(BASE, params={"q": "   "})

    assert len(response.json()) == 2


def test_list_q_over_200_characters_is_422(api: Api) -> None:
    """?q= is capped at 200 characters."""
    assert api.client.get(BASE, params={"q": "a" * 201}).status_code == 422
    assert api.client.get(BASE, params={"q": "a" * 200}).status_code == 200


def test_put_items_adds_and_is_idempotent(api: Api) -> None:
    """PUT adds items and reports how many were new; repeating adds none."""
    created = api.create()
    a, b = api.live_item(), api.live_item()
    url = f"{BASE}/{created['id']}/item"

    first = api.client.put(url, json={"item_ids": [a, b, a]})
    second = api.client.put(url, json={"item_ids": [a, b]})
    third = api.client.put(url, json={"item_ids": [a, api.live_item()]})

    assert first.status_code == 200
    assert first.json() == {"added": 2}
    assert second.json() == {"added": 0}
    assert third.json() == {"added": 1}
    assert api.client.get(f"{BASE}/{created['id']}").json()["item_count"] == 3


def test_put_items_with_unknown_item_names_it_and_adds_nothing(api: Api) -> None:
    """PUT with a non-item id is refused, naming the id; the shelf is unchanged."""
    created = api.create()
    good = api.live_item()
    bad = str(uuid.uuid4())

    response = api.client.put(
        f"{BASE}/{created['id']}/item", json={"item_ids": [good, bad]}
    )

    assert response.status_code == 400
    assert response.json()["detail"] == f"Unknown or deleted items: {bad}"
    assert good not in response.json()["detail"]
    assert api.client.get(f"{BASE}/{created['id']}").json()["item_count"] == 0


def test_put_items_over_500_is_422(api: Api) -> None:
    """More than 500 ids fails request validation."""
    created = api.create()

    response = api.client.put(
        f"{BASE}/{created['id']}/item",
        json={"item_ids": [str(uuid.uuid4()) for _ in range(501)]},
    )

    assert response.status_code == 422


def test_put_items_malformed_id_is_422(api: Api) -> None:
    """A non-UUID id fails request validation."""
    created = api.create()

    response = api.client.put(
        f"{BASE}/{created['id']}/item", json={"item_ids": ["nope"]}
    )

    assert response.status_code == 422


def test_put_items_empty_list_adds_nothing(api: Api) -> None:
    """An empty id list is accepted and adds nothing."""
    created = api.create()

    response = api.client.put(f"{BASE}/{created['id']}/item", json={"item_ids": []})

    assert response.json() == {"added": 0}


def test_delete_item_removes_it_and_is_idempotent(api: Api) -> None:
    """DELETE of an item returns 204, lowers the count, and repeats safely."""
    created = api.create()
    item = api.live_item()
    api.client.put(f"{BASE}/{created['id']}/item", json={"item_ids": [item]})
    url = f"{BASE}/{created['id']}/item/{item}"

    first = api.client.delete(url)
    second = api.client.delete(url)

    assert first.status_code == 204
    assert second.status_code == 204
    assert api.client.get(f"{BASE}/{created['id']}").json()["item_count"] == 0


@pytest.mark.parametrize(
    "call",
    [
        lambda c, cid: c.put(f"{BASE}/{cid}/item", json={"item_ids": []}),
        lambda c, cid: c.delete(f"{BASE}/{cid}/item/{uuid.uuid4()}"),
    ],
    ids=["put", "delete"],
)
def test_item_endpoints_404_for_unknown_collection(
    api: Api, call: Callable[[TestClient, uuid.UUID], Any]
) -> None:
    """Both item endpoints return 404 when the collection does not exist."""
    response = call(api.client, uuid.uuid4())

    assert response.status_code == 404
    assert response.json()["title"] == "CollectionNotFoundError"


def _etag(api: Api, collection_id: str) -> str:
    """Return the collection's current ETag."""
    return api.client.get(f"{BASE}/{collection_id}").headers["ETag"]


def test_etag_changes_when_items_are_added(api: Api) -> None:
    """Adding items moves the ETag, so a stale If-None-Match gets fresh counts."""
    created = api.create()
    url = f"{BASE}/{created['id']}"
    old = _etag(api, created["id"])
    api.client.put(f"{url}/item", json={"item_ids": [api.live_item()]})

    stale = api.client.get(url, headers={"If-None-Match": old})

    assert stale.status_code == 200
    assert stale.json()["item_count"] == 1
    assert stale.headers["ETag"] != old
    current = api.client.get(url, headers={"If-None-Match": stale.headers["ETag"]})
    assert current.status_code == 304


def test_etag_changes_when_an_item_is_removed(api: Api) -> None:
    """Removing an item moves the ETag and lowers the reported count."""
    created = api.create()
    url = f"{BASE}/{created['id']}"
    item = api.live_item()
    api.client.put(f"{url}/item", json={"item_ids": [item]})
    old = _etag(api, created["id"])
    api.client.delete(f"{url}/item/{item}")

    stale = api.client.get(url, headers={"If-None-Match": old})

    assert stale.status_code == 200
    assert stale.json()["item_count"] == 0
    assert stale.headers["ETag"] != old
    current = api.client.get(url, headers={"If-None-Match": stale.headers["ETag"]})
    assert current.status_code == 304


def test_patch_with_old_if_match_after_membership_change_is_412(api: Api) -> None:
    """Intended: membership changes alter the representation, so old If-Match fails."""
    created = api.create()
    url = f"{BASE}/{created['id']}"
    old = _etag(api, created["id"])
    api.client.put(f"{url}/item", json={"item_ids": [api.live_item()]})

    response = api.client.patch(url, json={"name": "Late"}, headers={"If-Match": old})

    assert response.status_code == 412


def test_etag_changes_when_a_live_item_disappears_without_a_collection_write(
    api: Api,
) -> None:
    """An item deleted elsewhere lowers item_count, so the old ETag must not 304."""
    created = api.create()
    url = f"{BASE}/{created['id']}"
    keep, gone = api.live_item(), api.live_item()
    api.client.put(f"{url}/item", json={"item_ids": [keep, gone]})
    first = api.client.get(url)
    old = first.headers["ETag"]
    assert first.json()["item_count"] == 2
    api.items.live.discard(uuid.UUID(gone))

    stale = api.client.get(url, headers={"If-None-Match": old})

    assert stale.status_code == 200
    assert stale.json()["item_count"] == 1
    assert stale.json()["updated_at"] == first.json()["updated_at"]
    new = stale.headers["ETag"]
    assert new != old
    assert api.client.get(url, headers={"If-None-Match": new}).status_code == 304
    assert api.client.get(url, headers={"If-None-Match": old}).status_code == 200


def test_patch_etag_follows_live_item_count(api: Api) -> None:
    """PATCH checks If-Match against the count-aware ETag and returns a matching one."""
    created = api.create()
    url = f"{BASE}/{created['id']}"
    keep, gone = api.live_item(), api.live_item()
    api.client.put(f"{url}/item", json={"item_ids": [keep, gone]})
    old = _etag(api, created["id"])
    api.items.live.discard(uuid.UUID(gone))
    fresh = _etag(api, created["id"])

    stale = api.client.patch(url, json={"name": "A"}, headers={"If-Match": old})
    ok = api.client.patch(url, json={"name": "B"}, headers={"If-Match": fresh})

    assert fresh != old
    assert stale.status_code == 412
    assert stale.headers["ETag"] == fresh
    assert ok.status_code == 200
    assert ok.json()["item_count"] == 1
    assert ok.headers["ETag"] == api.client.get(url).headers["ETag"]


def test_both_validators_after_live_count_drop_gets_200_not_304(api: Api) -> None:
    """If-None-Match decides alone: a matching If-Modified-Since must not give 304."""
    created = api.create()
    url = f"{BASE}/{created['id']}"
    keep, gone = api.live_item(), api.live_item()
    api.client.put(f"{url}/item", json={"item_ids": [keep, gone]})
    first = api.client.get(url)
    old_etag, last_modified = first.headers["ETag"], first.headers["Last-Modified"]
    api.items.live.discard(uuid.UUID(gone))

    stale = api.client.get(
        url, headers={"If-None-Match": old_etag, "If-Modified-Since": last_modified}
    )

    assert stale.status_code == 200
    assert stale.json()["item_count"] == 1
    assert stale.headers["ETag"] != old_etag
    assert stale.headers["Last-Modified"] == last_modified
    current = api.client.get(
        url,
        headers={
            "If-None-Match": stale.headers["ETag"],
            "If-Modified-Since": last_modified,
        },
    )
    assert current.status_code == 304
    assert current.headers["ETag"] == stale.headers["ETag"]


def test_if_modified_since_alone_still_gives_304_when_unchanged(api: Api) -> None:
    """With only If-Modified-Since the earlier behaviour is kept."""
    created = api.create()
    url = f"{BASE}/{created['id']}"
    last_modified = api.client.get(url).headers["Last-Modified"]

    response = api.client.get(url, headers={"If-Modified-Since": last_modified})

    assert response.status_code == 304


def test_create_blank_description_is_stored_as_null(api: Api) -> None:
    """A whitespace-only description on create is stored as null."""
    created = api.create("Shelf", description="   ")

    assert created["description"] is None


@pytest.mark.parametrize("limit", [0, -1, 101])
def test_list_limit_out_of_range_is_422(api: Api, limit: int) -> None:
    """Limit must be between 1 and 100."""
    assert api.client.get(BASE, params={"limit": limit}).status_code == 422


def test_list_limit_bounds_are_accepted_and_link_is_correct(api: Api) -> None:
    """limit=1 pages one at a time; limit=100 returns everything without a Link."""
    first = api.create("A")
    second = api.create("B")

    one = api.client.get(BASE, params={"limit": 1})
    hundred = api.client.get(BASE, params={"limit": 100})

    assert [c["id"] for c in one.json()] == [first["id"]]
    assert f"after={first['id']}" in one.headers["Link"]
    assert [c["id"] for c in hundred.json()] == [first["id"], second["id"]]
    assert "Link" not in hundred.headers


def test_list_q_ignores_accents(api: Api) -> None:
    """?q=cafe finds a collection named Café."""
    api.create("Café")
    api.create("Vinyl")

    response = api.client.get(BASE, params={"q": "cafe"})

    assert [c["name"] for c in response.json()] == ["Café"]
