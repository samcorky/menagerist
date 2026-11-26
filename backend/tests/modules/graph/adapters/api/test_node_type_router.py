import uuid
from typing import TYPE_CHECKING

from starlette.testclient import TestClient

from app.entrypoints.api import create_app
from app.entrypoints.api.shared.dependencies import get_current_actor
from app.modules.graph.adapters.api.dependencies import get_graph_repos, get_graph_uow
from app.modules.graph.adapters.persistence.in_memory_edge_repository import (
    InMemoryEdgeRepository,
)
from app.modules.graph.adapters.persistence.in_memory_edge_type_repository import (
    InMemoryEdgeTypeRepository,
)
from app.modules.graph.adapters.persistence.in_memory_node_repository import (
    InMemoryNodeRepository,
)
from app.modules.graph.adapters.persistence.in_memory_node_type_repository import (
    InMemoryNodeTypeRepository,
)
from app.modules.graph.adapters.persistence.unit_of_work import (
    create_in_memory_graph_uow,
)
from app.modules.graph.ports.unit_of_work import GraphRepos
from app.shared_kernel.actor import Actor

if TYPE_CHECKING:
    from fastapi import FastAPI


def _app_with_in_memory_graph() -> FastAPI:
    app = create_app()
    repos = GraphRepos(
        nodes=InMemoryNodeRepository(),
        edges=InMemoryEdgeRepository(),
        node_types=InMemoryNodeTypeRepository(),
        edge_types=InMemoryEdgeTypeRepository(),
    )
    app.dependency_overrides[get_graph_uow] = lambda: create_in_memory_graph_uow(repos)
    app.dependency_overrides[get_graph_repos] = lambda: repos
    return app


def _admin_client() -> TestClient:
    """A client acting as an administrator (structure deletes are admin-only)."""
    app = _app_with_in_memory_graph()
    actor = Actor(id=uuid.UUID(int=1), roles=frozenset({"admin"}))
    app.dependency_overrides[get_current_actor] = lambda: actor
    return TestClient(app)


def test_create_get_list_and_404_round_trip() -> None:
    """A node type created via the API can be fetched and listed; a miss is 404."""
    client = TestClient(_app_with_in_memory_graph())

    create_response = client.post(
        "/api/v1/node-types",
        json={"slug": "film", "label": "Film", "description": "Motion pictures"},
    )
    assert create_response.status_code == 201
    nt = create_response.json()
    assert nt["slug"] == "film"
    assert nt["label"] == "Film"
    assert nt["description"] == "Motion pictures"

    get_response = client.get(f"/api/v1/node-types/{nt['id']}")
    assert get_response.status_code == 200
    assert get_response.json() == nt

    list_response = client.get("/api/v1/node-types")
    assert list_response.status_code == 200
    assert nt in list_response.json()

    missing_response = client.get(f"/api/v1/node-types/{uuid.uuid4()}")
    assert missing_response.status_code == 404
    assert missing_response.json()["title"] == "NodeTypeNotFoundError"


def test_create_node_type_returns_409_on_slug_conflict() -> None:
    """POST with a duplicate slug returns 409."""
    client = TestClient(_app_with_in_memory_graph())
    client.post("/api/v1/node-types", json={"slug": "film", "label": "Film"})

    response = client.post(
        "/api/v1/node-types", json={"slug": "film", "label": "Duplicate"}
    )

    assert response.status_code == 409


def test_update_node_type_applies_changes() -> None:
    """PATCH updates the label and leaves slug unchanged."""
    client = TestClient(_app_with_in_memory_graph())
    nt = client.post(
        "/api/v1/node-types", json={"slug": "film", "label": "Film"}
    ).json()

    update_response = client.patch(
        f"/api/v1/node-types/{nt['id']}", json={"label": "Movie"}
    )

    assert update_response.status_code == 200
    updated = update_response.json()
    assert updated["label"] == "Movie"
    assert updated["slug"] == "film"


def test_update_node_type_returns_404_when_missing() -> None:
    """PATCH on a nonexistent node type returns 404."""
    client = TestClient(_app_with_in_memory_graph())

    response = client.patch(
        f"/api/v1/node-types/{uuid.uuid4()}", json={"label": "Ghost"}
    )

    assert response.status_code == 404


