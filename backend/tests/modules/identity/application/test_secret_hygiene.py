import uuid
from datetime import timedelta
from typing import TYPE_CHECKING

import pytest

from app.modules.identity.adapters.security.session_token_generator import (
    InMemorySessionTokenGenerator,
)
from app.modules.identity.application.change_password import ChangePasswordCommand
from app.modules.identity.application.create_user import CreateUserCommand
from app.modules.identity.application.get_current_user import GetCurrentUserQuery
from app.modules.identity.application.reset_password import ResetPasswordCommand
from app.modules.identity.application.setup_first_admin import SetupFirstAdminCommand
from app.modules.identity.application.sign_in import SignIn, SignInCommand
from app.modules.identity.application.sign_out import SignOutCommand
from app.modules.identity.domain.errors import InvalidCredentialsError
from app.modules.identity.ports.authenticator import VerifiedIdentity
from app.shared_kernel.actor import ANONYMOUS_ACTOR

if TYPE_CHECKING:
    from app.modules.identity.ports.authenticator import PasswordCredentials
    from tests.modules.identity.conftest import MakeUser, World

SECRET = "s3cret-value-xyz"
TTL = timedelta(hours=1)


def test_commands_never_show_secrets_in_their_repr() -> None:
    """Passwords and tokens stay out of logs and tracebacks."""
    commands = [
        SignInCommand(username="alice", password=SECRET),
        SignOutCommand(token=SECRET),
        GetCurrentUserQuery(token=SECRET),
        ChangePasswordCommand(current_password=SECRET, new_password=SECRET),
        CreateUserCommand(username="alice", display_name="A", password=SECRET),
        ResetPasswordCommand(user_id=uuid.uuid7(), password=SECRET),
        SetupFirstAdminCommand(username="alice", display_name="A", password=SECRET),
    ]
    for command in commands:
        assert SECRET not in repr(command)
        assert SECRET not in str(command)


class _FixedAuthenticator:
    """Vouches for a username whatever the credentials are."""

    def __init__(self, subject: str) -> None:
        self._subject = subject

    async def authenticate(
        self, credentials: PasswordCredentials
    ) -> VerifiedIdentity | None:
        """Return the fixed identity."""
        return VerifiedIdentity(subject=self._subject, display_name="x")


@pytest.mark.parametrize("state", ["missing", "disabled"])
async def test_sign_in_rechecks_the_account_after_authentication(
    state: str, world: World, make_user: MakeUser
) -> None:
    """An account removed or disabled in between still gets the generic refusal."""
    user = make_user("alice")
    if state == "disabled":
        user.disable()
        await world.users.add(user)
    use_case = SignIn(
        world.uow,
        _FixedAuthenticator("alice"),
        InMemorySessionTokenGenerator(),
        session_ttl=TTL,
    )

    with pytest.raises(InvalidCredentialsError):
        await use_case.handle(
            SignInCommand(username="alice", password="x"), ANONYMOUS_ACTOR
        )

    assert not world.uow.committed
