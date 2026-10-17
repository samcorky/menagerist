import uuid
from datetime import datetime
from typing import TYPE_CHECKING, Any

from pydantic import BaseModel, ConfigDict, Field

from app.modules.identity.application.change_password import ChangePasswordCommand
from app.modules.identity.application.create_user import CreateUserCommand
from app.modules.identity.application.reset_password import ResetPasswordCommand
from app.modules.identity.application.set_own_display_name import (
    SetOwnDisplayNameCommand,
)
from app.modules.identity.application.setup_first_admin import SetupFirstAdminCommand
from app.modules.identity.application.sign_in import SignInCommand
from app.modules.identity.application.update_user import UpdateUserCommand
from app.modules.identity.domain.user import (
    MAX_DISPLAY_NAME_LENGTH,
    MAX_USERNAME_LENGTH,
    Role,
)
from app.platform.request_model import RequestModel

if TYPE_CHECKING:
    from app.modules.identity.application.client_device import ClientDevice
    from app.modules.identity.application.setup_first_admin import SetupFirstAdminResult
    from app.modules.identity.application.user_listing import UserListing
    from app.modules.identity.domain.user import User

# Generous bounds only stop absurd bodies; the domain applies the real password rules.
_MAX_PASSWORD_INPUT = 1024

_USER_EXAMPLE: dict[str, Any] = {
    "id": "01978c3e-2b8b-7c3a-9c2e-3a2f6b9d4e50",
    "username": "alice",
    "display_name": "Alice Example",
    "role": "member",
    "password_expired": False,
    "disabled": False,
    "last_login_at": "2026-10-11T08:30:00.000000Z",
    "locked_until": None,
    "created_at": "2026-10-10T12:00:00.000000Z",
    "updated_at": "2026-10-10T12:00:00.000000Z",
}


class SetupRequest(RequestModel):
    """Request body for creating the first administrator."""

    model_config = ConfigDict(
        json_schema_extra={
            "examples": [
                {
                    "username": "admin",
                    "display_name": "Administrator",
                    "password": "a long passphrase",
                }
            ]
        }
    )

    username: str = Field(max_length=MAX_USERNAME_LENGTH)
    display_name: str = Field(max_length=MAX_DISPLAY_NAME_LENGTH)
    password: str = Field(max_length=_MAX_PASSWORD_INPUT)

    def to_command(
        self,
        client_ip: str | None = None,
        device: ClientDevice | None = None,
    ) -> SetupFirstAdminCommand:
        """Convert this request into a `SetupFirstAdminCommand`."""
        return SetupFirstAdminCommand(
            username=self.username,
            display_name=self.display_name,
            password=self.password,
            client_ip=client_ip,
            device=device,
        )


class LoginRequest(RequestModel):
    """Request body for signing in."""

    model_config = ConfigDict(
        json_schema_extra={
            "examples": [{"username": "alice", "password": "a long passphrase"}]
        }
    )

    username: str = Field(max_length=MAX_USERNAME_LENGTH)
    password: str = Field(max_length=_MAX_PASSWORD_INPUT)

    def to_command(
        self,
        client_ip: str | None = None,
        device: ClientDevice | None = None,
    ) -> SignInCommand:
        """Convert this request into a `SignInCommand`."""
        return SignInCommand(
            username=self.username,
            password=self.password,
            client_ip=client_ip,
            device=device,
        )


class ChangePasswordRequest(RequestModel):
    """Request body for changing your own password."""

    model_config = ConfigDict(
        json_schema_extra={
            "examples": [
                {
                    "current_password": "the old passphrase",
                    "new_password": "a new, longer passphrase",
                }
            ]
        }
    )

    current_password: str = Field(max_length=_MAX_PASSWORD_INPUT)
    new_password: str = Field(max_length=_MAX_PASSWORD_INPUT)

    def to_command(
        self,
        client_ip: str | None = None,
        device: ClientDevice | None = None,
    ) -> ChangePasswordCommand:
        """Convert this request into a `ChangePasswordCommand`."""
        return ChangePasswordCommand(
            current_password=self.current_password,
            new_password=self.new_password,
            client_ip=client_ip,
            device=device,
        )


class UpdateMeRequest(RequestModel):
    """Request body for changing your own display name."""

    model_config = ConfigDict(
        json_schema_extra={"examples": [{"display_name": "Alice Example"}]}
    )

    display_name: str = Field(max_length=MAX_DISPLAY_NAME_LENGTH)

    def to_command(self) -> SetOwnDisplayNameCommand:
        """Convert this request into a `SetOwnDisplayNameCommand`."""
        return SetOwnDisplayNameCommand(display_name=self.display_name)


