"""Settings errors translated by the shared exception handlers."""

from app.shared_kernel.errors import ConflictError, NotFoundError, ValidationError


class UnknownSettingError(NotFoundError):
    """No tunable setting exists with the requested key."""

    def __init__(self, key: str) -> None:
        super().__init__(f"Unknown setting: {key}")
        self.key = key


class SettingLockedError(ConflictError):
    """The deployment pins the value, so it cannot be changed here."""

    def __init__(self, key: str, env_name: str) -> None:
        super().__init__(f"{key} is set by your deployment ({env_name})")
        self.key = key
        self.env_name = env_name


class InvalidSettingValueError(ValidationError):
    """A value does not satisfy the setting's type or constraints."""

    def __init__(self, key: str, reason: str) -> None:
        super().__init__(f"Invalid value for {key}: {reason}")
        self.key = key
