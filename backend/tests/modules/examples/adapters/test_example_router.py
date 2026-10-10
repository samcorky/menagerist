import asyncio
from dataclasses import replace
from typing import TYPE_CHECKING

from starlette.testclient import TestClient

from app.entrypoints.api import create_app
from app.entrypoints.api.shared.example_targets import (
    get_collection_pack_target,
    get_cover_pack_target,
    get_graph_pack_target,
    get_preset_pack_target,
)
from app.modules.examples.adapters.api.dependencies import (
    get_example_repos,
    get_example_uow,
    get_pack_catalogue,
)
from app.modules.examples.domain.installation import Installation
from app.modules.examples.domain.pack import (
    ExamplePack,
    PackCollection,
    PackItem,
    PackItemType,
)
from app.modules.examples.ports.unit_of_work import ExampleRepos
from app.modules.graph.domain.node_type import NodeType

if TYPE_CHECKING:
    from fastapi import FastAPI

    from app.modules.graph.domain.node import Node
    from tests.modules.examples.conftest import MakeWorld, SamplePack, World


def _client(world: World, *, raise_server_exceptions: bool = True) -> TestClient:
    app: FastAPI = create_app()
    app.dependency_overrides[get_example_uow] = lambda: world.uow
    app.dependency_overrides[get_example_repos] = lambda: ExampleRepos(
        installations=world.installations
    )
    app.dependency_overrides[get_pack_catalogue] = lambda: world.catalogue
    app.dependency_overrides[get_preset_pack_target] = lambda: world.presets
    app.dependency_overrides[get_graph_pack_target] = lambda: world.graph
    app.dependency_overrides[get_collection_pack_target] = lambda: world.collections
    app.dependency_overrides[get_cover_pack_target] = lambda: world.covers
    return TestClient(app, raise_server_exceptions=raise_server_exceptions)


def test_list_shows_packs_and_installation_state(
    make_world: MakeWorld, sample_pack: SamplePack
) -> None:
    """The list reports each pack and, once installed, its owned counts."""
    client = _client(make_world(sample_pack("one"), sample_pack("two")))

    first = client.get("/api/v1/example")
    assert first.status_code == 200
    assert [p["id"] for p in first.json()] == ["one", "two"]
    assert first.json()[0]["installation"] is None
    assert first.json()[0]["counts"]["items"] == 2

    assert client.put("/api/v1/example/one/installation").status_code == 200
    after = client.get("/api/v1/example").json()
    assert after[0]["installation"]["status"] == "installed"
    assert after[0]["installation"]["counts"]["items"] == 2
    assert after[1]["installation"] is None


def test_install_returns_what_was_created(make_world: MakeWorld) -> None:
    """Installing returns the pack id and the counts created."""
    client = _client(make_world())

    response = client.put("/api/v1/example/demo/installation")

    assert response.status_code == 200
    body = response.json()
    assert body["pack_id"] == "demo"
    assert body["created"]["item_types"] == 2
    assert body["adopted"] == {
        "presets": 0,
        "relationship_types": 0,
        "item_types": 0,
        "items": 0,
        "connections": 0,
        "collections": 0,
    }


def test_reinstall_reports_what_it_adopted(make_world: MakeWorld) -> None:
    """Kept, edited examples are taken back and counted as adopted, not created."""
    world = make_world()
    client = _client(world)
    client.put("/api/v1/example/demo/installation")
    blue = asyncio.run(_blue(world))
    blue.name = "Blue (my copy)"
    asyncio.run(world.graph_repos.nodes.save(blue))
    client.delete("/api/v1/example/demo/installation")

    response = client.put("/api/v1/example/demo/installation")

    assert response.status_code == 200
    body = response.json()
    assert (body["adopted"]["items"], body["adopted"]["item_types"]) == (1, 1)
    assert (body["created"]["items"], body["created"]["item_types"]) == (1, 1)


def test_install_twice_is_a_409_and_unknown_is_a_404(make_world: MakeWorld) -> None:
    """A second install conflicts; an unknown pack is not found."""
    client = _client(make_world())
    assert client.put("/api/v1/example/demo/installation").status_code == 200

    again = client.put("/api/v1/example/demo/installation")

    assert again.status_code == 409
    assert again.json()["title"] == "PackAlreadyInstalledError"
    assert client.put("/api/v1/example/nope/installation").status_code == 404