def test_delete_node_type_then_get_returns_404() -> None:
    """DELETE soft-deletes the node type; subsequent GET returns 404."""
    client = _admin_client()
    nt = client.post(
        "/api/v1/node-types", json={"slug": "film", "label": "Film"}
    ).json()

    delete_response = client.delete(f"/api/v1/node-types/{nt['id']}")
    assert delete_response.status_code == 204

    assert client.get(f"/api/v1/node-types/{nt['id']}").status_code == 404
    assert nt not in client.get("/api/v1/node-types").json()


def test_delete_node_type_returns_404_when_missing() -> None:
    """DELETE on a nonexistent node type returns 404."""
    client = _admin_client()

    response = client.delete(f"/api/v1/node-types/{uuid.uuid4()}")

    assert response.status_code == 404


def test_attributes_schema_round_trips_through_create_and_update() -> None:
    """attributes_schema is stored on create and can be updated via PATCH."""
    client = TestClient(_app_with_in_memory_graph())
    schema: dict[str, object] = {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "type": "object",
        "properties": {"year": {"title": "Year", "type": "number"}},
    }

    nt = client.post(
        "/api/v1/node-types",
        json={"slug": "film", "label": "Film", "attributes_schema": schema},
    ).json()
    assert nt["attributes_schema"] == schema

    new_schema: dict[str, object] = {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "type": "object",
        "properties": {},
    }
    updated = client.patch(
        f"/api/v1/node-types/{nt['id']}",
        json={"attributes_schema": new_schema},
    ).json()
    assert updated["attributes_schema"] == new_schema


def test_attribute_usage_and_purge_round_trip() -> None:
    """Usage counts nodes holding a key; purge removes it and answers 204."""
    client = _admin_client()
    nt = client.post(
        "/api/v1/node-types", json={"slug": "film", "label": "Film"}
    ).json()
    for name, attrs in [("A", {"old": 1}), ("B", {"old": 2}), ("C", {})]:
        client.post(
            "/api/v1/nodes", json={"name": name, "type": "film", "attributes": attrs}
        )
    base = f"/api/v1/node-types/{nt['id']}/attributes/old"

    assert client.get(f"{base}/usage").json() == {"count": 2}
    purge = client.delete(base)
    assert purge.status_code == 204
    assert purge.content == b""
    assert client.get(f"{base}/usage").json() == {"count": 0}


def test_attribute_usage_and_purge_return_404_for_missing_type() -> None:
    """Both endpoints report a missing node type as 404."""
    client = _admin_client()
    base = f"/api/v1/node-types/{uuid.uuid4()}/attributes/old"

    assert client.get(f"{base}/usage").status_code == 404
    assert client.delete(base).status_code == 404


def test_attribute_usage_can_filter_by_value() -> None:
    """`?value=` counts only nodes whose attribute equals that string."""
    client = TestClient(_app_with_in_memory_graph())
    nt = client.post(
        "/api/v1/node-types", json={"slug": "film", "label": "Film"}
    ).json()
    for name, status in [("A", "Draft"), ("B", "Draft"), ("C", "Live")]:
        client.post(
            "/api/v1/nodes",
            json={"name": name, "type": "film", "attributes": {"status": status}},
        )
    base = f"/api/v1/node-types/{nt['id']}/attributes/status/usage"

    assert client.get(base, params={"value": "Draft"}).json() == {"count": 2}
    assert client.get(base).json() == {"count": 3}


def test_attribute_usage_and_purge_can_target_a_group_sub_key() -> None:
    """`?sub_key=` counts and purges rows of a group array, not the whole key."""
    client = _admin_client()
    nt = client.post(
        "/api/v1/node-types", json={"slug": "recipe", "label": "Recipe"}
    ).json()
    client.post(
        "/api/v1/nodes",
        json={
            "name": "A",
            "type": "recipe",
            "attributes": {"ingredients": [{"name": "Flour", "unit": "g"}]},
        },
    )
    base = f"/api/v1/node-types/{nt['id']}/attributes/ingredients"

    assert client.get(f"{base}/usage", params={"sub_key": "unit"}).json() == {
        "count": 1
    }
    purge = client.delete(base, params={"sub_key": "unit"})
    assert purge.status_code == 204
    assert purge.content == b""
    assert client.get(f"{base}/usage", params={"sub_key": "unit"}).json() == {
        "count": 0
    }


