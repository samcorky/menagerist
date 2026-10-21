"""Fixtures wiring identity use cases over in-memory adapters."""

import uuid
from collections.abc import Callable
from dataclasses import dataclass
from datetime import timedelta
from typing import TYPE_CHECKING

import pytest

from app.entrypoints.api.shared.authorisation import RoleAuthorisationAdapter
from app.modules.identity.adapters.claim.no_op_existing_data_claim import (
    NoOpExistingDataClaim,
)
from app.modules.identity.adapters.security.in_memory_password_hasher import (
    InMemoryPasswordHasher,
)
from app.modules.identity.adapters.security.password_authenticator import (
    PasswordAuthenticator,
)
from app.modules.identity.adapters.security.session_token_generator import (
    InMemorySessionTokenGenerator,
)
from app.modules.identity.application.change_password import ChangePassword
from app.modules.identity.application.create_user import CreateUser
from app.modules.identity.application.get_current_user import GetCurrentUser
from app.modules.identity.application.list_users import ListUsers
from app.modules.identity.application.reset_password import ResetPassword
from app.modules.identity.application.set_own_display_name import SetOwnDisplayName
from app.modules.identity.application.setup_first_admin import SetupFirstAdmin
from app.modules.identity.application.sign_in import SignIn
from app.modules.identity.application.sign_in_throttle import SignInThrottle
from app.modules.identity.application.sign_out import SignOut
from app.modules.identity.application.unlock_user import UnlockUser
from app.modules.identity.application.update_user import UpdateUser
from app.modules.identity.domain.user import Role, User
from app.modules.identity.ports.existing_data_claim import ClaimReport
from app.modules.identity.ports.unit_of_work import IdentityRepos
from app.shared_kernel.actor import Actor

if TYPE_CHECKING:
    from app.modules.identity.ports.existing_data_claim import ExistingDataClaim
    from tests.modules.identity.conftest import World

TTL = timedelta(hours=1)  # also used by the tests as the session lifetime


def _actor_for(user: User) -> Actor:
    return Actor(id=user.id, roles=frozenset({user.role.value}))


class SpyClaim:
    """An `ExistingDataClaim` recording who it was asked to claim for."""

    def __init__(self, report: ClaimReport) -> None:
        self.report = report
        self.owners: list[object] = []

    async def claim(self, owner_id: object) -> ClaimReport:
        """Record the owner and return the canned report."""
        self.owners.append(owner_id)
        return self.report


@dataclass(kw_only=True)
class Cases:
    """Every identity use case wired to one in-memory world."""

    setup: SetupFirstAdmin
    sign_in: SignIn
    sign_out: SignOut
    current_user: GetCurrentUser
    change_password: ChangePassword
    create_user: CreateUser
    list_users: ListUsers
    update_user: UpdateUser
    reset_password: ResetPassword
    unlock_user: UnlockUser
    set_own_display_name: SetOwnDisplayName
    throttle: SignInThrottle


def build_cases(world: World, claim: ExistingDataClaim | None = None) -> Cases:
    """Wire the use cases over `world` with deterministic tokens and hashing."""
    hasher = InMemoryPasswordHasher()
    tokens = InMemorySessionTokenGenerator()
    decoy = hasher.hash("decoy")
    authenticator = PasswordAuthenticator(world.uow, hasher, decoy_hash=decoy)
    auth = RoleAuthorisationAdapter()
    throttle = SignInThrottle()
    repos = IdentityRepos(
        users=world.users, sessions=world.sessions, attempts=world.attempts
    )
    return Cases(
        setup=SetupFirstAdmin(
            world.uow, hasher, tokens, claim or NoOpExistingDataClaim(), session_ttl=TTL
        ),
        sign_in=SignIn(
            world.uow,
            authenticator,
            tokens,
            hasher,
            throttle,
            decoy_hash=decoy,
            session_ttl=TTL,
        ),
        sign_out=SignOut(world.uow, tokens),
        current_user=GetCurrentUser(world.uow, tokens),
        change_password=ChangePassword(
            world.uow, hasher, tokens, throttle, session_ttl=TTL
        ),
        create_user=CreateUser(world.uow, auth, hasher),
        list_users=ListUsers(repos, auth),
        update_user=UpdateUser(world.uow, auth),
        reset_password=ResetPassword(world.uow, auth, hasher),
        unlock_user=UnlockUser(world.uow, auth),
        set_own_display_name=SetOwnDisplayName(world.uow),
        throttle=throttle,
    )


MakeCases = Callable[..., Cases]
MakeClaim = Callable[[ClaimReport], SpyClaim]
ActorFor = Callable[[User], Actor]


@pytest.fixture
def make_cases(world: World) -> MakeCases:
    """Return a factory wiring the use cases, optionally with a given claim port."""
    return lambda claim=None: build_cases(world, claim)


@pytest.fixture
def make_claim() -> MakeClaim:
    """Return a factory for a recording claim port."""
    return SpyClaim


@pytest.fixture
def actor_for() -> ActorFor:
    """Return a function giving the actor a request signed in as a user runs as."""
    return _actor_for


@pytest.fixture
def cases(world: World) -> Cases:
    """Use cases over the shared in-memory world."""
    return build_cases(world)


@pytest.fixture
def admin_actor() -> Actor:
    """An actor holding the administrator role."""
    return Actor(id=uuid.uuid7(), roles=frozenset({Role.ADMIN.value}))
