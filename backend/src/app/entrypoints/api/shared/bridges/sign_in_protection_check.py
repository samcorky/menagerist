"""Bridge sign-in protection locks into warn-only system readiness diagnostics."""

from datetime import UTC, datetime
from typing import TYPE_CHECKING

import structlog

from app.entrypoints.api.shared.access_guard import get_access_guard
from app.modules.identity.adapters.persistence.unit_of_work import build_identity_repos
from app.modules.identity.application.assess_sign_in_protection import (
    AssessSignInProtection,
    AssessSignInProtectionQuery,
    SignInProtection,
)
from app.modules.system.domain.readiness import CheckObservation, CheckStatus
from app.platform.database import DATABASE_OUTAGE_ERRORS
from app.shared_kernel.actor import SYSTEM_ACTOR

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

logger = structlog.get_logger(__name__)

ACCOUNTS_KEY = "identity:lockedAccounts"
NAMES_KEY = "identity:guessedNames"
ADDRESSES_KEY = "identity:lockedAddresses"
ALL_KEYS = (ACCOUNTS_KEY, NAMES_KEY, ADDRESSES_KEY)


def _plural(count: int, one: str, many: str) -> str:
    return f"{count} {one if count == 1 else many}"


class SignInProtectionCheck:
    """Warn while sign-in protection holds locks, including on check failure.

    Counts only: the locks are stored as hashes, so no username or address can
    appear in the output.
    """

    def __init__(self, factory: async_sessionmaker[AsyncSession]) -> None:
        self._factory = factory

    async def run(self) -> dict[str, CheckObservation]:
        """Count current locks in a short session; a failure only warns."""
        now = datetime.now(UTC)
        try:
            async with self._factory() as session:
                protection = await AssessSignInProtection(
                    build_identity_repos(session),
                    get_access_guard(),
                ).handle(AssessSignInProtectionQuery(now=now), SYSTEM_ACTOR)
        except Exception as error:
            if isinstance(error, DATABASE_OUTAGE_ERRORS):
                logger.warning(
                    "sign-in protection check failed", error=type(error).__name__
                )
            else:
                logger.exception("sign-in protection check failed")
            return {
                key: CheckObservation(
                    component_type="component",
                    observed_value="unknown",
                    observed_unit="locked",
                    status=CheckStatus.WARN,
                    time=now,
                    output="Sign-in protection could not be checked.",
                )
                for key in ALL_KEYS
            }
        return self._observations(protection, now)

    @staticmethod
    def _observations(
        protection: SignInProtection, now: datetime
    ) -> dict[str, CheckObservation]:
        def row(count: int, output: str) -> CheckObservation:
            return CheckObservation(
                component_type="component",
                observed_value=count,
                observed_unit="locked",
                status=CheckStatus.WARN if count else CheckStatus.PASS,
                time=now,
                output=output if count else None,
            )

        accounts = protection.locked_accounts
        names = protection.unknown_names
        addresses = protection.locked_addresses
        accounts_text = " ".join(
            [
                f"{_plural(accounts, 'account is', 'accounts are')} locked after",
                "repeated failed sign-ins. Unlock from the Users page.",
            ]
        )
        names_text = " ".join(
            [
                _plural(names, "locked sign-in name", "locked sign-in names"),
                "matches" if names == 1 else "match",
                "no account, which can mean someone is guessing usernames.",
            ]
        )
        addresses_text = " ".join(
            [
                _plural(addresses, "client address is", "client addresses are"),
                "locked after repeated failed attempts, and requests from",
                "it are" if addresses == 1 else "them are",
                "refused (HTTP 429) until the lock ends.",
                "If this is most of your users, check that your reverse proxy is",
                "trusted (MENAGERIST_API_TRUSTED_PROXIES): an untrusted proxy makes",
                "every client look like one address.",
            ]
        )
        return {
            ACCOUNTS_KEY: row(accounts, accounts_text),
            NAMES_KEY: row(names, names_text),
            ADDRESSES_KEY: row(addresses, addresses_text),
        }
