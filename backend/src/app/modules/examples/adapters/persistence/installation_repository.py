import uuid
from typing import TYPE_CHECKING, Any

import structlog
from sqlalchemy import select

from app.modules.examples.adapters.persistence.models import ExampleInstallationModel
from app.modules.examples.domain.installation import (
    EntityKind,
    EntityRecord,
    Installation,
    InstallationStatus,
    Outcome,
)

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

logger = structlog.get_logger()
_ACTIVE = (InstallationStatus.INSTALLING.value, InstallationStatus.INSTALLED.value)


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


def _to_domain(model: ExampleInstallationModel) -> Installation:
    return Installation(
        id=model.id,
        pack_id=model.pack_id,
        status=InstallationStatus(model.status),
        entities=[_record_from_json(d) for d in model.entities],
        installed_at=model.installed_at,
        removed_at=model.removed_at,
        created_at=model.created_at,
        updated_at=model.updated_at,
    )


def _to_model(installation: Installation) -> ExampleInstallationModel:
    return ExampleInstallationModel(
        id=installation.id,
        pack_id=installation.pack_id,
        status=installation.status.value,
        entities=[_record_to_json(r) for r in installation.entities],
        installed_at=installation.installed_at,
        removed_at=installation.removed_at,
        created_at=installation.created_at,
        updated_at=installation.updated_at,
    )


class SqlAlchemyInstallationRepository:
    """Postgres-backed `InstallationRepository`, scoped to one session."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def add(self, installation: Installation) -> None:
        """Add a new installation."""
        logger.debug("adding example installation", installation_id=installation.id)
        self._session.add(_to_model(installation))
        await self._session.flush()

    async def save(self, installation: Installation) -> None:
        """Persist changes to an existing installation."""
        logger.debug("saving example installation", installation_id=installation.id)
        await self._session.merge(_to_model(installation))
        await self._session.flush()

    async def get(self, installation_id: uuid.UUID) -> Installation | None:
        """Return the installation with `installation_id`, or `None`."""
        model = await self._session.get(ExampleInstallationModel, installation_id)
        return None if model is None else _to_domain(model)

    async def get_active_for_pack(self, pack_id: str) -> Installation | None:
        """Return the installing or installed installation of `pack_id`, if any."""
        stmt = select(ExampleInstallationModel).where(
            ExampleInstallationModel.pack_id == pack_id,
            ExampleInstallationModel.status.in_(_ACTIVE),
        )
        model = (await self._session.execute(stmt)).scalar_one_or_none()
        return None if model is None else _to_domain(model)

    async def list_active(self) -> list[Installation]:
        """Return every installing or installed installation, oldest first."""
        stmt = (
            select(ExampleInstallationModel)
            .where(ExampleInstallationModel.status.in_(_ACTIVE))
            .order_by(ExampleInstallationModel.id)
        )
        return [_to_domain(m) for m in (await self._session.execute(stmt)).scalars()]
