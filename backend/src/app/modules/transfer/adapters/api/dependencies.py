from functools import lru_cache
from typing import Annotated

from fastapi import Depends

from app.entrypoints.api.shared.access_guard import get_access_guard
from app.entrypoints.api.shared.bridges.transfer_targets import (
    CollectionPackTarget,
    GraphPackTarget,
    PresetPackTarget,
    get_collection_pack_target,
    get_graph_pack_target,
    get_preset_pack_target,
)
from app.modules.transfer.adapters.codecs.menagerist_bundle import MenageristBundleCodec
from app.modules.transfer.application.bundle_files import (
    ExportBundle,
    ImportBundle,
    PlanBundleImport,
)
from app.modules.transfer.application.codecs import CodecRegistry
from app.shared_kernel.access_guard import AccessGuard


@lru_cache(maxsize=1)
def get_codecs() -> CodecRegistry:
    """Return every file format this server reads and writes (built once)."""
    return CodecRegistry([MenageristBundleCodec()])


def get_plan_bundle_import_use_case(
    guard: Annotated[AccessGuard, Depends(get_access_guard)],
    codecs: Annotated[CodecRegistry, Depends(get_codecs)],
    presets: Annotated[PresetPackTarget, Depends(get_preset_pack_target)],
    graph: Annotated[GraphPackTarget, Depends(get_graph_pack_target)],
    collections: Annotated[
        CollectionPackTarget, Depends(get_collection_pack_target)
    ],
) -> PlanBundleImport:
    return PlanBundleImport(guard, codecs, presets, graph, collections)


def get_import_bundle_use_case(
    guard: Annotated[AccessGuard, Depends(get_access_guard)],
    codecs: Annotated[CodecRegistry, Depends(get_codecs)],
    presets: Annotated[PresetPackTarget, Depends(get_preset_pack_target)],
    graph: Annotated[GraphPackTarget, Depends(get_graph_pack_target)],
    collections: Annotated[
        CollectionPackTarget, Depends(get_collection_pack_target)
    ],
) -> ImportBundle:
    return ImportBundle(guard, codecs, presets, graph, collections)


def get_export_bundle_use_case(
    guard: Annotated[AccessGuard, Depends(get_access_guard)],
    codecs: Annotated[CodecRegistry, Depends(get_codecs)],
    presets: Annotated[PresetPackTarget, Depends(get_preset_pack_target)],
    graph: Annotated[GraphPackTarget, Depends(get_graph_pack_target)],
    collections: Annotated[
        CollectionPackTarget, Depends(get_collection_pack_target)
    ],
) -> ExportBundle:
    return ExportBundle(guard, codecs, presets, graph, collections)
