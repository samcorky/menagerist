"""First-run setup claims existing content in one transaction, on real Postgres."""

import uuid
from dataclasses import dataclass
from typing import TYPE_CHECKING, Annotated

import pytest
import pytest_asyncio
import sqlalchemy
from fastapi import Depends
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from starlette.testclient import TestClient

from app.entrypoints.api import create_app
from app.entrypoints.api.shared.bridges.claim_existing_data import (
    ClaimExistingData,
    get_claim_existing_data,
)
from app.modules.collections.adapters.persistence.unit_of_work import (
    build_collections_repos,
)
from app.modules.collections.domain.collection import Collection
from app.modules.examples.adapters.persistence.unit_of_work import build_example_repos
from app.modules.examples.domain.installation import Installation
from app.modules.graph.adapters.persistence.unit_of_work import build_graph_repos
from app.modules.graph.domain.edge import Edge
from app.modules.graph.domain.node import Node
from app.modules.identity.adapters.api.dependencies import get_existing_data_claim
from app.modules.media.adapters.persistence.unit_of_work import build_media_repos
from app.modules.media.domain.media_asset import MediaAsset
from app.platform.database import get_engine, get_session_factory
from app.shared_kernel.slug import Slug

if TYPE_CHECKING:
    from collections.abc import AsyncIterator, Iterator

    from sqlalchemy.ext.asyncio import AsyncSession

pytestmark = pytest.mark.integration

AUTH = "/api/v1/auth"
SYSTEM = uuid.UUID(int=0)
LEGACY_API = uuid.UUID(int=1)
STRANGER = uuid.uuid7()
SETUP_BODY = {
    "username": "Admin",
    "display_name": "Admin",
    "password": "a long passphrase",
}
TABLES = (
    "nodes",
    "edges",
    "collections",
    "media_assets",
    "example_installations",
)
Owners = dict[str, list[uuid.UUID | None]]


def _wipe(sync_url: str) -> None:
    engine = sqlalchemy.create_engine(sync_url)
    with engine.begin() as connection:
        for table in (
            "sessions",
            "users",
            "media_attachments",
            "media_assets",
            "collection_members",
            "collections",
            "edges",
            "nodes",
            "example_installations",
        ):
            connection.execute(sqlalchemy.text(f"DELETE FROM {table}"))
    engine.dispose()


def _owners(sync_url: str) -> Owners:
    """Every table's owners, NULLs first."""
    engine = sqlalchemy.create_engine(sync_url)
    with engine.connect() as connection:
        found = {
            table: list(
                connection.execute(
                    sqlalchemy.text(
                        f"SELECT owner_id FROM {table} ORDER BY owner_id NULLS FIRST"
                    )
                ).scalars()
            )
            for table in TABLES
        }
    engine.dispose()
    return found


def _count(sync_url: str, table: str) -> int:
    engine = sqlalchemy.create_engine(sync_url)
    with engine.connect() as connection:
        value = connection.execute(
            sqlalchemy.text(f"SELECT count(*) FROM {table}")
        ).scalar_one()
    engine.dispose()
    return int(value)


@dataclass(kw_only=True)
class Seeded:
    """The owners each table started with."""

    before: Owners


async def _seed(session: AsyncSession) -> None:
    """Rows in every table: ownerless, system-owned, legacy-API and a stranger's."""
    graph = build_graph_repos(session)
    nodes = [Node.create(owner_id=SYSTEM, name=f"n{i}") for i in range(4)]
    for node, owner in zip(nodes, (None, SYSTEM, STRANGER, STRANGER), strict=True):
        node.owner_id = owner
        await graph.nodes.add(node)
    for owner in (None, SYSTEM, STRANGER, STRANGER):
        edge = Edge.create(
            owner_id=SYSTEM, source_id=nodes[0].id, target_id=nodes[1].id, type="t"
        )
        edge.owner_id = owner
        await graph.edges.add(edge)
    collections = build_collections_repos(session)
    for slug, owner in (
        ("a", SYSTEM),
        ("b", LEGACY_API),
        ("c", STRANGER),
        ("d", STRANGER),
    ):
        await collections.collections.add(
            Collection.create(name=slug, slug=Slug(slug), owner_id=owner)
        )
    media = build_media_repos(session)
    for owner in (None, SYSTEM, LEGACY_API, STRANGER):
        asset = MediaAsset.create(
            owner_id=SYSTEM,
            filename="a.jpg",
            content_type="image/jpeg",
            size=1,
            sha256="x",
        )
        asset.owner_id = owner
        await media.assets.add(asset)
    examples = build_example_repos(session)
    packs = (("p1", None), ("p2", SYSTEM), ("p3", STRANGER), ("p4", STRANGER))
    for pack, owner in packs:
        installation = Installation.start(pack, SYSTEM)
        installation.owner_id = owner
        await examples.installations.add(installation)
    await session.commit()


