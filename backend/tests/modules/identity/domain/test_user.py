from datetime import UTC, datetime, timedelta

import pytest

from app.modules.identity.domain.errors import InvalidPasswordError, InvalidUserError
from app.modules.identity.domain.user import Role, User, validate_password

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
    """A new user is a lower-cased, enabled member who has never signed in."""
    user = _user("Alice.B-1_x")
    assert user.username == "alice.b-1_x"
    assert user.role is Role.MEMBER
    assert (user.disabled, user.password_expired) == (False, False)
    assert user.last_login_at is None
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


def test_change_password_sets_hash_and_flag() -> None:
    """Changing the password resets the must-change flag unless asked otherwise."""
    user = _user(password_expired=True)
    user.change_password("fake$new")
    assert user.password_hash == "fake$new"
    assert user.password_expired is False
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


def test_record_sign_in_stamps_the_time() -> None:
    """A recorded sign-in sets `last_login_at` and touches the account."""
    user = _user()
    later = NOW + timedelta(hours=1)

    user.record_sign_in(later)

    assert user.last_login_at == later
    assert user.updated_at > NOW


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
