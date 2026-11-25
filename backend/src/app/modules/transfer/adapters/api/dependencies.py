from datetime import timedelta
from functools import lru_cache
from typing import TYPE_CHECKING, Annotated

from fastapi import Depends

from app.entrypoints.api.shared.access_guard import get_access_guard
from app.entrypoints.api.shared.bridges.job_queue import get_job_queue
from app.entrypoints.api.shared.bridges.transfer_targets import (
    CollectionPackTarget,
    GraphPackTarget,
    PresetPackTarget,
    get_collection_pack_target,
    get_graph_pack_target,
    get_preset_pack_target,
)
from app.modules.transfer.adapters.codecs.menagerist_bundle import MenageristBundleCodec
from app.modules.transfer.adapters.persistence.unit_of_work import (
    build_transfer_repos,
    create_transfer_uow,
)
from app.modules.transfer.adapters.storage.local_import_files import import_file_store
from app.modules.transfer.application.bundle_files import (
    ExportBundle,
    ImportBundle,
    PlanBundleImport,
)
from app.modules.transfer.application.codecs import CodecRegistry
from app.modules.transfer.application.item_import import (
    ImportItems,
    InspectItemImport,
    PlanItemImport,
)
from app.modules.transfer.application.stored_imports import (
    DeleteItemImport,
    GetItemImport,
    InspectStoredItemImport,
    ListItemImports,
    PlanStoredItemImport,
    QueueItemImport,
    UploadItemImport,
)
from app.modules.transfer.ports.import_file_store import ImportFileStore
from app.modules.transfer.ports.unit_of_work import TransferRepos, TransferUnitOfWork
from app.platform.config.transfer import get_transfer_settings
from app.platform.database import get_session_factory
from app.shared_kernel.access_guard import AccessGuard
from app.shared_kernel.job_queue import JobQueue

if TYPE_CHECKING:
    from collections.abc import AsyncIterator

    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker


def get_transfer_uow(
    session_factory: Annotated[
        async_sessionmaker[AsyncSession], Depends(get_session_factory)
    ],
) -> TransferUnitOfWork:
    """Return a unit of work over the source links table, for commands."""
    return create_transfer_uow(session_factory)


async def get_transfer_repos(
    session_factory: Annotated[
        async_sessionmaker[AsyncSession], Depends(get_session_factory)
    ],
) -> AsyncIterator[TransferRepos]:
    """Return a read-only repository bundle, for queries."""
    async with session_factory() as session:
        yield build_transfer_repos(session)


def get_inspect_item_import_use_case(
    guard: Annotated[AccessGuard, Depends(get_access_guard)],
    presets: Annotated[PresetPackTarget, Depends(get_preset_pack_target)],
    graph: Annotated[GraphPackTarget, Depends(get_graph_pack_target)],
) -> InspectItemImport:
    return InspectItemImport(guard, presets, graph)


def get_plan_item_import_use_case(
    repos: Annotated[TransferRepos, Depends(get_transfer_repos)],
    guard: Annotated[AccessGuard, Depends(get_access_guard)],
    presets: Annotated[PresetPackTarget, Depends(get_preset_pack_target)],
    graph: Annotated[GraphPackTarget, Depends(get_graph_pack_target)],
) -> PlanItemImport:
    return PlanItemImport(repos, guard, presets, graph)


def get_import_items_use_case(
    uow: Annotated[TransferUnitOfWork, Depends(get_transfer_uow)],
    guard: Annotated[AccessGuard, Depends(get_access_guard)],
    presets: Annotated[PresetPackTarget, Depends(get_preset_pack_target)],
    graph: Annotated[GraphPackTarget, Depends(get_graph_pack_target)],
) -> ImportItems:
    return ImportItems(uow, guard, presets, graph)


def get_import_file_store() -> ImportFileStore:
    """Return where uploaded import files wait."""
    return import_file_store()


def get_upload_item_import_use_case(
    uow: Annotated[TransferUnitOfWork, Depends(get_transfer_uow)],
    guard: Annotated[AccessGuard, Depends(get_access_guard)],
    store: Annotated[ImportFileStore, Depends(get_import_file_store)],
) -> UploadItemImport:
    keep_for = timedelta(hours=get_transfer_settings().import_ttl_hours)
    return UploadItemImport(uow, guard, store, keep_for)


