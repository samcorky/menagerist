"""Shared fixtures: a sample pack and an all-in-memory world to install it into."""

import uuid
from collections.abc import Callable, Sequence
from dataclasses import dataclass, replace
from typing import Any

import pytest

from app.entrypoints.api.shared.example_targets import (
    CoverPackTarget,
    GraphPackTarget,
    GraphStores,
    PresetPackTarget,
    in_memory_cover_stores,
    in_memory_graph_stores,
    in_memory_preset_stores,
)
from app.modules.examples.adapters.covers.in_memory_cover_renderer import (
    InMemoryCoverRenderer,
)
from app.modules.examples.adapters.persistence.in_memory_installation_repository import (  # noqa: E501
    InMemoryInstallationRepository,
)
from app.modules.examples.adapters.platform.in_memory_pack_catalogue import (
    InMemoryPackCatalogue,
)
from app.modules.examples.domain.installation import EntityKind
from app.modules.examples.domain.pack import (
    ExamplePack,
    PackCollection,
    PackConnection,
    PackItem,
    PackItemType,
    PackPreset,
    PackRelationshipType,
)
from app.modules.examples.ports.pack_targets import Created, Inspection, RemoveResult
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
from app.modules.graph.ports.unit_of_work import GraphRepos
from app.modules.media.adapters.imaging.in_memory_image_processor import (
    InMemoryImageProcessor,
)
from app.modules.media.adapters.persistence.in_memory_media_asset_repository import (
    InMemoryMediaAssetRepository,
)
from app.modules.media.adapters.persistence.in_memory_media_attachment_repository import (  # noqa: E501
    InMemoryMediaAttachmentRepository,
)
from app.modules.media.adapters.policy.content_type_attachment_policy import (
    ContentTypeAttachmentPolicy,
)
from app.modules.media.adapters.storage.in_memory_media_storage import (
    InMemoryMediaStorage,
)
from app.modules.media.ports.unit_of_work import MediaRepos
from app.modules.presets.adapters.persistence.in_memory_preset_repository import (
    InMemoryPresetRepository,
)
from app.modules.presets.ports.unit_of_work import PresetRepos
from app.shared_kernel.unit_of_work import InMemoryUnitOfWork

_RECORD_SCHEMA: dict[str, Any] = {
    "$schema": "https://json-schema.org/draft/2020-12/schema",
    "type": "object",
    "properties": {
        "condition": {
            "title": "Condition",
            "type": "string",
            "x-menagerist": {"kind": "choice", "list": {"$preset": "grades"}},
        }
    },
}


@dataclass(kw_only=True)
class FakeCollection:
    """A collection held by the fake target; tests edit it directly."""

    id: uuid.UUID
    name: str
    description: str | None
    members: list[uuid.UUID]


class InMemoryCollectionTarget:
    """Fake `CollectionTarget`: stores collections and records its calls."""

    def __init__(self) -> None:
        self.collections: dict[uuid.UUID, FakeCollection] = {}
        self.create_calls: list[tuple[PackCollection, list[uuid.UUID]]] = []
        self.events: list[str] = []  # removal calls, shared with the graph target
        self.fail_on_call: int | None = None  # make this create_collection call fail

    def member_ids(self) -> set[uuid.UUID]:
        """Return every item id that belongs to a live collection."""
        return {m for c in self.collections.values() for m in c.members}

    def add_users_own(self, name: str, members: Sequence[uuid.UUID]) -> uuid.UUID:
        """Add a collection the user made, outside any pack."""
        coll = FakeCollection(
            id=uuid.uuid7(), name=name, description=None, members=list(members)
        )
        self.collections[coll.id] = coll
        return coll.id

    async def create_collection(
        self, spec: PackCollection, *, item_ids: Sequence[uuid.UUID]
    ) -> Created:
        """Store a collection with `item_ids` as members."""
        self.create_calls.append((spec, list(item_ids)))
        if self.fail_on_call == len(self.create_calls):
            raise RuntimeError("collection boom")
        coll = FakeCollection(
            id=uuid.uuid7(),
            name=spec.name,
            description=spec.description,
            members=list(item_ids),
        )
        self.collections[coll.id] = coll
        return Created(entity_id=coll.id, content=_collection_content(coll))

    async def inspect(self, collection_id: uuid.UUID) -> Inspection | None:
        """Return the collection as it is now, or `None` if gone."""
        coll = self.collections.get(collection_id)
        return None if coll is None else Inspection(content=_collection_content(coll))

    async def remove(self, collection_id: uuid.UUID) -> RemoveResult:
        """Remove the collection, recording the call."""
        self.events.append("collection")
        if self.collections.pop(collection_id, None) is None:
            return RemoveResult.ALREADY_GONE
        return RemoveResult.REMOVED


