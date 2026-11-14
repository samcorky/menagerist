import uuid
from typing import TYPE_CHECKING, Any

import structlog
from sqlalchemy import select

from app.modules.transfer.adapters.persistence.models import RunModel
from app.modules.transfer.domain.entity_kind import EntityKind
from app.modules.transfer.domain.run import EntityRecord, Outcome, Run, RunStatus
from app.platform.orm_mixins import claim_rows, owned_by

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

    from app.shared_kernel.content_filter import ContentFilter

logger = structlog.get_logger()
_ACTIVE = (RunStatus.INSTALLING.value, RunStatus.INSTALLED.value)


def _record_to_json(record: EntityRecord) -> dict[str, Any]:
    return {
        "kind": record.kind.value,
        "ref": record.ref,
        "label": record.label,
        "entity_id": str(record.entity_id),
        "content_hash": record.content_hash,
        "outcome": record.outcome.value,
        "reason": record.reason,
    }


def _record_from_json(data: dict[str, Any]) -> EntityRecord:
    return EntityRecord(
        kind=EntityKind(data["kind"]),
        ref=data["ref"],
        label=data["label"],
        entity_id=uuid.UUID(data["entity_id"]),
        content_hash=data["content_hash"],
        outcome=Outcome(data["outcome"]),
        reason=data.get("reason"),
    )


def _to_domain(model: RunModel) -> Run:
    return Run(
        id=model.id,
        owner_id=model.owner_id,
        bundle_id=model.pack_id,
        status=RunStatus(model.status),
        entities=[_record_from_json(d) for d in model.entities],
        installed_at=model.installed_at,
        removed_at=model.removed_at,
        created_at=model.created_at,
        updated_at=model.updated_at,
    )


def _to_model(run: Run) -> RunModel:
    return RunModel(
        id=run.id,
        owner_id=run.owner_id,
        pack_id=run.bundle_id,
        status=run.status.value,
        entities=[_record_to_json(r) for r in run.entities],
        installed_at=run.installed_at,
        removed_at=run.removed_at,
        created_at=run.created_at,
        updated_at=run.updated_at,
    )


class SqlAlchemyRunRepository:
    """Postgres-backed `RunRepository`, scoped to one session."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def add(self, run: Run) -> None:
        """Add a new run."""
        logger.debug("adding bundle run", run_id=run.id)
        self._session.add(_to_model(run))
        await self._session.flush()

    async def save(self, run: Run) -> None:
        """Persist changes to an existing run."""
        logger.debug("saving bundle run", run_id=run.id)
        await self._session.merge(_to_model(run))
        await self._session.flush()

    async def get(self, run_id: uuid.UUID, *, scope: ContentFilter) -> Run | None:
        """Return the run with `run_id` in `scope`, or `None`."""
        stmt = select(RunModel).where(
            RunModel.id == run_id,
            owned_by(RunModel, scope.user_id),
        )
        model = (await self._session.execute(stmt)).scalar_one_or_none()
        return None if model is None else _to_domain(model)

    async def get_active_for_bundle(
        self, bundle_id: str, *, scope: ContentFilter
    ) -> Run | None:
        """Return the installing or installed run of `bundle_id`, if any."""
        stmt = select(RunModel).where(
            RunModel.pack_id == bundle_id,
            RunModel.status.in_(_ACTIVE),
            owned_by(RunModel, scope.user_id),
        )
        # Several people may hold the bundle when the scope is everyone: newest wins.
        stmt = stmt.order_by(RunModel.id.desc()).limit(1)
        model = (await self._session.execute(stmt)).scalar_one_or_none()
        return None if model is None else _to_domain(model)

    async def list_active(self, *, scope: ContentFilter) -> list[Run]:
        """Return every installing or installed run, oldest first."""
        stmt = (
            select(RunModel)
            .where(
                RunModel.status.in_(_ACTIVE),
                owned_by(RunModel, scope.user_id),
            )
            .order_by(RunModel.id)
        )
        return [_to_domain(m) for m in (await self._session.execute(stmt)).scalars()]

    async def list_for_bundle(
        self, bundle_id: str, *, scope: ContentFilter
    ) -> list[Run]:
        """Return every run of `bundle_id`, whatever its status, newest first."""
        stmt = (
            select(RunModel)
            .where(
                RunModel.pack_id == bundle_id,
                owned_by(RunModel, scope.user_id),
            )
            .order_by(RunModel.id.desc())
        )
        return [_to_domain(m) for m in (await self._session.execute(stmt)).scalars()]

    async def claim_orphaned(
        self, owner_id: uuid.UUID, *, legacy_owner_ids: frozenset[uuid.UUID]
    ) -> int:
        """Give `owner_id` every run with no owner or a legacy owner."""
        return await claim_rows(self._session, RunModel, owner_id, legacy_owner_ids)
