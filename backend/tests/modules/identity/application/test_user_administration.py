import uuid
from datetime import UTC, datetime
from typing import TYPE_CHECKING

import pytest
import time_machine
from structlog.testing import capture_logs

from app.modules.identity.application.change_password import ChangePasswordCommand
from app.modules.identity.application.create_user import CreateUserCommand
from app.modules.identity.application.get_current_user import GetCurrentUserQuery
from app.modules.identity.application.list_users import ListUsersQuery
from app.modules.identity.application.reset_password import ResetPasswordCommand
from app.modules.identity.application.sign_in import SignInCommand
from app.modules.identity.application.update_user import UpdateUserCommand
from app.modules.identity.domain.errors import (
    CurrentPasswordIncorrectError,
    InvalidPasswordError,
    LastAdministratorError,
    UsernameTakenError,
    UserNotFoundError,
)
from app.modules.identity.domain.user import Role
from app.shared_kernel.actor import ANONYMOUS_ACTOR, SYSTEM_ACTOR, Actor
from app.shared_kernel.errors import ForbiddenError

if TYPE_CHECKING:
    from tests.modules.identity.application.conftest import ActorFor, Cases
    from tests.modules.identity.conftest import MakeUser, World

NOW = datetime(2026, 10, 10, 12, 0, tzinfo=UTC)
MEMBER = Actor(id=uuid.uuid7(), roles=frozenset({"member"}))


def _create(
    username: str = "bob", password: str = "initial-pass-1"
) -> CreateUserCommand:
    return CreateUserCommand(
        username=username, display_name="Bob", password=password, role=Role.MEMBER
    )


async def test_create_user_makes_a_member_who_must_change_the_password(
    cases: Cases, world: World, admin_actor: Actor
) -> None:
    """The admin sets an initial password; the new account must replace it."""
    user = await cases.create_user.handle(_create("Bob"), admin_actor)

    assert user.username == "bob"
    assert user.role is Role.MEMBER
    assert user.password_expired
    assert world.uow.committed
    assert await world.users.get(user.id) is user


async def test_create_user_rejects_duplicates_and_weak_passwords(
    cases: Cases, world: World, make_user: MakeUser, admin_actor: Actor
) -> None:
    """Usernames stay unique and passwords follow the rules."""
    await world.users.add(make_user("bob"))
    with pytest.raises(UsernameTakenError):
        await cases.create_user.handle(_create("BOB"), admin_actor)
    with pytest.raises(InvalidPasswordError):
        await cases.create_user.handle(_create("carol", "x"), admin_actor)


async def test_list_users_returns_everyone_for_admins_only(
    cases: Cases, world: World, make_user: MakeUser, admin_actor: Actor
) -> None:
    """Listing is admin-only."""
    await world.users.add(make_user("alice"))
    await world.users.add(make_user("bob"))

    assert len(await cases.list_users.handle(ListUsersQuery(), admin_actor)) == 2
    with pytest.raises(ForbiddenError):
        await cases.list_users.handle(ListUsersQuery(), MEMBER)


async def test_admin_only_commands_reject_members(
    cases: Cases, world: World, make_user: MakeUser
) -> None:
    """Create, update and reset all refuse a non-admin actor without writing."""
    target = make_user("alice")
    await world.users.add(target)
    with pytest.raises(ForbiddenError):
        await cases.create_user.handle(_create(), MEMBER)
    with pytest.raises(ForbiddenError):
        await cases.update_user.handle(
            UpdateUserCommand(user_id=target.id, display_name="X"), MEMBER
        )
    with pytest.raises(ForbiddenError):
        await cases.reset_password.handle(
            ResetPasswordCommand(user_id=target.id, password="another-pass-1"), MEMBER
        )
    assert not world.uow.committed


async def test_the_system_actor_passes_the_admin_gate(
    cases: Cases, world: World, make_user: MakeUser
) -> None:
    """The CLI runs as the system actor, which may administer accounts."""
    target = make_user("alice")
    await world.users.add(target)

    await cases.create_user.handle(_create(), SYSTEM_ACTOR)
    await cases.reset_password.handle(
        ResetPasswordCommand(user_id=target.id, password="another-pass-1"),
        SYSTEM_ACTOR,
    )
    users = await cases.list_users.handle(ListUsersQuery(), SYSTEM_ACTOR)

    assert {u.username for u in users} == {"alice", "bob"}


