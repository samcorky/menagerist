from dataclasses import dataclass

from app.modules.identity.ports.session_repository import SessionRepository
from app.modules.identity.ports.sign_in_attempt_repository import (
    SignInAttemptRepository,
)
from app.modules.identity.ports.user_repository import UserRepository
from app.shared_kernel.unit_of_work import UnitOfWork


@dataclass(kw_only=True)
class IdentityRepos:
    """The identity module's repository bundle."""

    users: UserRepository
    sessions: SessionRepository
    attempts: SignInAttemptRepository


IdentityUnitOfWork = UnitOfWork[IdentityRepos]
