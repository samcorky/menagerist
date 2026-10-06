"""Shared fixtures: a sample pack and an all-in-memory world to install it into."""

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

import pytest

from app.entrypoints.api.shared.example_targets import (
    GraphPackTarget,
    PresetPackTarget,
    in_memory_graph_stores,
    in_memory_preset_stores,
)
from app.modules.examples.adapters.persistence.in_memory_installation_repository import (  # noqa: E501
    InMemoryInstallationRepository,
)
from app.modules.examples.adapters.platform.in_memory_pack_catalogue import (
    InMemoryPackCatalogue,
)
from app.modules.examples.domain.pack import (
    ExamplePack,
    PackConnection,
    PackItem,
    PackItemType,
    PackPreset,
    PackRelationshipType,
)
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
from app.modules.media.adapters.persistence.in_memory_media_asset_repository import (
    InMemoryMediaAssetRepository,
)
from app.modules.media.adapters.persistence.in_memory_media_attachment_repository import (  # noqa: E501
    InMemoryMediaAttachmentRepository,
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
class World:
    """Everything an application test needs, all in memory."""

    graph_repos: GraphRepos
    preset_repos: PresetRepos
    media_repos: MediaRepos
    installations: InMemoryInstallationRepository
    catalogue: InMemoryPackCatalogue
    uow: InMemoryUnitOfWork[ExampleRepos]
    presets: PresetPackTarget
    graph: GraphPackTarget


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
    return World(
        graph_repos=graph_repos,
        preset_repos=preset_repos,
        media_repos=media_repos,
        installations=installations,
        catalogue=catalogue,
        uow=InMemoryUnitOfWork(ExampleRepos(installations=installations)),
        presets=PresetPackTarget(in_memory_preset_stores(preset_repos, graph_repos)),
        graph=GraphPackTarget(
            in_memory_graph_stores(graph_repos, media_repos, preset_repos)
        ),
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
