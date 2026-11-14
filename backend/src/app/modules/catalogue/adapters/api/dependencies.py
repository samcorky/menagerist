from functools import lru_cache
from typing import Annotated

from fastapi import Depends

from app.entrypoints.api.shared.access_guard import get_access_guard
from app.entrypoints.api.shared.bridges.transfer_targets import (
    GraphPackTarget,
    PresetPackTarget,
    get_graph_pack_target,
    get_preset_pack_target,
)
from app.modules.catalogue.adapters.platform.file_entry_catalogue import (
    FileEntryCatalogue,
)
from app.modules.catalogue.application.install_catalogue_entry import (
    InstallCatalogueEntry,
)
from app.modules.catalogue.application.list_catalogue_entries import (
    ListCatalogueEntries,
)
from app.modules.catalogue.ports.entry_catalogue import EntryCatalogue
from app.shared_kernel.access_guard import AccessGuard


@lru_cache(maxsize=1)
def _catalogue() -> FileEntryCatalogue:
    return FileEntryCatalogue()


def get_entry_catalogue() -> EntryCatalogue:
    """Return the shipped catalogue (parsed once per process)."""
    return _catalogue()


def get_list_catalogue_entries_use_case(
    guard: Annotated[AccessGuard, Depends(get_access_guard)],
    catalogue: Annotated[EntryCatalogue, Depends(get_entry_catalogue)],
    presets: Annotated[PresetPackTarget, Depends(get_preset_pack_target)],
    graph: Annotated[GraphPackTarget, Depends(get_graph_pack_target)],
) -> ListCatalogueEntries:
    return ListCatalogueEntries(guard, catalogue, presets, graph)


def get_install_catalogue_entry_use_case(
    guard: Annotated[AccessGuard, Depends(get_access_guard)],
    catalogue: Annotated[EntryCatalogue, Depends(get_entry_catalogue)],
    presets: Annotated[PresetPackTarget, Depends(get_preset_pack_target)],
    graph: Annotated[GraphPackTarget, Depends(get_graph_pack_target)],
) -> InstallCatalogueEntry:
    return InstallCatalogueEntry(guard, catalogue, presets, graph)
