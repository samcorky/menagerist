"""Import and export bundle files: decode with a codec, then plan and apply."""

import uuid
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, ClassVar

import structlog

from app.modules.transfer.application.codecs import CodecRegistry  # noqa: TC001
from app.modules.transfer.application.extras import BundleExtras
from app.modules.transfer.application.permissions import TransferPermission
from app.modules.transfer.application.pipeline import (
    AppliedBundle,
    apply_bundle,
    plan_bundle,
)
from app.modules.transfer.domain.bundle import (
    BUNDLE_FORMAT,
    MAX_ITEMS,
    Bundle,
    preset_refs,
    unportable_condition,
)
from app.modules.transfer.domain.errors import InvalidBundleError
from app.modules.transfer.domain.plan import ClashPolicy, Plan
from app.shared_kernel.access import Access, Requires
from app.shared_kernel.cqrs import UseCase

if TYPE_CHECKING:
    from app.modules.transfer.domain.bundle import BundleCollection
    from app.modules.transfer.ports.targets import (
        CollectionTarget,
        GraphTarget,
        PresetTarget,
    )
    from app.shared_kernel.access_guard import AccessGuard
    from app.shared_kernel.actor import Actor

logger = structlog.get_logger()


@dataclass(kw_only=True)
class BundleFileRequest:
    """A parsed bundle file; its `format` field picks the codec that reads it."""

    data: Mapping[str, Any]


@dataclass(kw_only=True)
class ExportBundleQuery:
    """What to write to a file, and the format to write it in.

    The saved lists, fields and groups the types use are written too.
    """

    preset_ids: list[uuid.UUID] = field(default_factory=list)
    item_type_ids: list[uuid.UUID] = field(default_factory=list)
    relationship_type_ids: list[uuid.UUID] = field(default_factory=list)
    item_ids: list[uuid.UUID] = field(default_factory=list)
    collection_ids: list[uuid.UUID] = field(default_factory=list)
    format: str = BUNDLE_FORMAT


class _FileUseCase:
    def __init__(
        self,
        guard: AccessGuard,
        codecs: CodecRegistry,
        presets: PresetTarget,
        graph: GraphTarget,
        collections: CollectionTarget,
    ) -> None:
        """Initialise with the access guard, the codecs and the targets."""
        self._guard = guard
        self._codecs = codecs
        self._presets = presets
        self._graph = graph
        self._collections = collections

    def _decode(self, request: BundleFileRequest) -> Bundle:
        return self._codecs.get(request.data.get("format")).decode(request.data)


class PlanBundleImport(_FileUseCase, UseCase[BundleFileRequest, Plan]):
    """Return the plan `ImportBundle` would apply to a file; nothing is written.

    A taken type name is skipped, as importing keeps what the person has.

    Raises:
        UnknownFormatError: no codec reads the file's format.
        ValidationError: the file, or something in it, is not valid.
    """

    access: ClassVar[Access] = Requires(TransferPermission.BUNDLE_IMPORT)

    async def _handle(self, request: BundleFileRequest, actor: Actor) -> Plan:
        """Decode the file and plan it against what the person has."""
        bundle = self._decode(request)
        return await plan_bundle(
            bundle,
            self._presets,
            self._graph,
            clash=ClashPolicy.SKIP,
            extras=BundleExtras(collections=self._collections),
        )


class ImportBundle(_FileUseCase, UseCase[BundleFileRequest, AppliedBundle]):
    """Import a file: plan it as `PlanBundleImport` does, then apply that plan.

    Raises:
        UnknownFormatError: no codec reads the file's format.
        ValidationError: the file, or something in it, is not valid.
    """

    access: ClassVar[Access] = Requires(TransferPermission.BUNDLE_IMPORT)

    async def _handle(self, request: BundleFileRequest, actor: Actor) -> AppliedBundle:
        """Decode, plan and apply the file."""
        bundle = self._decode(request)
        extras = BundleExtras(collections=self._collections)
        plan = await plan_bundle(
            bundle, self._presets, self._graph, clash=ClashPolicy.SKIP, extras=extras
        )
        applied = await apply_bundle(
            plan, bundle, self._presets, self._graph, extras=extras
        )
        logger.info(
            "bundle imported",
            created=applied.total_created,
            skipped=applied.total_skipped,
        )
        return applied


class ExportBundle(_FileUseCase, UseCase[ExportBundleQuery, dict[str, Any]]):
    """Write the person's presets, types, items and collections given as a file.

    A type's saved lists come with it, so the file can be imported on its own.

    Raises:
        UnknownFormatError: no codec writes the format asked for.
        InvalidBundleError: there is nothing to export.
        NotFoundError: an id is not one of the person's own.
    """

    access: ClassVar[Access] = Requires(TransferPermission.BUNDLE_READ)

    async def _handle(self, request: ExportBundleQuery, actor: Actor) -> dict[str, Any]:
        """Read the types, then the presets they use and those asked for, and encode."""
        codec = self._codecs.get(request.format)
        if not (
            request.preset_ids
            or request.item_type_ids
            or request.relationship_type_ids
            or request.item_ids
            or request.collection_ids
        ):
            raise InvalidBundleError("Choose something to export.")
        collections = await self._collections.read_collections(
            list(dict.fromkeys(request.collection_ids))
        )
        _refuse_unportable(collections)
        # A manual collection brings its items, so the file stands alone.
        item_ids = _with_ids(
            request.item_ids, (ref for c in collections for ref in c.item_refs)
        )
        if len(item_ids) > MAX_ITEMS:
            raise InvalidBundleError(
                f"A file holds at most {MAX_ITEMS} items; this export has "
                + f"{len(item_ids)}. Choose fewer items or collections."
            )
        items = await self._graph.read_items(item_ids)
        connections = await self._graph.read_connections(item_ids)
        # Items and connections bring the types they use, so the file stands alone.
        item_types = await self._graph.read_item_types(
            _with_ids(request.item_type_ids, (i.type_ref for i in items))
        )
        relationship_types = await self._graph.read_relationship_types(
            _with_ids(request.relationship_type_ids, (c.type_ref for c in connections))
        )
        wanted = {str(i): i for i in request.preset_ids}
        schemas = [t.attributes_schema for t in item_types]
        schemas += [r.attributes_schema for r in relationship_types]
        for schema in schemas:
            for ref in sorted(preset_refs(schema)):
                wanted.setdefault(ref, uuid.UUID(ref))
        presets = await self._presets.read(list(wanted.values()))
        return codec.encode(
            Bundle(
                id=codec.format,
                presets=tuple(presets),
                relationship_types=tuple(relationship_types),
                item_types=tuple(item_types),
                items=tuple(items),
                connections=tuple(connections),
                collections=tuple(collections),
            )
        )


def _refuse_unportable(collections: Iterable[BundleCollection]) -> None:
    """Refuse a smart collection that would behave differently once imported."""
    for collection in collections:
        if collection.definition is None:
            continue
        found = unportable_condition(collection.definition)
        if found is not None:
            path, reason = found
            raise InvalidBundleError(
                f"Collection '{collection.name}' cannot be exported: its condition "
                + f"at '{path}' is not portable ({reason})"
            )


def _with_ids(asked: list[uuid.UUID], refs: Iterable[str | None]) -> list[uuid.UUID]:
    """The ids asked for, then those of `refs` not already there; refs are ids."""
    ids = dict.fromkeys(asked)
    ids.update(dict.fromkeys(uuid.UUID(r) for r in refs if r is not None))
    return list(ids)