class CreateUserRequest(RequestModel):
    """Request body for creating an account with an initial password."""

    model_config = ConfigDict(
        json_schema_extra={
            "examples": [
                {
                    "username": "alice",
                    "display_name": "Alice Example",
                    "password": "an initial passphrase",
                    "role": "member",
                }
            ]
        }
    )

    username: str = Field(max_length=MAX_USERNAME_LENGTH)
    display_name: str = Field(max_length=MAX_DISPLAY_NAME_LENGTH)
    password: str = Field(max_length=_MAX_PASSWORD_INPUT)
    role: Role = Role.MEMBER

    def to_command(self) -> CreateUserCommand:
        """Convert this request into a `CreateUserCommand`."""
        return CreateUserCommand(
            username=self.username,
            display_name=self.display_name,
            password=self.password,
            role=self.role,
        )


class UpdateUserRequest(RequestModel):
    """Request body for changing an account; omitted fields are left as they are."""

    model_config = ConfigDict(
        json_schema_extra={
            "examples": [
                {"display_name": "Alice B", "role": "admin", "disabled": False}
            ]
        }
    )

    display_name: str | None = Field(default=None, max_length=MAX_DISPLAY_NAME_LENGTH)
    role: Role | None = None
    disabled: bool | None = None

    def to_command(self, user_id: uuid.UUID) -> UpdateUserCommand:
        """Convert this request into an `UpdateUserCommand`."""
        return UpdateUserCommand(
            user_id=user_id,
            display_name=self.display_name,
            role=self.role,
            disabled=self.disabled,
        )


class ResetPasswordRequest(RequestModel):
    """Request body for giving an account a new initial password."""

    model_config = ConfigDict(
        json_schema_extra={"examples": [{"password": "a new initial passphrase"}]}
    )

    password: str = Field(max_length=_MAX_PASSWORD_INPUT)

    def to_command(self, user_id: uuid.UUID) -> ResetPasswordCommand:
        """Convert this request into a `ResetPasswordCommand`."""
        return ResetPasswordCommand(user_id=user_id, password=self.password)


class AuthStatusResponse(BaseModel):
    """Whether first-run setup is still to be done."""

    model_config = ConfigDict(
        json_schema_extra={"examples": [{"setup_required": True}]}
    )

    setup_required: bool


class UserResponse(BaseModel):
    """An account as returned by the API; never includes credentials."""

    model_config = ConfigDict(json_schema_extra={"examples": [_USER_EXAMPLE]})

    id: uuid.UUID
    username: str
    display_name: str
    role: Role
    password_expired: bool
    disabled: bool
    last_login_at: datetime | None = Field(
        default=None, description="When the account last signed in; null if never."
    )
    locked_until: datetime | None = Field(
        default=None,
        description=(
            "When a sign-in lockout on this username ends; null when not locked."
            + " Only filled in by the administrator user list and update."
        ),
    )
    created_at: datetime
    updated_at: datetime

    @classmethod
    def from_listing(cls, listing: UserListing) -> UserResponse:
        """Build a response from a user and its lock state."""
        return cls.from_domain(listing.user, locked_until=listing.locked_until)

    @classmethod
    def from_domain(
        cls, user: User, *, locked_until: datetime | None = None
    ) -> UserResponse:
        """Build a response from a user."""
        return cls(
            id=user.id,
            username=user.username,
            display_name=user.display_name,
            role=user.role,
            password_expired=user.password_expired,
            disabled=user.disabled,
            last_login_at=user.last_login_at,
            locked_until=locked_until,
            created_at=user.created_at,
            updated_at=user.updated_at,
        )


class SetupResponse(BaseModel):
    """The new administrator and what they took ownership of."""

    model_config = ConfigDict(
        json_schema_extra={
            "examples": [{"user": _USER_EXAMPLE, "claimed": {"collections": 2}}]
        }
    )

    user: UserResponse
    claimed: dict[str, int] = Field(
        description="How many existing items of each kind became theirs."
    )

    @classmethod
    def from_result(cls, result: SetupFirstAdminResult) -> SetupResponse:
        """Build a response from the setup outcome."""
        return cls(
            user=UserResponse.from_domain(result.user),
            claimed=dict(result.claim.counts),
        )