def test_uninstall_reports_removed_and_kept(make_world: MakeWorld) -> None:
    """Uninstalling returns what was removed and what was kept."""
    client = _client(make_world())
    client.put("/api/v1/example/demo/installation")

    response = client.delete("/api/v1/example/demo/installation")

    assert response.status_code == 200
    body = response.json()
    assert body["removed"]["items"] == 2
    assert body["kept"] == []


def test_uninstall_reports_kept_entities(make_world: MakeWorld) -> None:
    """Kept entities are serialised with kind, label and reason."""
    world = make_world()
    client = _client(world)
    client.put("/api/v1/example/demo/installation")
    blue = asyncio.run(_blue(world))
    blue.name = "Blue (my copy)"
    asyncio.run(world.graph_repos.nodes.save(blue))

    response = client.delete("/api/v1/example/demo/installation")

    assert response.status_code == 200
    kept = response.json()["kept"]
    assert {"kind": "item", "label": "Blue", "reason": "edited"} in kept


async def _blue(world: World) -> Node:
    nodes = await world.graph_repos.nodes.list(after=None, limit=10)
    return next(n for n in nodes if n.name == "Blue")


def test_uninstall_when_not_installed_is_a_409(make_world: MakeWorld) -> None:
    """Removing a pack that is not installed conflicts."""
    client = _client(make_world())

    assert client.delete("/api/v1/example/demo/installation").status_code == 409


def test_a_failed_install_is_a_500_problem_with_the_cause(
    make_world: MakeWorld,
) -> None:
    """An unexpected failure surfaces as a problem response naming the cause."""
    world = make_world()

    async def boom(*_args: object, **_kwargs: object) -> None:
        raise RuntimeError("boom")

    world.graph.create_item = boom  # type: ignore[assignment,method-assign]
    client = _client(world, raise_server_exceptions=False)

    response = client.put("/api/v1/example/demo/installation")

    assert response.status_code == 500
    assert response.headers["content-type"].startswith("application/problem+json")
    assert "boom" in response.json()["detail"]


def test_slug_clash_is_a_409_naming_the_slug(make_world: MakeWorld) -> None:
    """A taken type name conflicts and the detail names it."""
    world = make_world()
    asyncio.run(
        world.graph_repos.node_types.add(
            NodeType.create(slug="demo-record", label="Mine")
        )
    )

    response = _client(world).put("/api/v1/example/demo/installation")

    assert response.status_code == 409
    assert "demo-record" in response.json()["detail"]


def test_openapi_documents_the_installation_status_values(
    make_world: MakeWorld,
) -> None:
    """The schema lists the allowed statuses rather than a bare string."""
    schema = _client(make_world()).get("/api/openapi.json").json()

    status = schema["components"]["schemas"]["InstallationResponse"]["properties"][
        "status"
    ]
    enum = schema["components"]["schemas"][status["$ref"].rsplit("/", 1)[-1]]
    assert enum["enum"] == ["installing", "installed", "removed", "failed"]


def test_entities_lists_owned_item_and_item_type_ids(make_world: MakeWorld) -> None:
    """Once installed, the pack's items and item types are listed; none before."""
    client = _client(make_world())
    assert client.get("/api/v1/example/entities").json() == {
        "item_ids": [],
        "item_type_ids": [],
        "collection_ids": [],
    }

    assert client.put("/api/v1/example/demo/installation").status_code == 200
    body = client.get("/api/v1/example/entities").json()
    assert len(body["item_ids"]) == 2
    assert len(body["item_type_ids"]) == 2

    assert client.delete("/api/v1/example/demo/installation").status_code == 200
    assert client.get("/api/v1/example/entities").json() == {
        "item_ids": [],
        "item_type_ids": [],
        "collection_ids": [],
    }


def test_entities_lists_owned_collection_ids(
    make_world: MakeWorld, sample_pack: SamplePack
) -> None:
    """Installed example collections are listed by id, and gone once removed."""
    pack = replace(
        sample_pack(),
        collections=(PackCollection(ref="all", name="All", item_refs=("blue", "ada")),),
    )
    world = make_world(pack)
    client = _client(world)

    assert client.put("/api/v1/example/demo/installation").status_code == 200
    body = client.get("/api/v1/example/entities").json()
    assert body["collection_ids"] == [str(c) for c in world.collections.collections]
    assert len(body["collection_ids"]) == 1

    assert client.delete("/api/v1/example/demo/installation").status_code == 200
    assert client.get("/api/v1/example/entities").json()["collection_ids"] == []