@time_machine.travel(NOW, tick=False)
async def test_update_user_changes_name_role_and_enabled_state(
    cases: Cases, world: World, make_user: MakeUser, admin_actor: Actor
) -> None:
    """Each optional field is applied; disabling also ends the user's sessions."""
    user = make_user("alice")
    await world.users.add(make_user("root", role=Role.ADMIN))
    await world.users.add(user)
    signed_in = await cases.sign_in.handle(
        SignInCommand(username="alice", password="password-123"), ANONYMOUS_ACTOR
    )

    updated = await cases.update_user.handle(
        UpdateUserCommand(
            user_id=user.id, display_name="  Alice B ", role=Role.ADMIN, disabled=True
        ),
        admin_actor,
    )

    assert (updated.display_name, updated.role, updated.disabled) == (
        "Alice B",
        Role.ADMIN,
        True,
    )
    enabled = await cases.update_user.handle(
        UpdateUserCommand(user_id=user.id, disabled=False), admin_actor
    )
    assert not enabled.disabled
    still_valid = await cases.current_user.handle(
        GetCurrentUserQuery(token=signed_in.token), ANONYMOUS_ACTOR
    )
    assert still_valid is None


async def test_update_user_unknown_id_is_not_found(
    cases: Cases, admin_actor: Actor
) -> None:
    """An unknown id raises UserNotFoundError."""
    with pytest.raises(UserNotFoundError):
        await cases.update_user.handle(
            UpdateUserCommand(user_id=uuid.uuid7(), display_name="X"), admin_actor
        )


async def test_the_last_active_admin_cannot_be_disabled(
    cases: Cases, world: World, make_user: MakeUser, admin_actor: Actor
) -> None:
    """Disabling the only enabled admin is a conflict and writes nothing."""
    admin = make_user("root", role=Role.ADMIN)
    await world.users.add(admin)

    with pytest.raises(LastAdministratorError):
        await cases.update_user.handle(
            UpdateUserCommand(user_id=admin.id, disabled=True), admin_actor
        )

    assert not world.uow.committed
    assert not admin.disabled


async def test_the_last_active_admin_cannot_be_demoted(
    cases: Cases, world: World, make_user: MakeUser, admin_actor: Actor
) -> None:
    """Demoting the only enabled admin is a conflict and writes nothing."""
    admin = make_user("root", role=Role.ADMIN)
    await world.users.add(admin)

    with pytest.raises(LastAdministratorError):
        await cases.update_user.handle(
            UpdateUserCommand(user_id=admin.id, role=Role.MEMBER), admin_actor
        )

    assert not world.uow.committed
    assert admin.role is Role.ADMIN


async def test_an_admin_can_be_demoted_while_another_remains(
    cases: Cases, world: World, make_user: MakeUser, admin_actor: Actor
) -> None:
    """With two enabled admins, one may step down."""
    first = make_user("root", role=Role.ADMIN)
    await world.users.add(first)
    await world.users.add(make_user("second", role=Role.ADMIN))

    updated = await cases.update_user.handle(
        UpdateUserCommand(user_id=first.id, role=Role.MEMBER), admin_actor
    )

    assert updated.role is Role.MEMBER


async def test_disabled_admins_do_not_count_as_a_remaining_admin(
    cases: Cases, world: World, make_user: MakeUser, admin_actor: Actor
) -> None:
    """A disabled admin does not rescue the last enabled one."""
    last = make_user("root", role=Role.ADMIN)
    gone = make_user("gone", role=Role.ADMIN)
    gone.disable()
    await world.users.add(last)
    await world.users.add(gone)

    with pytest.raises(LastAdministratorError):
        await cases.update_user.handle(
            UpdateUserCommand(user_id=last.id, disabled=True), admin_actor
        )


@time_machine.travel(NOW, tick=False)
async def test_reset_password_sets_initial_password_and_ends_sessions(
    cases: Cases, world: World, make_user: MakeUser, admin_actor: Actor
) -> None:
    """The user must change it again, may sign in with it, and loses old sessions."""
    user = make_user("alice")
    user.record_failure(NOW)
    await world.users.add(user)
    old = await cases.sign_in.handle(
        SignInCommand(username="alice", password="password-123"), ANONYMOUS_ACTOR
    )

    await cases.reset_password.handle(
        ResetPasswordCommand(user_id=user.id, password="brand-new-pass"), admin_actor
    )

    assert user.password_expired
    assert user.failed_attempts == 0
    old_user = await cases.current_user.handle(
        GetCurrentUserQuery(token=old.token), ANONYMOUS_ACTOR
    )
    assert old_user is None
    fresh = await cases.sign_in.handle(
        SignInCommand(username="alice", password="brand-new-pass"), ANONYMOUS_ACTOR
    )
    assert fresh.user is user