def _collection_content(coll: FakeCollection) -> dict[str, Any]:
    return {
        "name": coll.name,
        "description": coll.description,
        "members": sorted(str(m) for m in coll.members),
    }


class WorldGraphTarget(GraphPackTarget):
    """Graph target modelling the rule: a member of a live collection is user data."""

    def __init__(
        self, stores: GraphStores, collections: InMemoryCollectionTarget
    ) -> None:
        super().__init__(stores)
        self._collections = collections

    async def inspect(
        self, kind: EntityKind, entity_id: uuid.UUID
    ) -> Inspection | None:
        """Inspect as the real target does, plus collection membership for items."""
        inspection = await super().inspect(kind, entity_id)
        if (
            inspection is not None
            and kind is EntityKind.ITEM
            and entity_id in self._collections.member_ids()
        ):
            return replace(inspection, has_user_data=True)
        return inspection

    async def remove(self, kind: EntityKind, entity_id: uuid.UUID) -> RemoveResult:
        """Remove the entity, recording the call's kind."""
        self._collections.events.append(kind.value)
        return await super().remove(kind, entity_id)


class WorldCoverTarget(CoverPackTarget):
    """Real cover target over in-memory media that records and can fail its calls."""

    def __init__(
        self,
        repos: MediaRepos,
        storage: InMemoryMediaStorage,
        events: list[str],
    ) -> None:
        super().__init__(
            in_memory_cover_stores(repos),
            renderer=InMemoryCoverRenderer(),
            storage=storage,
            policy=ContentTypeAttachmentPolicy(),
            image_processor=InMemoryImageProcessor(),
        )
        self.events = events  # removal calls, shared with the other targets
        self.create_calls: list[tuple[uuid.UUID, str, str]] = []
        self.removed: list[uuid.UUID] = []
        self.fail_on_call: int | None = None  # make this create call fail

    async def create(self, item_id: uuid.UUID, name: str, style: str) -> Created:
        """Create the cover, recording the call."""
        self.create_calls.append((item_id, name, style))
        if self.fail_on_call == len(self.create_calls):
            raise RuntimeError("cover boom")
        return await super().create(item_id, name, style)

    async def remove(self, cover_id: uuid.UUID) -> RemoveResult:
        """Remove the cover, recording the call."""
        self.events.append("cover")
        self.removed.append(cover_id)
        return await super().remove(cover_id)


@dataclass(kw_only=True)
class World:
    """Everything an application test needs, all in memory."""

    graph_repos: GraphRepos
    preset_repos: PresetRepos
    media_repos: MediaRepos
    installations: InMemoryInstallationRepository
    catalogue: InMemoryPackCatalogue
    uow: InMemoryUnitOfWork[ExampleRepos]
    presets: PresetPackTarget
    graph: WorldGraphTarget
    collections: InMemoryCollectionTarget
    covers: WorldCoverTarget
    storage: InMemoryMediaStorage


SamplePack = Callable[..., ExamplePack]
MakeWorld = Callable[..., World]


