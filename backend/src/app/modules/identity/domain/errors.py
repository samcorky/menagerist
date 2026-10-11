from app.shared_kernel.errors import (
    ConflictError,
    ForbiddenError,
    NotFoundError,
    TooManyRequestsError,
    UnauthenticatedError,
    ValidationError,
)


class InvalidUserError(ValidationError):
    """Raised when a username or display name is not acceptable."""


class InvalidPasswordError(ValidationError):
    """Raised when a password breaks the password rules."""


class UserNotFoundError(NotFoundError):
    """Raised when a requested user does not exist."""


class UsernameTakenError(ConflictError):
    """Raised when a username is already in use (ignoring case)."""


class SignInThrottledError(TooManyRequestsError):
    """Raised when sign-in is refused because of too many recent failures."""


class InvalidCredentialsError(UnauthenticatedError):
    """Raised when sign-in fails; the same for any cause, so none is revealed."""


class SessionRequiredError(UnauthenticatedError):
    """Raised when a request needs a signed-in session and has none."""

    problem_type = "unauthenticated"


class SetupAlreadyDoneError(ConflictError):
    """Raised when first-run setup is attempted after an account exists."""


class LastAdministratorError(ConflictError):
    """Raised when a change would leave no enabled administrator."""


class CurrentPasswordIncorrectError(ValidationError):
    """Raised when the current password given for a change is wrong."""


class SetupRequiredError(UnauthenticatedError):
    """Raised when no account exists yet, so first-run setup must happen first."""

    problem_type = "setup_required"


class PasswordExpiredError(ForbiddenError):
    """Raised when the account's password has expired and must be replaced first."""

    problem_type = "password_expired"


class AccountDisabledError(ForbiddenError):
    """Raised when correct credentials belong to a disabled account."""

    problem_type = "account_disabled"

    def __init__(self) -> None:
        super().__init__("This account has been disabled. Ask an administrator.")


class PasswordUnchangedError(ValidationError):
    """Raised when a new password is the same as the current one."""
