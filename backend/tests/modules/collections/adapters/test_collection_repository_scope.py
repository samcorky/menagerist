"""Scoped `CollectionRepository` and `MembershipRepository`, in memory and Postgres."""

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime

import pytest

from app.modules.collections.adapters.persistence.collection_repository import (
    SqlAlchemyCollectionRepository,
)
from app.modules.collections.adapters.persistence.in_memory_collection_repository import (  # noqa: E501
    InMemoryCollectionRepository,
)
from app.modules.collections.adapters.persistence.in_memory_membership_repository import (  # noqa: E501
    InMemoryMembershipRepository,
)
from app.modules.collections.adapters.persistence.membership_repository import (
    SqlAlchemyMembershipRepository,
)
from app.modules.collections.domain.collection import Collection, Membership
from app.modules.collections.ports.collection_repository import CollectionRepository
from app.modules.collections.ports.membership_repository import MembershipRepository
from app.shared_kernel.access_scope import AccessScope
from app.shared_kernel.errors import ConflictError
from app.shared_kernel.slug import Slug

ALICE = uuid.UUID(int=101)
BOB = uuid.UUID(int=102)
A = AccessScope.of(ALICE)
B = AccessScope.of(BOB)
ALL = AccessScope.everyone()


@dataclass
class Repos:
    """Both repositories of one adapter."""

    collections: CollectionRepository
    memberships: MembershipRepository


@pytest.fixture(
    params=["in_memory", pytest.param("postgres", marks=pytest.mark.integration)]
)
def repos(request: pytest.FixtureRequest) -> Repos:
    """The same scenarios run against both adapters."""
    if request.param == "in_memory":
        collections = InMemoryCollectionRepository()
        return Repos(collections, InMemoryMembershipRepository(collections))
    session = request.getfixturevalue("db_session")
    return Repos(
        SqlAlchemyCollectionRepository(session), SqlAlchemyMembershipRepository(session)
    )


def _shelf(owner: uuid.UUID, name: str = "Jazz", slug: str | None = None) -> Collection:
    return Collection.create(name=name, slug=Slug(slug or name), owner_id=owner)


def _member(collection: Collection, item_id: uuid.UUID) -> Membership:
    return Membership(
        collection_id=collection.id, item_id=item_id, added_at=datetime.now(UTC)
    )


async def test_get_and_get_by_slug_hide_other_owners(repos: Repos) -> None:
    """A's collection is visible to A and everyone(), never to B."""
    shelf = _shelf(ALICE)
    await repos.collections.add(shelf)

    assert await repos.collections.get(shelf.id, scope=A) is not None
    assert await repos.collections.get(shelf.id, scope=ALL) is not None
    assert await repos.collections.get(shelf.id, scope=B) is None
    assert await repos.collections.get_by_slug("jazz", scope=A) is not None
    assert await repos.collections.get_by_slug("jazz", scope=ALL) is not None
    assert await repos.collections.get_by_slug("jazz", scope=B) is None


async def test_soft_deleted_collections_are_excluded(repos: Repos) -> None:
    """A deleted collection is invisible to its owner and to everyone()."""
    shelf = _shelf(ALICE)
    await repos.collections.add(shelf)
    shelf.soft_delete()
    await repos.collections.save(shelf)

    for scope in (A, ALL):
        assert await repos.collections.get(shelf.id, scope=scope) is None
        assert await repos.collections.get_by_slug("jazz", scope=scope) is None
        assert await repos.collections.list(scope=scope, after=None, limit=5) == []


async def test_list_is_scoped_with_paging_and_search(repos: Repos) -> None:
    """Each owner lists only their own collections, including paged and searched."""
    mine = [_shelf(ALICE, f"Tape {n}") for n in range(3)]
    theirs = [_shelf(BOB, f"Tape B{n}") for n in range(2)]
    for shelf in [*mine, *theirs]:
        await repos.collections.add(shelf)
    mine_ids = sorted(s.id for s in mine)

    first = await repos.collections.list(scope=A, after=None, limit=2)
    rest = await repos.collections.list(scope=A, after=first[-1].id, limit=2)
    searched = await repos.collections.list(scope=B, after=None, limit=10, q="tape")

    assert [c.id for c in [*first, *rest]] == mine_ids
    assert {c.id for c in searched} == {s.id for s in theirs}
    assert len(await repos.collections.list(scope=ALL, after=None, limit=10)) == 5


async def test_same_slug_for_two_owners_is_allowed(repos: Repos) -> None:
    """A and B can each hold 'jazz'; lookups stay per owner."""
    mine, theirs = _shelf(ALICE), _shelf(BOB)
    await repos.collections.add(mine)
    await repos.collections.add(theirs)

    found_a = await repos.collections.get_by_slug("jazz", scope=A)
    found_b = await repos.collections.get_by_slug("jazz", scope=B)
    assert found_a is not None
    assert found_b is not None
    assert (found_a.id, found_b.id) == (mine.id, theirs.id)


@pytest.mark.integration
async def test_same_owner_same_slug_conflicts_in_postgres(
    db_session: object,
) -> None:
    """The per-owner unique index still rejects a duplicate live slug."""
    repo = SqlAlchemyCollectionRepository(db_session)  # type: ignore[arg-type]
    await repo.add(_shelf(ALICE))
    with pytest.raises(ConflictError):
        await repo.add(_shelf(ALICE))
    await repo.add(_shelf(BOB))


@pytest.mark.integration
async def test_deleted_slug_is_reusable_by_its_owner_in_postgres(
    db_session: object,
) -> None:
    """Only live rows reserve a slug within one owner."""
    repo = SqlAlchemyCollectionRepository(db_session)  # type: ignore[arg-type]
    old = _shelf(ALICE)
    await repo.add(old)
    old.soft_delete()
    await repo.save(old)

    await repo.add(_shelf(ALICE))


async def test_memberships_follow_the_collection_owner(repos: Repos) -> None:
    """item_ids and collection_ids_for are empty outside the owner's scope."""
    shelf = _shelf(ALICE)
    await repos.collections.add(shelf)
    item = uuid.uuid7()
    await repos.memberships.add(_member(shelf, item))

    assert await repos.memberships.item_ids(shelf.id, scope=A) == {item}
    assert await repos.memberships.item_ids(shelf.id, scope=ALL) == {item}
    assert await repos.memberships.item_ids(shelf.id, scope=B) == set()
    assert await repos.memberships.collection_ids_for(item, scope=A) == {shelf.id}
    assert await repos.memberships.collection_ids_for(item, scope=ALL) == {shelf.id}
    assert await repos.memberships.collection_ids_for(item, scope=B) == set()