def test_list_attribute_values_returns_distinct_values_most_used_first() -> None:
    """Distinct string values are returned with counts, most-used first."""
    client = TestClient(_app_with_in_memory_graph())
    nt = client.post(
        "/api/v1/node-types", json={"slug": "film", "label": "Film"}
    ).json()
    for name, status in [("A", "Draft"), ("B", "Draft"), ("C", "Live")]:
        client.post(
            "/api/v1/nodes",
            json={"name": name, "type": "film", "attributes": {"status": status}},
        )
    base = f"/api/v1/node-types/{nt['id']}/attributes/status/values"

    response = client.get(base)

    assert response.status_code == 200
    assert response.json() == [
        {"value": "Draft", "count": 2},
        {"value": "Live", "count": 1},
    ]


def test_list_attribute_values_can_filter_by_q() -> None:
    """`?q=` filters values by a case-insensitive substring."""
    client = TestClient(_app_with_in_memory_graph())
    nt = client.post(
        "/api/v1/node-types", json={"slug": "film", "label": "Film"}
    ).json()
    for name, status in [("A", "Draft"), ("B", "Live")]:
        client.post(
            "/api/v1/nodes",
            json={"name": name, "type": "film", "attributes": {"status": status}},
        )
    base = f"/api/v1/node-types/{nt['id']}/attributes/status/values"

    response = client.get(base, params={"q": "dra"})

    assert response.json() == [{"value": "Draft", "count": 1}]


def test_list_attribute_values_returns_404_for_missing_type() -> None:
    """A missing node type is reported as 404."""
    client = TestClient(_app_with_in_memory_graph())
    base = f"/api/v1/node-types/{uuid.uuid4()}/attributes/status/values"

    assert client.get(base).status_code == 404


def test_icon_and_colour_can_be_set_changed_and_cleared() -> None:
    """A type's icon and colour are in every response and can be cleared with ''."""
    client = TestClient(_app_with_in_memory_graph())

    created = client.post(
        "/api/v1/node-types",
        json={"slug": "film", "label": "Film", "icon": "clapperboard", "colour": "red"},
    )
    assert created.status_code == 201
    assert (created.json()["icon"], created.json()["colour"]) == ("clapperboard", "red")
    type_id = created.json()["id"]

    changed = client.patch(f"/api/v1/node-types/{type_id}", json={"colour": "blue"})
    assert (changed.json()["icon"], changed.json()["colour"]) == (
        "clapperboard",
        "blue",
    )

    cleared = client.patch(
        f"/api/v1/node-types/{type_id}", json={"icon": None, "colour": None}
    )
    assert (cleared.json()["icon"], cleared.json()["colour"]) == (None, None)


def test_a_blank_icon_or_colour_is_refused_not_treated_as_a_clear() -> None:
    """An empty string is an error; null is how an icon or colour is removed."""
    client = TestClient(_app_with_in_memory_graph())
    created = client.post(
        "/api/v1/node-types",
        json={"slug": "film", "label": "Film", "icon": "film", "colour": "red"},
    ).json()

    for body in ({"icon": ""}, {"colour": ""}):
        response = client.patch(f"/api/v1/node-types/{created['id']}", json=body)
        assert response.status_code == 400

    kept = client.get(f"/api/v1/node-types/{created['id']}").json()
    assert (kept["icon"], kept["colour"]) == ("film", "red")


def test_leaving_icon_and_colour_out_keeps_them() -> None:
    """Omitted is not null: only an explicit null removes the value."""
    client = TestClient(_app_with_in_memory_graph())
    created = client.post(
        "/api/v1/node-types",
        json={"slug": "film", "label": "Film", "icon": "film", "colour": "red"},
    ).json()

    changed = client.patch(
        f"/api/v1/node-types/{created['id']}", json={"label": "Movie"}
    )

    assert (changed.json()["icon"], changed.json()["colour"]) == ("film", "red")


def test_a_type_without_an_icon_or_colour_reports_nulls() -> None:
    """Both fields are always present, null when unset."""
    client = TestClient(_app_with_in_memory_graph())

    created = client.post("/api/v1/node-types", json={"slug": "book", "label": "Book"})

    assert created.json()["icon"] is None
    assert created.json()["colour"] is None


