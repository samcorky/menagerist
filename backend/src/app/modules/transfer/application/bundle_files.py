"""Import and export bundle files: decode with a codec, then plan and apply."""

import uuid
from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, ClassVar

import structlog

from app.modules.transfer.application.codecs import CodecRegistry  # noqa: TC001
from app.modules.transfer.application.permissions import TransferPermission
from app.modules.transfer.application.pipeline import (
    AppliedBundle,
    apply_bundle,
    plan_bundle,
)
from app.modules.transfer.domain.bundle import BUNDLE_FORMAT, Bundle
from app.modules.transfer.domain.plan import ClashPolicy, Plan
from app.shared_kernel.access import Access, Requires
from app.shared_kernel.cqrs import UseCase

if TYPE_CHECKING:
    from app.modules.transfer.ports.targets import GraphTarget, PresetTarget
    from app.shared_kernel.access_guard import AccessGuard
    from app.shared_kernel.actor import Actor

logger = structlog.get_logger()


@dataclass(kw_only=True)
class BundleFileRequest:
    """A parsed bundle file; its `format` field picks the codec that reads it."""

    data: Mapping[str, Any]


@dataclass(kw_only=True)
class ExportBundleQuery:
    """The presets to write to a file, and the format to write it in."""

    preset_ids: list[uuid.UUID] = field(default_factory=list)
    format: str = BUNDLE_FORMAT


class _FileUseCase:
    def __init__(
        self,
        guard: AccessGuard,
        codecs: CodecRegistry,
        presets: PresetTarget,
        graph: GraphTarget,
    ) -> None:
        """Initialise with the access guard, the codecs and the targets."""
        self._guard = guard
        self._codecs = codecs
        self._presets = presets
        self._graph = graph

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
            bundle, self._presets, self._graph, clash=ClashPolicy.SKIP
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
        plan = await plan_bundle(
            bundle, self._presets, self._graph, clash=ClashPolicy.SKIP
        )
        applied = await apply_bundle(plan, bundle, self._presets, self._graph)
        logger.info(
            "bundle imported",
            created=applied.total_created,
            skipped=applied.total_skipped,
        )
        return applied


class ExportBundle(_FileUseCase, UseCase[ExportBundleQuery, dict[str, Any]]):
    """Write the person's presets with the ids given as a file.

    Raises:
        UnknownFormatError: no codec writes the format asked for.
        NotFoundError: an id is not one of the person's presets.
    """

    access: ClassVar[Access] = Requires(TransferPermission.BUNDLE_READ)

    async def _handle(self, request: ExportBundleQuery, actor: Actor) -> dict[str, Any]:
        """Read the presets and encode them."""
        codec = self._codecs.get(request.format)
        presets = await self._presets.read(request.preset_ids)
        return codec.encode(Bundle(id=codec.format, presets=tuple(presets)))
