"""Fixtures wiring identity use cases over in-memory adapters."""

import uuid
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import timedelta
from typing import TYPE_CHECKING

import pytest

from app.entrypoints.api.shared.access_guard import get_access_guard
from app.entrypoints.api.shared.authorisation import (
    TOKEN_GRANTABLE_PERMISSIONS,
    get_authorisation_port,
)
from app.modules.identity.adapters.claim.no_op_existing_data_claim import (
    NoOpExistingDataClaim,
)
from app.modules.identity.adapters.security.in_memory_password_hasher import (
    InMemoryPasswordHasher,
)
from app.modules.identity.adapters.security.password_authenticator import (
    PasswordAuthenticator,
)
from app.modules.identity.adapters.security.secrets_api_token_generator import (
    SecretsApiTokenGenerator,
)
from app.modules.identity.adapters.security.session_token_generator import (
    InMemorySessionTokenGenerator,
)
from app.modules.identity.application.authenticate_api_token import AuthenticateApiToken
from app.modules.identity.application.change_password import ChangePassword
from app.modules.identity.application.create_api_token import (
    CreateApiToken,
    CreateApiTokenCommand,
    CreatedApiToken,
)
from app.modules.identity.application.create_user import CreateUser
from app.modules.identity.application.get_current_user import GetCurrentUser
from app.modules.identity.application.list_grantable_permissions import (
    ListGrantablePermissions,
)
from app.modules.identity.application.list_own_api_tokens import ListOwnApiTokens
from app.modules.identity.application.list_users import ListUsers
from app.modules.identity.application.reset_password import ResetPassword
from app.modules.identity.application.revoke_own_api_token import RevokeOwnApiToken
from app.modules.identity.application.rotate_api_token import RotateApiToken
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

GRANTABLE = frozenset(p.value for p in TOKEN_GRANTABLE_PERMISSIONS)
DEFAULT_DAYS = 90
MAX_DAYS = 365
MAX_TOKENS = 20
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
    create_api_token: CreateApiToken
    list_own_api_tokens: ListOwnApiTokens
    revoke_own_api_token: RevokeOwnApiToken
    rotate_api_token: RotateApiToken
    authenticate_api_token: AuthenticateApiToken
    list_grantable: ListGrantablePermissions
    api_tokens: SecretsApiTokenGenerator


def build_cases(world: World, claim: ExistingDataClaim | None = None) -> Cases:
    """Wire the use cases over `world` with deterministic tokens and hashing."""
    hasher = InMemoryPasswordHasher()
    tokens = InMemorySessionTokenGenerator()
    decoy = hasher.hash("decoy")
    authenticator = PasswordAuthenticator(world.uow, hasher, decoy_hash=decoy)
    guard = get_access_guard()
    api_tokens = SecretsApiTokenGenerator()
    authorisation = get_authorisation_port()
    throttle = SignInThrottle()
    repos = IdentityRepos(
        users=world.users,
        sessions=world.sessions,
        attempts=world.attempts,
        tokens=world.tokens,
    )
    return Cases(
        setup=SetupFirstAdmin(
            world.uow,
            get_access_guard(),
            hasher,
            tokens,
            claim or NoOpExistingDataClaim(),
            session_ttl=TTL,
        ),
        sign_in=SignIn(
            world.uow,
            get_access_guard(),
            authenticator,
            tokens,
            hasher,
            throttle,
            decoy_hash=decoy,
            session_ttl=TTL,
        ),
        sign_out=SignOut(world.uow, get_access_guard(), tokens),
        current_user=GetCurrentUser(world.uow, get_access_guard(), tokens),
        change_password=ChangePassword(
            world.uow, get_access_guard(), hasher, tokens, throttle, session_ttl=TTL
        ),
        create_user=CreateUser(world.uow, guard, hasher),
        list_users=ListUsers(repos, guard),
        update_user=UpdateUser(world.uow, guard),
        reset_password=ResetPassword(world.uow, guard, hasher),
        unlock_user=UnlockUser(world.uow, guard),
        set_own_display_name=SetOwnDisplayName(world.uow, get_access_guard()),
        throttle=throttle,
        create_api_token=CreateApiToken(
            world.uow,
            guard,
            hasher,
            api_tokens,
            throttle,
            authorisation,
            grantable=GRANTABLE,
            default_days=DEFAULT_DAYS,
            max_days=MAX_DAYS,
            max_tokens=MAX_TOKENS,
        ),
        list_own_api_tokens=ListOwnApiTokens(repos, guard),
        revoke_own_api_token=RevokeOwnApiToken(world.uow, guard),
        rotate_api_token=RotateApiToken(
            world.uow,
            guard,
            hasher,
            api_tokens,
            throttle,
            authorisation,
            default_days=DEFAULT_DAYS,
            max_days=MAX_DAYS,
        ),
        authenticate_api_token=AuthenticateApiToken(world.uow, guard, api_tokens),
        list_grantable=ListGrantablePermissions(
            repos, guard, authorisation, grantable=GRANTABLE
        ),
        api_tokens=api_tokens,
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


IssueToken = Callable[..., Awaitable[CreatedApiToken]]


@pytest.fixture
def issue_token(cases: Cases, actor_for: ActorFor) -> IssueToken:
    """Return a coroutine function issuing a token for a stored user."""

    async def _issue(
        user: User,
        *,
        name: str = "Script",
        grants: frozenset[str] = frozenset({"graph:item:read"}),
        days: int | None = None,
    ) -> CreatedApiToken:
        return await cases.create_api_token.handle(
            CreateApiTokenCommand(
                name=name,
                password="password-123",
                grants=grants,
                expires_in_days=days,
            ),
            actor_for(user),
        )

    return _issue
