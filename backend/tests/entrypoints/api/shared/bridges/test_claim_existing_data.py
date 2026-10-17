"""The existing-data claim over in-memory adapters: which rows move, which stay."""

import uuid
from dataclasses import dataclass

import pytest

from app.entrypoints.api.shared.bridges.claim_existing_data import (
    ClaimExistingData,
    build_claim_existing_data,
    get_claim_existing_data,
)
from app.modules.collections.adapters.persistence.in_memory_collection_repository import (  # noqa: E501
    InMemoryCollectionRepository,
)
from app.modules.collections.adapters.persistence.in_memory_membership_repository import (  # noqa: E501
    InMemoryMembershipRepository,
)
from app.modules.collections.domain.collection import Collection
from app.modules.collections.ports.unit_of_work import CollectionsRepos
from app.modules.examples.adapters.persistence.in_memory_installation_repository import (  # noqa: E501
    InMemoryInstallationRepository,
)
from app.modules.examples.domain.installation import Installation
from app.modules.examples.ports.unit_of_work import ExampleRepos
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
from app.modules.graph.domain.edge import Edge
from app.modules.graph.domain.node import Node
from app.modules.graph.ports.unit_of_work import GraphRepos
from app.modules.media.adapters.persistence.in_memory_media_asset_repository import (
    InMemoryMediaAssetRepository,
)
from app.modules.media.adapters.persistence.unit_of_work import make_in_memory_repos
from app.modules.media.domain.media_asset import MediaAsset
from app.shared_kernel.access_scope import AccessScope
from app.shared_kernel.slug import Slug

EVERYONE = AccessScope.everyone()
SYSTEM = uuid.UUID(int=0)
LEGACY_API = uuid.UUID(int=1)
OTHER = uuid.uuid7()
ADMIN = uuid.uuid7()


@dataclass(kw_only=True)
class Stores:
    """Every in-memory repository the claim touches."""

    nodes: InMemoryNodeRepository
    edges: InMemoryEdgeRepository
    collections: InMemoryCollectionRepository
    assets: InMemoryMediaAssetRepository
    installations: InMemoryInstallationRepository
    claim: ClaimExistingData


@pytest.fixture
def stores() -> Stores:
    """A claim wired over empty in-memory repositories."""
    nodes = InMemoryNodeRepository()
    edges = InMemoryEdgeRepository()
    collections = InMemoryCollectionRepository()
    assets = InMemoryMediaAssetRepository()
    installations = InMemoryInstallationRepository()
    claim = build_claim_existing_data(
        graph=GraphRepos(
            nodes=nodes,
            edges=edges,
            node_types=InMemoryNodeTypeRepository(),
            edge_types=InMemoryEdgeTypeRepository(),
        ),
        collections=CollectionsRepos(
            collections=collections,
            memberships=InMemoryMembershipRepository(collections),
        ),
        media=make_in_memory_repos(assets=assets),
        examples=ExampleRepos(installations=installations),
    )
    return Stores(
        nodes=nodes,
        edges=edges,
        collections=collections,
        assets=assets,
        installations=installations,
        claim=claim,
    )


def _node(owner: uuid.UUID | None) -> Node:
    node = Node.create(owner_id=SYSTEM, name="n")
    node.owner_id = owner
    return node


def _edge(owner: uuid.UUID | None) -> Edge:
    edge = Edge.create(
        owner_id=SYSTEM, source_id=uuid.uuid7(), target_id=uuid.uuid7(), type="t"
    )
    edge.owner_id = owner
    return edge


def _collection(owner: uuid.UUID, slug: str) -> Collection:
    return Collection.create(name=slug, slug=Slug(slug), owner_id=owner)


def _asset(owner: uuid.UUID | None) -> MediaAsset:
    asset = MediaAsset.create(
        owner_id=SYSTEM, filename="a.jpg", content_type="image/jpeg", size=1, sha256="x"
    )
    asset.owner_id = owner
    return asset


