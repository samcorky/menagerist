"""An in-memory world: real targets over in-memory repositories, a shipped catalogue.

The catalogue and transfer tests both install through these targets.
"""

import uuid
from dataclasses import dataclass

import pytest

from app.entrypoints.api.shared.bridges.transfer_targets import (
    CollectionPackTarget,
    GraphPackTarget,
    PresetPackTarget,
    build_in_memory_collections_repos,
    in_memory_collection_stores,
    in_memory_graph_stores,
    in_memory_preset_stores,
)
from app.modules.catalogue.adapters.platform.file_entry_catalogue import (
    FileEntryCatalogue,
)
from app.modules.graph.adapters.persistence.unit_of_work import (
    build_in_memory_graph_repos,
)
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
from app.modules.transfer.adapters.persistence.in_memory_import_repository import (
    InMemoryItemImportRepository,
)
from app.modules.transfer.adapters.persistence.in_memory_source_link_repository import (
    InMemorySourceLinkRepository,
)
from app.modules.transfer.ports.unit_of_work import TransferRepos
from app.shared_kernel.access_guard import AccessGuard, InMemoryAccessGuard
from app.shared_kernel.actor import Actor

ALICE = Actor(id=uuid.UUID(int=0xA1), roles=frozenset({"member"}))
BOB = Actor(id=uuid.UUID(int=0xB2), roles=frozenset({"member"}))


@dataclass
class Targets:
    """The targets the catalogue and bundle files go through, for one person."""

    presets: PresetPackTarget
    graph: GraphPackTarget
    collections: CollectionPackTarget


class Shared:
    """Repositories shared by every person in a test, so isolation is real."""

    def __init__(self) -> None:
        self.graph_repos = build_in_memory_graph_repos()
        self.collection_repos = build_in_memory_collections_repos()
        self.preset_repos = PresetRepos(presets=InMemoryPresetRepository())
        assets = InMemoryMediaAssetRepository()
        self.media_repos = MediaRepos(
            assets=assets, attachments=InMemoryMediaAttachmentRepository(assets)
        )
        self.catalogue = FileEntryCatalogue()
        self.transfer_repos = TransferRepos(
            links=InMemorySourceLinkRepository(), imports=InMemoryItemImportRepository()
        )

    def targets(self, actor: Actor, guard: AccessGuard | None = None) -> Targets:
        """Return targets acting as `actor`, optionally with a custom guard."""
        guard = guard or InMemoryAccessGuard()
        return Targets(
            presets=PresetPackTarget(
                in_memory_preset_stores(self.preset_repos, self.graph_repos),
                actor,
                access=guard,
            ),
            graph=GraphPackTarget(
                in_memory_graph_stores(
                    self.graph_repos,
                    self.media_repos,
                    self.preset_repos,
                    self.collection_repos,
                ),
                actor,
                access=guard,
            ),
            collections=CollectionPackTarget(
                in_memory_collection_stores(self.collection_repos, self.graph_repos),
                actor,
                access=guard,
            ),
        )


@pytest.fixture
def shared() -> Shared:
    """Return a fresh in-memory world."""
    return Shared()
