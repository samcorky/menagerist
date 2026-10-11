from datetime import UTC, datetime, timedelta

import pytest

from app.modules.identity.domain.errors import InvalidPasswordError, InvalidUserError
from app.modules.identity.domain.user import (
    LOCKOUT_ATTEMPTS,
    LOCKOUT_WINDOW,
    Role,
    User,
    validate_password,
)

NOW = datetime(2026, 10, 10, 12, 0, tzinfo=UTC)


def _user(
    username: str = "Alice",
    *,
    role: Role = Role.MEMBER,
    password_expired: bool = False,
) -> User:
    return User.create(
        username=username,
        display_name="Alice A",
        password_hash="fake$x",
        role=role,
        password_expired=password_expired,
        now=NOW,
    )


def test_create_normalises_username_and_sets_defaults() -> None:
    """A new user is a lower-cased, enabled member with no failures."""
    user = _user("Alice.B-1_x")
    assert user.username == "alice.b-1_x"
    assert user.role is Role.MEMBER
    assert (user.disabled, user.password_expired, user.failed_attempts) == (
        False,
        False,
        0,
    )
    assert user.locked_until is None
    assert user.created_at == user.updated_at == NOW


@pytest.mark.parametrize("username", ["ab", "a" * 65, "has space", "bad!", "ün", ""])
def test_create_rejects_bad_usernames(username: str) -> None:
    """Usernames are 3 to 64 characters from `[A-Za-z0-9._-]`."""
    with pytest.raises(InvalidUserError):
        _user(username)


def test_create_accepts_boundary_usernames() -> None:
    """3 and 64 characters are both fine."""
    assert _user("abc").username == "abc"
    assert _user("a" * 64).username == "a" * 64


@pytest.mark.parametrize("display_name", ["", "   ", "x" * 121])
def test_create_rejects_bad_display_names(display_name: str) -> None:
    """Display names are 1 to 120 characters once trimmed."""
    with pytest.raises(InvalidUserError):
        User.create(
            username="alice", display_name=display_name, password_hash="h", now=NOW
        )


def test_create_trims_display_name() -> None:
    """Surrounding whitespace is dropped."""
    user = User.create(
        username="alice", display_name="  Al  ", password_hash="h", now=NOW
    )
    assert user.display_name == "Al"


def test_create_admin_requiring_password_change() -> None:
    """Role and the change-password flag can be set on creation."""
    user = _user(role=Role.ADMIN, password_expired=True)
    assert user.role is Role.ADMIN
    assert user.password_expired is True


def test_validate_password_rules() -> None:
    """Passwords are 10 to 128 characters and differ from the username."""
    validate_password("a" * 10, "alice")
    validate_password("a" * 128, "alice")
    for bad in ("a" * 9, "a" * 129):
        with pytest.raises(InvalidPasswordError):
            validate_password(bad, "alice")
    with pytest.raises(InvalidPasswordError):
        validate_password("Alice12345", "alice12345")


def test_change_password_clears_flag_and_failures() -> None:
    """Changing the password resets the must-change flag and lockout state."""
    user = _user(password_expired=True)
    user.record_failure(NOW)
    user.change_password("fake$new")
    assert user.password_hash == "fake$new"
    assert user.password_expired is False
    assert user.failed_attempts == 0
    user.change_password("fake$newer", expired=True)
    assert user.password_expired is True


def test_rehash_keeps_flags() -> None:
    """Rewriting the hash does not touch the must-change flag."""
    user = _user(password_expired=True)
    user.rehash("scrypt$new")
    assert user.password_hash == "scrypt$new"
    assert user.password_expired is True


def test_disable_and_enable() -> None:
    """Disabling and enabling flip the flag."""
    user = _user()
    user.disable()
    assert user.disabled is True
    user.enable()
    assert user.disabled is False


def test_lockout_after_five_failures_within_window() -> None:
    """The fifth failure inside 15 minutes locks until the window ends."""
    user = _user()
    for i in range(LOCKOUT_ATTEMPTS - 1):
        user.record_failure(NOW + timedelta(minutes=i))
        assert user.is_locked(NOW + timedelta(minutes=i)) is False
    user.record_failure(NOW + timedelta(minutes=4))
    assert user.failed_attempts == LOCKOUT_ATTEMPTS
    assert user.locked_until == NOW + LOCKOUT_WINDOW
    assert user.is_locked(NOW + timedelta(minutes=5)) is True
    assert user.is_locked(NOW + LOCKOUT_WINDOW) is False


def test_failures_outside_window_restart_the_count() -> None:
    """A failure after the window expires starts a new count."""
    user = _user()
    for _ in range(LOCKOUT_ATTEMPTS - 1):
        user.record_failure(NOW)
    user.record_failure(NOW + LOCKOUT_WINDOW)
    assert user.failed_attempts == 1
    assert user.locked_until is None


def test_success_resets_failures() -> None:
    """A successful sign-in clears the count and any lock."""
    user = _user()
    for _ in range(LOCKOUT_ATTEMPTS):
        user.record_failure(NOW)
    user.record_success()
    assert (user.failed_attempts, user.locked_until) == (0, None)
    assert user.is_locked(NOW) is False


def test_rename_cleans_and_validates_the_display_name() -> None:
    """Renaming trims the name and rejects an empty one."""
    user = User.create(
        username="alice", display_name="Alice", password_hash="h", now=NOW
    )

    user.rename("  Alice B  ")

    assert user.display_name == "Alice B"
    with pytest.raises(InvalidUserError):
        user.rename("   ")
    assert user.display_name == "Alice B"


def test_set_role_changes_the_role() -> None:
    """The role can be changed."""
    user = User.create(
        username="alice", display_name="Alice", password_hash="h", now=NOW
    )

    user.set_role(Role.ADMIN)

    assert user.role is Role.ADMIN