async def test_reset_password_validates_and_finds_the_user(
    cases: Cases, world: World, make_user: MakeUser, admin_actor: Actor
) -> None:
    """Weak passwords and unknown users are rejected."""
    user = make_user("alice")
    await world.users.add(user)
    with pytest.raises(InvalidPasswordError):
        await cases.reset_password.handle(
            ResetPasswordCommand(user_id=user.id, password="short"), admin_actor
        )
    with pytest.raises(UserNotFoundError):
        await cases.reset_password.handle(
            ResetPasswordCommand(user_id=uuid.uuid7(), password="brand-new-pass"),
            admin_actor,
        )


@time_machine.travel(NOW, tick=False)
async def test_change_password_ends_other_sessions_and_rotates_the_current(
    cases: Cases, world: World, make_user: MakeUser, actor_for: ActorFor
) -> None:
    """Every old session dies; a fresh token is issued; the flag is cleared."""
    user = make_user("alice")
    user.change_password(user.password_hash, expired=True)
    await world.users.add(user)
    here = await cases.sign_in.handle(
        SignInCommand(username="alice", password="password-123"), ANONYMOUS_ACTOR
    )
    elsewhere = await cases.sign_in.handle(
        SignInCommand(username="alice", password="password-123"), ANONYMOUS_ACTOR
    )

    result = await cases.change_password.handle(
        ChangePasswordCommand(
            current_password="password-123", new_password="a-much-better-one"
        ),
        actor_for(user),
    )

    assert not user.password_expired
    for old in (here, elsewhere):
        stale = await cases.current_user.handle(
            GetCurrentUserQuery(token=old.token), ANONYMOUS_ACTOR
        )
        assert stale is None
    current = await cases.current_user.handle(
        GetCurrentUserQuery(token=result.token), ANONYMOUS_ACTOR
    )
    assert current is not None
    assert current.user is user
    assert current.session_id == result.session_id
    again = await cases.sign_in.handle(
        SignInCommand(username="alice", password="a-much-better-one"), ANONYMOUS_ACTOR
    )
    assert again.user is user


async def test_change_password_rejects_wrong_current_and_weak_new_password(
    cases: Cases, world: World, make_user: MakeUser, actor_for: ActorFor
) -> None:
    """Nothing changes unless the current password is right and the new one valid."""
    user = make_user("alice")
    await world.users.add(user)
    actor = actor_for(user)
    with pytest.raises(CurrentPasswordIncorrectError):
        await cases.change_password.handle(
            ChangePasswordCommand(
                current_password="not-it-at-all", new_password="a-much-better-one"
            ),
            actor,
        )
    with pytest.raises(InvalidPasswordError):
        await cases.change_password.handle(
            ChangePasswordCommand(current_password="password-123", new_password="no"),
            actor,
        )
    assert not world.uow.committed


async def test_change_password_for_a_vanished_user_is_not_found(cases: Cases) -> None:
    """An actor whose account no longer exists gets UserNotFoundError."""
    with pytest.raises(UserNotFoundError):
        await cases.change_password.handle(
            ChangePasswordCommand(
                current_password="password-123", new_password="a-much-better-one"
            ),
            Actor(id=uuid.uuid7(), roles=frozenset({"member"})),
        )


@time_machine.travel(NOW, tick=False)
async def test_ending_sessions_logs_a_count_and_no_token(
    cases: Cases, world: World, make_user: MakeUser, admin_actor: Actor
) -> None:
    """Reset, change and disable report how many sessions went, never a token."""
    user = make_user("alice")
    await world.users.add(user)
    spare = make_user("carol")
    await world.users.add(spare)
    tokens = []
    for _ in range(2):
        signed_in = await cases.sign_in.handle(
            SignInCommand(username="alice", password="password-123"), ANONYMOUS_ACTOR
        )
        tokens.append(signed_in.token)

    with capture_logs() as logs:
        await cases.reset_password.handle(
            ResetPasswordCommand(user_id=user.id, password="brand-new-pass"),
            admin_actor,
        )
        await cases.update_user.handle(
            UpdateUserCommand(user_id=spare.id, disabled=True), admin_actor
        )

    ended = [log for log in logs if log["event"] == "sessions ended"]
    assert [(log["user_id"], log["count"]) for log in ended] == [(user.id, 2)]
    assert not any(token in str(logs) for token in tokens)