def _installation(owner: uuid.UUID | None, pack: str) -> Installation:
    installation = Installation.start(pack, SYSTEM)
    installation.owner_id = owner
    return installation


async def test_claims_ownerless_and_legacy_rows_in_every_module(stores: Stores) -> None:
    """NULL and system owners move to the admin in all four modules, with counts."""
    nodes = [_node(None), _node(SYSTEM)]
    edges = [_edge(None), _edge(SYSTEM)]
    collections = [
        _collection(SYSTEM, "a"),
        _collection(LEGACY_API, "b"),
    ]
    assets = [_asset(None), _asset(SYSTEM)]
    installations = [_installation(None, "p1"), _installation(SYSTEM, "p2")]
    for node in nodes:
        await stores.nodes.add(node)
    for edge in edges:
        await stores.edges.add(edge)
    for collection in collections:
        await stores.collections.add(collection)
    for asset in assets:
        await stores.assets.add(asset)
    for installation in installations:
        await stores.installations.add(installation)

    report = await stores.claim.claim(ADMIN)

    assert report.counts == {
        "items": 2,
        "connections": 2,
        "collections": 2,
        "files": 2,
        "examples": 2,
    }
    owners = [
        *(n.owner_id for n in nodes),
        *(e.owner_id for e in edges),
        *(c.owner_id for c in collections),
        *(a.owner_id for a in assets),
        *(i.owner_id for i in installations),
    ]
    assert owners == [ADMIN] * len(owners)


async def test_other_peoples_rows_and_later_rows_are_untouched(stores: Stores) -> None:
    """Rows owned by a real user stay put; a second claim finds nothing new."""
    theirs_node = _node(OTHER)
    theirs_collection = _collection(OTHER, "theirs")
    theirs_asset = _asset(OTHER)
    theirs_installation = _installation(OTHER, "p")
    await stores.nodes.add(theirs_node)
    await stores.collections.add(theirs_collection)
    await stores.assets.add(theirs_asset)
    await stores.installations.add(theirs_installation)

    first = await stores.claim.claim(ADMIN)
    # Created after setup by someone else, then a (mistaken) second claim.
    later = _node(OTHER)
    await stores.nodes.add(later)
    second = await stores.claim.claim(ADMIN)

    assert sum(first.counts.values()) == 0
    assert sum(second.counts.values()) == 0
    assert theirs_node.owner_id == OTHER
    assert theirs_collection.owner_id == OTHER
    assert theirs_asset.owner_id == OTHER
    assert theirs_installation.owner_id == OTHER
    assert later.owner_id == OTHER


async def test_legacy_api_owner_is_claimed_only_for_collections(
    stores: Stores,
) -> None:
    """UUID(int=1) is a legacy owner of collections alone."""
    node = _node(LEGACY_API)
    asset = _asset(LEGACY_API)
    await stores.nodes.add(node)
    await stores.assets.add(asset)

    report = await stores.claim.claim(ADMIN)

    assert sum(report.counts.values()) == 0
    assert node.owner_id == LEGACY_API
    assert asset.owner_id == LEGACY_API


async def test_soft_deleted_rows_are_claimed_too(stores: Stores) -> None:
    """A deleted legacy row must not stay orphaned if it is ever restored."""
    node = _node(None)
    node.soft_delete()
    await stores.nodes.add(node)

    report = await stores.claim.claim(ADMIN)

    assert report.counts["items"] == 1
    assert node.owner_id == ADMIN


def test_create_app_wires_the_real_claim_bridge() -> None:
    """Losing this override would leave existing content ownerless after setup."""
    from app.entrypoints.api import create_app
    from app.modules.identity.adapters.api.dependencies import get_existing_data_claim

    overrides = create_app().dependency_overrides
    assert overrides[get_existing_data_claim] is get_claim_existing_data
