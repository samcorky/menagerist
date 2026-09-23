from datetime import UTC, datetime
from typing import TYPE_CHECKING

from app.modules.system.adapters.platform.checks._util import (
    failed_observation,
    observation,
)
from app.modules.system.domain.readiness import CheckObservation, CheckStatus
from app.platform.alembic_runner import code_head_revisions, db_current_revisions

if TYPE_CHECKING:
    from collections.abc import Mapping

    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker


class DatabaseMigrationCheck:
    """Verifies the database's applied migrations match what the code expects."""

    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._session_factory = session_factory

    async def run(self) -> Mapping[str, CheckObservation]:
        """Compare the database's current revisions against the code's head."""
        now = datetime.now(UTC)
        code_revisions = code_head_revisions()
        code_rev_str = ", ".join(sorted(code_revisions)) if code_revisions else "none"
        # Broad Exception here: same rationale as DatabaseConnectivityCheck - pool
        # connect failures propagate as raw OSError, not SQLAlchemyError.
        try:
            db_revisions = await db_current_revisions(self._session_factory)
            db_rev_str = ", ".join(sorted(db_revisions)) if db_revisions else "none"
            migration_ok = set(db_revisions) == set(code_revisions)
            mismatch = f"database at {db_rev_str}, code expects {code_rev_str}"
            return {
                "database:migrationRevision": observation(
                    db_rev_str,
                    "revision",
                    now=now,
                    status=CheckStatus.PASS if migration_ok else CheckStatus.FAIL,
                    output=None if migration_ok else mismatch,
                )
            }
        except Exception as exc:
            return {
                "database:migrationRevision": failed_observation(
                    "revision", now=now, exc=exc
                )
            }