def get_list_item_imports_use_case(
    repos: Annotated[TransferRepos, Depends(get_transfer_repos)],
    guard: Annotated[AccessGuard, Depends(get_access_guard)],
) -> ListItemImports:
    return ListItemImports(repos, guard)


def get_get_item_import_use_case(
    repos: Annotated[TransferRepos, Depends(get_transfer_repos)],
    guard: Annotated[AccessGuard, Depends(get_access_guard)],
) -> GetItemImport:
    return GetItemImport(repos, guard)


def get_delete_item_import_use_case(
    uow: Annotated[TransferUnitOfWork, Depends(get_transfer_uow)],
    guard: Annotated[AccessGuard, Depends(get_access_guard)],
    store: Annotated[ImportFileStore, Depends(get_import_file_store)],
) -> DeleteItemImport:
    return DeleteItemImport(uow, guard, store)


def get_inspect_stored_item_import_use_case(
    repos: Annotated[TransferRepos, Depends(get_transfer_repos)],
    guard: Annotated[AccessGuard, Depends(get_access_guard)],
    store: Annotated[ImportFileStore, Depends(get_import_file_store)],
    inspect: Annotated[InspectItemImport, Depends(get_inspect_item_import_use_case)],
) -> InspectStoredItemImport:
    return InspectStoredItemImport(repos, guard, store, inspect)


def get_plan_stored_item_import_use_case(
    repos: Annotated[TransferRepos, Depends(get_transfer_repos)],
    guard: Annotated[AccessGuard, Depends(get_access_guard)],
    store: Annotated[ImportFileStore, Depends(get_import_file_store)],
    plan: Annotated[PlanItemImport, Depends(get_plan_item_import_use_case)],
) -> PlanStoredItemImport:
    return PlanStoredItemImport(repos, guard, store, plan)


def get_queue_item_import_use_case(
    uow: Annotated[TransferUnitOfWork, Depends(get_transfer_uow)],
    guard: Annotated[AccessGuard, Depends(get_access_guard)],
    jobs: Annotated[JobQueue, Depends(get_job_queue)],
) -> QueueItemImport:
    return QueueItemImport(uow, guard, jobs)


@lru_cache(maxsize=1)
def get_codecs() -> CodecRegistry:
    """Return every file format this server reads and writes (built once)."""
    return CodecRegistry([MenageristBundleCodec()])


def get_plan_bundle_import_use_case(
    guard: Annotated[AccessGuard, Depends(get_access_guard)],
    codecs: Annotated[CodecRegistry, Depends(get_codecs)],
    presets: Annotated[PresetPackTarget, Depends(get_preset_pack_target)],
    graph: Annotated[GraphPackTarget, Depends(get_graph_pack_target)],
    collections: Annotated[CollectionPackTarget, Depends(get_collection_pack_target)],
) -> PlanBundleImport:
    return PlanBundleImport(guard, codecs, presets, graph, collections)


def get_import_bundle_use_case(
    guard: Annotated[AccessGuard, Depends(get_access_guard)],
    codecs: Annotated[CodecRegistry, Depends(get_codecs)],
    presets: Annotated[PresetPackTarget, Depends(get_preset_pack_target)],
    graph: Annotated[GraphPackTarget, Depends(get_graph_pack_target)],
    collections: Annotated[CollectionPackTarget, Depends(get_collection_pack_target)],
) -> ImportBundle:
    return ImportBundle(guard, codecs, presets, graph, collections)


def get_export_bundle_use_case(
    guard: Annotated[AccessGuard, Depends(get_access_guard)],
    codecs: Annotated[CodecRegistry, Depends(get_codecs)],
    presets: Annotated[PresetPackTarget, Depends(get_preset_pack_target)],
    graph: Annotated[GraphPackTarget, Depends(get_graph_pack_target)],
    collections: Annotated[CollectionPackTarget, Depends(get_collection_pack_target)],
) -> ExportBundle:
    return ExportBundle(guard, codecs, presets, graph, collections)