def _add_on_world(make_world: MakeWorld, sample_pack: SamplePack) -> World:
    """A base ('Base'), and two add-ons that require it."""
    add_ons = [
        ExamplePack(
            id=pack_id,
            requires=("base",),
            item_types=(PackItemType(ref="t", slug=f"{pack_id}-t", label="T"),),
            items=(PackItem(ref="i", type_ref="t", name=f"{pack_id} item"),),
        )
        for pack_id in ("extras", "more")
    ]
    return make_world(sample_pack("base"), *add_ons)


def test_list_shows_requires_and_required_by_with_names(
    make_world: MakeWorld, sample_pack: SamplePack
) -> None:
    """An add-on lists what it requires; the base lists installed dependants."""
    client = _client(_add_on_world(make_world, sample_pack))

    before = {p["id"]: p for p in client.get("/api/v1/example").json()}
    assert before["extras"]["requires"] == [{"id": "base", "name": "Base"}]
    assert before["base"]["requires"] == []
    assert before["base"]["required_by"] == []

    client.put("/api/v1/example/base/installation")
    client.put("/api/v1/example/extras/installation")
    during = {p["id"]: p for p in client.get("/api/v1/example").json()}
    assert during["base"]["required_by"] == [{"id": "extras", "name": "Extras"}]
    assert during["extras"]["required_by"] == []

    client.delete("/api/v1/example/extras/installation")
    after = {p["id"]: p for p in client.get("/api/v1/example").json()}
    assert after["base"]["required_by"] == []


def test_ordinary_packs_have_empty_requirement_lists(
    make_world: MakeWorld, sample_pack: SamplePack
) -> None:
    """A pack with no add-ons around it reports empty lists."""
    client = _client(make_world(sample_pack("one")))

    pack = client.get("/api/v1/example").json()[0]

    assert (pack["requires"], pack["required_by"]) == ([], [])


def test_install_add_on_without_base_is_a_409(
    make_world: MakeWorld, sample_pack: SamplePack
) -> None:
    """Adding an add-on before its base conflicts, in plain words."""
    client = _client(_add_on_world(make_world, sample_pack))

    response = client.put("/api/v1/example/extras/installation")

    assert response.status_code == 409
    assert response.json()["title"] == "RequirementsNotMetError"
    assert response.json()["detail"] == "Add Base first."


def test_uninstall_base_with_dependants_is_a_409(
    make_world: MakeWorld, sample_pack: SamplePack
) -> None:
    """Removing a base lists every installed add-on that needs it."""
    client = _client(_add_on_world(make_world, sample_pack))
    for pack_id in ("base", "extras", "more"):
        client.put(f"/api/v1/example/{pack_id}/installation")

    response = client.delete("/api/v1/example/base/installation")

    assert response.status_code == 409
    assert response.json()["title"] == "RequiredByInstalledPackError"
    assert response.json()["detail"] == "Remove Extras and More first."


def test_half_added_add_on_counts_as_dependant_and_blocks_removal(
    make_world: MakeWorld, sample_pack: SamplePack
) -> None:
    """An installing add-on shows in `required_by` and blocks removing the base."""
    world = _add_on_world(make_world, sample_pack)
    client = _client(world)
    client.put("/api/v1/example/base/installation")
    asyncio.run(world.installations.add(Installation.start("extras")))

    listed = {p["id"]: p for p in client.get("/api/v1/example").json()}
    blocked = client.delete("/api/v1/example/base/installation")

    assert listed["base"]["required_by"] == [{"id": "extras", "name": "Extras"}]
    assert blocked.status_code == 409
    assert blocked.json()["detail"] == "Remove Extras first."


def test_required_by_lists_every_dependant_in_catalogue_order(
    make_world: MakeWorld, sample_pack: SamplePack
) -> None:
    """Two installed add-ons are both listed, in catalogue order."""
    client = _client(_add_on_world(make_world, sample_pack))
    for pack_id in ("base", "more", "extras"):
        client.put(f"/api/v1/example/{pack_id}/installation")

    base = client.get("/api/v1/example").json()[0]

    assert [r["id"] for r in base["required_by"]] == ["extras", "more"]
