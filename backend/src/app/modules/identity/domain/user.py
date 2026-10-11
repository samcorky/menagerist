import re
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import StrEnum

from app.modules.identity.domain.errors import InvalidPasswordError, InvalidUserError
from app.shared_kernel.mixins import Identifiable, Timestamped

MIN_USERNAME_LENGTH = 3
MAX_USERNAME_LENGTH = 64
MAX_DISPLAY_NAME_LENGTH = 120
MIN_PASSWORD_LENGTH = 10
MAX_PASSWORD_LENGTH = 128
LOCKOUT_ATTEMPTS = 5
LOCKOUT_WINDOW = timedelta(minutes=15)

_USERNAME = re.compile(r"[A-Za-z0-9._-]+")


class Role(StrEnum):
    """What an account may do."""

    ADMIN = "admin"
    MEMBER = "member"


def validate_password(password: str, username: str) -> None:
    """Check `password` against the password rules.

    Raises:
        InvalidPasswordError: If it is not 10 to 128 characters, or equals the
            username (ignoring case).
    """
    if not MIN_PASSWORD_LENGTH <= len(password) <= MAX_PASSWORD_LENGTH:
        raise InvalidPasswordError(
            f"A password must be {MIN_PASSWORD_LENGTH} to {MAX_PASSWORD_LENGTH}"
            + " characters."
        )
    if password.casefold() == username.casefold():
        raise InvalidPasswordError("A password must not be the same as the username.")


def _clean_username(username: str) -> str:
    if (
        not MIN_USERNAME_LENGTH <= len(username) <= MAX_USERNAME_LENGTH
        or _USERNAME.fullmatch(username) is None
    ):
        raise InvalidUserError(
            f"A username must be {MIN_USERNAME_LENGTH} to {MAX_USERNAME_LENGTH}"
            + " characters: letters, digits, dots, underscores and hyphens."
        )
    return username.lower()


def _clean_display_name(display_name: str) -> str:
    cleaned = display_name.strip()
    if not 1 <= len(cleaned) <= MAX_DISPLAY_NAME_LENGTH:
        raise InvalidUserError(
            f"A display name must be 1 to {MAX_DISPLAY_NAME_LENGTH} characters."
        )
    return cleaned


@dataclass(kw_only=True, eq=False)
class User(Identifiable, Timestamped):
    """A local account; the username is stored lower-cased (unique ignoring case)."""

    username: str
    display_name: str
    password_hash: str = field(repr=False)
    role: Role = Role.MEMBER
    password_expired: bool = False
    disabled: bool = False
    failed_attempts: int = 0
    failure_window_started_at: datetime | None = None
    locked_until: datetime | None = None

    @classmethod
    def create(
        cls,
        *,
        username: str,
        display_name: str,
        password_hash: str,
        now: datetime,
        role: Role = Role.MEMBER,
        password_expired: bool = False,
    ) -> User:
        """Create an enabled account.

        Raises:
            InvalidUserError: If the username or display name breaks the rules.
        """
        return cls(
            id=uuid.uuid7(),
            username=_clean_username(username),
            display_name=_clean_display_name(display_name),
            password_hash=password_hash,
            role=role,
            password_expired=password_expired,
            created_at=now,
            updated_at=now,
        )

    def change_password(self, password_hash: str, *, expired: bool = False) -> None:
        """Replace the password hash and clear any sign-in failures."""
        self.password_hash = password_hash
        self.password_expired = expired
        self.record_success()

    def rename(self, display_name: str) -> None:
        """Change the display name.

        Raises:
            InvalidUserError: If the display name breaks the rules.
        """
        self.display_name = _clean_display_name(display_name)
        self.touch()

    def set_role(self, role: Role) -> None:
        """Change what this account may do."""
        self.role = role
        self.touch()

    def rehash(self, password_hash: str) -> None:
        """Rewrite the stored hash of the same password (scheme or cost upgrade)."""
        self.password_hash = password_hash
        self.touch()

    def disable(self) -> None:
        """Stop this account from signing in."""
        self.disabled = True
        self.touch()

    def enable(self) -> None:
        """Let this account sign in again."""
        self.disabled = False
        self.touch()

    def is_locked(self, now: datetime) -> bool:
        """Whether sign-in is refused at `now` after too many failures."""
        return self.locked_until is not None and now < self.locked_until

    def record_failure(self, now: datetime) -> None:
        """Count a failed sign-in; the fifth in a fixed 15-minute window locks."""
        started = self.failure_window_started_at
        if started is None or now - started >= LOCKOUT_WINDOW:
            started = now
            self.failure_window_started_at = now
            self.failed_attempts = 0
            self.locked_until = None
        self.failed_attempts += 1
        if self.failed_attempts >= LOCKOUT_ATTEMPTS:
            self.locked_until = started + LOCKOUT_WINDOW
        self.touch()

    def record_success(self) -> None:
        """Clear the failure count and any lock."""
        self.failed_attempts = 0
        self.failure_window_started_at = None
        self.locked_until = None
        self.touch()