def test_an_invalid_icon_or_colour_is_a_400() -> None:
    """A bad icon name or a colour outside the palette is refused."""
    client = TestClient(_app_with_in_memory_graph())

    bad_icon = client.post(
        "/api/v1/node-types", json={"slug": "a", "label": "A", "icon": "Not An Icon"}
    )
    bad_colour = client.post(
        "/api/v1/node-types", json={"slug": "b", "label": "B", "colour": "purple"}
    )

    assert bad_icon.status_code == 400
    assert "icon must be" in bad_icon.json()["detail"]
    assert bad_colour.status_code == 400
    assert "colour must be one of" in bad_colour.json()["detail"]


def test_a_type_has_no_parent_unless_given_one() -> None:
    """Every type is top-level by default, and says so."""
    client = TestClient(_app_with_in_memory_graph())

    created = client.post("/api/v1/node-types", json={"slug": "book", "label": "Book"})

    assert created.json()["parent"] is None


def test_a_subtype_round_trips_its_parent_and_can_be_made_top_level_again() -> None:
    """Create with a parent, read it back, then send null to remove it."""
    client = TestClient(_app_with_in_memory_graph())
    client.post(
        "/api/v1/node-types", json={"slug": "memorabilia", "label": "Memorabilia"}
    )

    created = client.post(
        "/api/v1/node-types",
        json={"slug": "poster", "label": "Poster", "parent": "memorabilia"},
    )
    assert created.status_code == 201
    assert created.json()["parent"] == "memorabilia"
    poster_id = created.json()["id"]
    assert (
        client.get(f"/api/v1/node-types/{poster_id}").json()["parent"] == "memorabilia"
    )

    renamed = client.patch(
        f"/api/v1/node-types/{poster_id}", json={"label": "Film poster"}
    )
    assert renamed.json()["parent"] == "memorabilia"

    cleared = client.patch(f"/api/v1/node-types/{poster_id}", json={"parent": None})
    assert cleared.status_code == 200
    assert cleared.json()["parent"] is None


def test_a_parent_that_cannot_be_used_is_a_400_naming_why() -> None:
    """A missing parent, a subtype as a parent, and a clashing field are refused."""
    client = TestClient(_app_with_in_memory_graph())
    client.post(
        "/api/v1/node-types",
        json={
            "slug": "memorabilia",
            "label": "Memorabilia",
            "attributes_schema": {
                "type": "object",
                "properties": {"condition": {"type": "string"}},
            },
        },
    )
    client.post(
        "/api/v1/node-types",
        json={"slug": "poster", "label": "Poster", "parent": "memorabilia"},
    )

    missing = client.post(
        "/api/v1/node-types", json={"slug": "a", "label": "A", "parent": "nothing"}
    )
    nested = client.post(
        "/api/v1/node-types", json={"slug": "b", "label": "B", "parent": "poster"}
    )
    clash = client.post(
        "/api/v1/node-types",
        json={
            "slug": "c",
            "label": "C",
            "parent": "memorabilia",
            "attributes_schema": {
                "type": "object",
                "properties": {"condition": {"type": "string"}},
            },
        },
    )

    assert [r.status_code for r in (missing, nested, clash)] == [400, 400, 400]
    assert "not found" in missing.json()["detail"]
    assert "one level" in nested.json()["detail"]
    assert "condition" in clash.json()["detail"]


def _fields(*keys: str) -> dict[str, object]:
    return {"type": "object", "properties": {k: {"type": "string"} for k in keys}}


def test_a_subtypes_response_shows_the_fields_it_uses() -> None:
    """effective_schema is the parent's fields then its own; the other, just its own."""
    client = TestClient(_app_with_in_memory_graph())
    client.post(
        "/api/v1/node-types",
        json={
            "slug": "memorabilia",
            "label": "Memorabilia",
            "attributes_schema": _fields("condition"),
        },
    )

    poster = client.post(
        "/api/v1/node-types",
        json={
            "slug": "poster",
            "label": "Poster",
            "parent": "memorabilia",
            "attributes_schema": _fields("width"),
        },
    ).json()

    fetched = client.get(f"/api/v1/node-types/{poster['id']}").json()
    parent = client.get("/api/v1/node-types").json()[0]
    assert list(poster["effective_schema"]["properties"]) == ["condition", "width"]
    assert list(fetched["effective_schema"]["properties"]) == ["condition", "width"]
    assert list(fetched["attributes_schema"]["properties"]) == ["width"]
    # A type with no parent uses just its own.
    assert parent["effective_schema"] == parent["attributes_schema"]


