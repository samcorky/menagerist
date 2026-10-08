"""Shared fixtures: an all-in-memory collections world."""

import uuid
from collections.abc import Callable
from dataclasses import dataclass

import pytest

from app.modules.collections.adapters.persistence.in_memory_collection_repository import (  # noqa: E501
    InMemoryCollectionRepository,
)
from app.modules.collections.adapters.persistence.in_memory_item_lookup import (
    InMemoryItemLookup,
)
from app.modules.collections.adapters.persistence.in_memory_membership_repository import (  # noqa: E501
    InMemoryMembershipRepository,
)
from app.modules.collections.domain.collection import Collection
from app.modules.collections.ports.unit_of_work import CollectionsRepos
from app.shared_kernel.slug import Slug
from app.shared_kernel.unit_of_work import InMemoryUnitOfWork


@dataclass(kw_only=True)
class World:
    """Everything an application test needs, all in memory."""

    collections: InMemoryCollectionRepository
    memberships: InMemoryMembershipRepository
    items: InMemoryItemLookup
    uow: InMemoryUnitOfWork[CollectionsRepos]


MakeWorld = Callable[[], World]
MakeCollection = Callable[..., Collection]


def _make_world() -> World:
    """Build a world with empty repositories and no live items."""
    collections = InMemoryCollectionRepository()
    memberships = InMemoryMembershipRepository()
    return World(
        collections=collections,
        memberships=memberships,
        items=InMemoryItemLookup(),
        uow=InMemoryUnitOfWork(
            CollectionsRepos(collections=collections, memberships=memberships)
        ),
    )


def _make_collection(name: str = "Shelf", slug: str | None = None) -> Collection:
    """Create a collection with a slug derived from `name` unless given."""
    return Collection.create(name=name, slug=Slug(slug or name), owner_id=uuid.uuid7())


@pytest.fixture
def world() -> World:
    """Return a fresh in-memory world."""
    return _make_world()


@pytest.fixture
def make_collection() -> MakeCollection:
    """Return a factory building a collection."""
    return _make_collection