@pytest_asyncio.fixture
async def seeded(postgres_url: str, postgres_sync_url: str) -> AsyncIterator[Seeded]:
    """Seed rows in every table; empty everything afterwards."""
    _wipe(postgres_sync_url)
    engine = create_async_engine(postgres_url)
    async with async_sessionmaker(engine, expire_on_commit=False)() as session:
        await _seed(session)
    await engine.dispose()
    try:
        yield Seeded(before=_owners(postgres_sync_url))
    finally:
        _wipe(postgres_sync_url)


@pytest.fixture
def client(seeded: Seeded) -> Iterator[TestClient]:
    """The real app, after rows were seeded."""
    get_session_factory.cache_clear()
    get_engine.cache_clear()
    try:
        with TestClient(create_app(), raise_server_exceptions=False) as c:
            yield c
    finally:
        get_session_factory.cache_clear()
        get_engine.cache_clear()


def test_setup_gives_every_pre_existing_row_to_the_admin(
    client: TestClient, seeded: Seeded, postgres_sync_url: str
) -> None:
    """NULL, system and legacy owners move; the stranger's rows stay; counts match."""
    response = client.post(f"{AUTH}/setup", json=SETUP_BODY)

    assert response.status_code == 201
    assert response.json()["claimed"] == {
        "items": 2,
        "connections": 2,
        "collections": 2,
        "files": 2,
        "examples": 2,
    }
    admin = uuid.UUID(response.json()["user"]["id"])
    after = _owners(postgres_sync_url)
    assert sorted(map(str, after["nodes"])) == sorted(
        map(str, [admin, admin, STRANGER, STRANGER])
    )
    assert sorted(map(str, after["edges"])) == sorted(
        map(str, [admin, admin, STRANGER, STRANGER])
    )
    assert sorted(map(str, after["collections"])) == sorted(
        map(str, [admin, admin, STRANGER, STRANGER])
    )
    # UUID(int=1) is a legacy owner of collections only.
    assert sorted(map(str, after["media_assets"])) == sorted(
        map(str, [admin, admin, LEGACY_API, STRANGER])
    )
    assert sorted(map(str, after["example_installations"])) == sorted(
        map(str, [admin, admin, STRANGER, STRANGER])
    )
    assert seeded.before["nodes"][0] is None


def test_setup_twice_is_refused_and_claims_nothing(
    client: TestClient, postgres_sync_url: str
) -> None:
    """A second setup answers 409 and leaves a new ownerless row ownerless."""
    assert client.post(f"{AUTH}/setup", json=SETUP_BODY).status_code == 201
    engine = sqlalchemy.create_engine(postgres_sync_url)
    with engine.begin() as connection:
        connection.execute(
            sqlalchemy.text("UPDATE nodes SET owner_id = NULL WHERE owner_id = :o"),
            {"o": STRANGER},
        )
    engine.dispose()
    before = _owners(postgres_sync_url)
    assert before["nodes"].count(None) == 2

    again = client.post(f"{AUTH}/setup", json=SETUP_BODY | {"username": "second"})

    assert again.status_code == 409
    assert _owners(postgres_sync_url) == before
    assert _count(postgres_sync_url, "users") == 1


class _FailsAfterClaiming:
    """Runs the real claim, then fails, as if a later step broke."""

    def __init__(self, inner: ClaimExistingData) -> None:
        self._inner = inner

    async def claim(self, owner_id: uuid.UUID) -> object:
        """Claim everything, then raise."""
        await self._inner.claim(owner_id)
        raise RuntimeError("boom")


def _failing_claim(
    real: Annotated[ClaimExistingData, Depends(get_claim_existing_data)],
) -> _FailsAfterClaiming:
    return _FailsAfterClaiming(real)


def test_a_failure_inside_the_claim_rolls_the_whole_setup_back(
    seeded: Seeded, postgres_sync_url: str
) -> None:
    """No admin, no session, no changed owner: setup and claim share one transaction."""
    get_session_factory.cache_clear()
    get_engine.cache_clear()
    app = create_app()
    app.dependency_overrides[get_existing_data_claim] = _failing_claim
    try:
        with TestClient(app, raise_server_exceptions=False) as c:
            response = c.post(f"{AUTH}/setup", json=SETUP_BODY)
            status = c.get(f"{AUTH}/status")
    finally:
        get_session_factory.cache_clear()
        get_engine.cache_clear()

    assert response.status_code == 500
    assert status.json() == {"setup_required": True}
    assert _count(postgres_sync_url, "users") == 0
    assert _count(postgres_sync_url, "sessions") == 0
    assert _owners(postgres_sync_url) == seeded.before