def test_a_subtypes_etag_follows_a_change_to_its_parent() -> None:
    """A cached subtype is not answered 304 once its parent gains a field."""
    client = TestClient(_app_with_in_memory_graph())
    parent = client.post(
        "/api/v1/node-types",
        json={
            "slug": "memorabilia",
            "label": "Memorabilia",
            "attributes_schema": _fields("condition"),
        },
    ).json()
    poster = client.post(
        "/api/v1/node-types",
        json={"slug": "poster", "label": "Poster", "parent": "memorabilia"},
    ).json()
    url = f"/api/v1/node-types/{poster['id']}"
    before = client.get(url)
    assert (
        client.get(url, headers={"If-None-Match": before.headers["ETag"]}).status_code
        == 304
    )

    client.patch(
        f"/api/v1/node-types/{parent['id']}",
        json={"attributes_schema": _fields("condition", "value")},
    )

    after = client.get(url, headers={"If-None-Match": before.headers["ETag"]})
    assert after.status_code == 200
    assert after.headers["ETag"] != before.headers["ETag"]
    assert list(after.json()["effective_schema"]["properties"]) == [
        "condition",
        "value",
    ]


def test_a_parents_subtypes_are_listed_with_paging() -> None:
    """GET /node-types/{id}/subtypes lists only that parent's, paged like the rest."""
    client = TestClient(_app_with_in_memory_graph())
    parent = client.post(
        "/api/v1/node-types", json={"slug": "memorabilia", "label": "Memorabilia"}
    ).json()
    client.post("/api/v1/node-types", json={"slug": "music-media", "label": "Music"})
    for slug, under in (
        ("poster", "memorabilia"),
        ("figure", "memorabilia"),
        ("mug", "memorabilia"),
        ("vinyl", "music-media"),
    ):
        client.post(
            "/api/v1/node-types", json={"slug": slug, "label": slug, "parent": under}
        )

    first = client.get(f"/api/v1/node-types/{parent['id']}/subtypes?limit=2")

    assert first.status_code == 200
    assert [t["slug"] for t in first.json()] == ["poster", "figure"]
    assert 'rel="next"' in first.headers["Link"]
    last_id = first.json()[-1]["id"]
    rest = client.get(
        f"/api/v1/node-types/{parent['id']}/subtypes?after={last_id}&limit=2"
    )
    assert [t["slug"] for t in rest.json()] == ["mug"]
    assert "Link" not in rest.headers


def test_listing_the_subtypes_of_an_unknown_type_is_a_404() -> None:
    """The parent has to exist."""
    client = TestClient(_app_with_in_memory_graph())

    missing = client.get(f"/api/v1/node-types/{uuid.uuid4()}/subtypes")

    assert missing.status_code == 404


def test_deleting_a_parent_with_subtypes_is_a_409_until_they_are_gone() -> None:
    """The parent can only go once its subtypes have."""
    client = TestClient(_app_with_in_memory_graph())
    parent = client.post(
        "/api/v1/node-types", json={"slug": "memorabilia", "label": "Memorabilia"}
    ).json()
    sub = client.post(
        "/api/v1/node-types",
        json={"slug": "poster", "label": "Poster", "parent": "memorabilia"},
    ).json()

    refused = client.delete(f"/api/v1/node-types/{parent['id']}")
    assert refused.status_code == 409
    assert "poster" in refused.json()["detail"]

    assert client.delete(f"/api/v1/node-types/{sub['id']}").status_code == 204
    assert client.delete(f"/api/v1/node-types/{parent['id']}").status_code == 204


def _choice_field(*options: str) -> dict[str, object]:
    return {
        "type": "string",
        "enum": list(options),
        "x-menagerist": {"kind": "choice"},
    }