def _sample_pack(pack_id: str = "demo") -> ExamplePack:
    """One preset, two item types, one relationship type, two items, one link."""
    return ExamplePack(
        id=pack_id,
        presets=(
            PackPreset(
                ref="grades",
                kind="choice_list",
                label=f"{pack_id} grades",
                definition={"options": ["Mint", "Good"]},
            ),
        ),
        relationship_types=(
            PackRelationshipType(
                ref="signed-by",
                slug=f"{pack_id}-signed-by",
                label="Signed by",
                reverse_label="Signed",
            ),
        ),
        item_types=(
            PackItemType(
                ref="record",
                slug=f"{pack_id}-record",
                label="Record",
                attributes_schema=_RECORD_SCHEMA,
            ),
            PackItemType(ref="person", slug=f"{pack_id}-person", label="Person"),
        ),
        items=(
            PackItem(
                ref="blue",
                type_ref="record",
                name="Blue",
                attributes={"condition": "Mint"},
                tags=("jazz",),
            ),
            PackItem(ref="ada", type_ref="person", name="Ada"),
        ),
        connections=(
            PackConnection(source_ref="blue", target_ref="ada", type_ref="signed-by"),
        ),
    )


def _make_world(*packs: ExamplePack) -> World:
    """Build a world with `packs` in the catalogue (the demo pack by default)."""
    graph_repos = GraphRepos(
        nodes=InMemoryNodeRepository(),
        edges=InMemoryEdgeRepository(),
        node_types=InMemoryNodeTypeRepository(),
        edge_types=InMemoryEdgeTypeRepository(),
    )
    preset_repos = PresetRepos(presets=InMemoryPresetRepository())
    media_repos = MediaRepos(
        assets=InMemoryMediaAssetRepository(),
        attachments=InMemoryMediaAttachmentRepository(),
    )
    installations = InMemoryInstallationRepository()
    catalogue = InMemoryPackCatalogue()
    for pack in packs or (_sample_pack(),):
        catalogue.add(pack, name=pack.id.title(), description=f"{pack.id} examples")
    collections = InMemoryCollectionTarget()
    storage = InMemoryMediaStorage()
    return World(
        graph_repos=graph_repos,
        preset_repos=preset_repos,
        media_repos=media_repos,
        installations=installations,
        catalogue=catalogue,
        uow=InMemoryUnitOfWork(ExampleRepos(installations=installations)),
        presets=PresetPackTarget(in_memory_preset_stores(preset_repos, graph_repos)),
        graph=WorldGraphTarget(
            in_memory_graph_stores(graph_repos, media_repos, preset_repos),
            collections,
        ),
        collections=collections,
        covers=WorldCoverTarget(media_repos, storage, collections.events),
        storage=storage,
    )


@pytest.fixture
def sample_pack() -> SamplePack:
    """Return a factory building the sample pack under a given id."""
    return _sample_pack


@pytest.fixture
def make_world() -> MakeWorld:
    """Return a factory building an in-memory world holding the given packs."""
    return _make_world


@pytest.fixture
def pack_data() -> dict[str, Any]:
    """Return a fresh, valid pack file as a JSON-style dict."""
    return {
        "format": "menagerist-example-pack",
        "version": 1,
        "id": "demo",
        "presets": [
            {
                "ref": "grades",
                "kind": "choice_list",
                "label": "Grades",
                "definition": {"options": ["Mint"]},
            }
        ],
        "relationship_types": [
            {"ref": "by", "slug": "by", "label": "By", "reverse_label": "Made"}
        ],
        "item_types": [{"ref": "thing", "slug": "thing", "label": "Thing"}],
        "items": [
            {"ref": "a", "type": "thing", "name": "A", "tags": ["x"]},
            {"ref": "b", "type": "thing", "name": "B"},
        ],
        "connections": [{"from": "a", "to": "b", "type": "by"}],
    }