def _clashing_pair(client: TestClient) -> tuple[dict[str, str], dict[str, str]]:
    """A parent and a standalone type that both define `condition`."""
    parent = client.post(
        "/api/v1/node-types",
        json={
            "slug": "memorabilia",
            "label": "Memorabilia",
            "attributes_schema": {
                "type": "object",
                "properties": {"condition": _choice_field("Mint", "Good")},
            },
        },
    ).json()
    poster = client.post(
        "/api/v1/node-types",
        json={
            "slug": "poster",
            "label": "Poster",
            "attributes_schema": {
                "type": "object",
                "properties": {
                    "condition": _choice_field("Worn"),
                    "width": {"type": "string"},
                },
            },
        },
    ).json()
    return parent, poster


def test_previewing_a_clash_reports_it_and_changes_nothing() -> None:
    """The plan names the shared field; the type still has no parent afterwards."""
    client = TestClient(_app_with_in_memory_graph())
    _, poster = _clashing_pair(client)
    url = f"/api/v1/node-types/{poster['id']}/parent/plan"

    refused = client.post(url, json={"parent": "memorabilia"})
    merged = client.post(url, json={"parent": "memorabilia", "on_clash": "merge"})

    assert refused.status_code == 200
    assert refused.json()["allowed"] is False
    assert refused.json()["clashes"] == ["condition"]
    assert "condition" in refused.json()["reason"]
    assert merged.json()["allowed"] is True
    assert merged.json()["merged"] == ["condition"]
    assert merged.json()["reason"] is None
    assert client.get(f"/api/v1/node-types/{poster['id']}").json()["parent"] is None


def test_previewing_a_detach_lists_what_is_kept_or_archived() -> None:
    """Removing the parent reports the fields it would copy or archive."""
    client = TestClient(_app_with_in_memory_graph())
    _, poster = _clashing_pair(client)
    client.patch(
        f"/api/v1/node-types/{poster['id']}",
        json={"parent": "memorabilia", "on_clash": "merge"},
    )
    url = f"/api/v1/node-types/{poster['id']}/parent/plan"

    keep = client.post(url, json={"parent": None}).json()
    drop = client.post(url, json={"parent": None, "on_detach": "drop"}).json()

    assert (keep["previous"], keep["parent"]) == ("memorabilia", None)
    assert keep["kept"] == ["condition"]
    assert drop["archived"] == ["condition"]


def test_previewing_for_an_unknown_type_or_parent_is_refused() -> None:
    """A missing type is a 404 and a parent that cannot be used is a 400."""
    client = TestClient(_app_with_in_memory_graph())
    _, poster = _clashing_pair(client)

    unknown = client.post(
        f"/api/v1/node-types/{uuid.uuid4()}/parent/plan", json={"parent": None}
    )
    no_parent = client.post(
        f"/api/v1/node-types/{poster['id']}/parent/plan", json={"parent": "nothing"}
    )

    assert unknown.status_code == 404
    assert no_parent.status_code == 400


def test_patching_with_merge_widens_the_parents_choices() -> None:
    """The same request the preview described is applied, parent included."""
    client = TestClient(_app_with_in_memory_graph())
    parent, poster = _clashing_pair(client)

    refused = client.patch(
        f"/api/v1/node-types/{poster['id']}", json={"parent": "memorabilia"}
    )
    merged = client.patch(
        f"/api/v1/node-types/{poster['id']}",
        json={"parent": "memorabilia", "on_clash": "merge"},
    )

    assert refused.status_code == 400
    assert merged.status_code == 200
    assert list(merged.json()["attributes_schema"]["properties"]) == ["width"]
    widened = client.get(f"/api/v1/node-types/{parent['id']}").json()
    options = widened["attributes_schema"]["properties"]["condition"]["enum"]
    assert options == ["Mint", "Good", "Worn"]


def test_patching_to_remove_a_parent_with_drop_archives_its_fields() -> None:
    """`on_detach: drop` hides the inherited fields rather than copying them."""
    client = TestClient(_app_with_in_memory_graph())
    _, poster = _clashing_pair(client)
    client.patch(
        f"/api/v1/node-types/{poster['id']}",
        json={"parent": "memorabilia", "on_clash": "merge"},
    )

    detached = client.patch(
        f"/api/v1/node-types/{poster['id']}",
        json={"parent": None, "on_detach": "drop"},
    )

    assert detached.json()["parent"] is None
    condition = detached.json()["attributes_schema"]["properties"]["condition"]
    assert condition["x-menagerist"]["archived"] is True
