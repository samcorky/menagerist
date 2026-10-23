import uuid
from datetime import datetime
from typing import TYPE_CHECKING, Any

from pydantic import BaseModel, ConfigDict, Field

from app.entrypoints.api.shared.permissions import Permission
from app.modules.identity.application.change_password import ChangePasswordCommand
from app.modules.identity.application.create_api_token import (
    CreateApiTokenCommand,
    CreatedApiToken,
)
from app.modules.identity.application.create_user import CreateUserCommand
from app.modules.identity.application.reset_password import ResetPasswordCommand
from app.modules.identity.application.rotate_api_token import RotateApiTokenCommand
from app.modules.identity.application.set_own_display_name import (
    SetOwnDisplayNameCommand,
)
from app.modules.identity.application.setup_first_admin import SetupFirstAdminCommand
from app.modules.identity.application.sign_in import SignInCommand
from app.modules.identity.application.update_user import UpdateUserCommand
from app.modules.identity.domain.api_token import MAX_TOKEN_NAME_LENGTH
from app.modules.identity.domain.user import (
    MAX_DISPLAY_NAME_LENGTH,
    MAX_USERNAME_LENGTH,
    Role,
)
from app.platform.request_model import RequestModel

if TYPE_CHECKING:
    from app.modules.identity.application.client_device import ClientDevice
    from app.modules.identity.application.list_own_sessions import OwnSession
    from app.modules.identity.application.session_listing import SessionListing
    from app.modules.identity.application.setup_first_admin import SetupFirstAdminResult
    from app.modules.identity.application.user_listing import UserListing
    from app.modules.identity.domain.api_token import ApiToken
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


_SESSION_EXAMPLE: dict[str, Any] = {
    "id": "01978c3e-2b8b-7c3a-9c2e-3a2f6b9d4e50",
    "user_agent": "Mozilla/5.0 (X11; Linux x86_64) Firefox/130.0",
    "client_platform": "Linux",
    "client_mobile": False,
    "client_ip": "192.0.2.1",
    "created_at": "2026-10-10T12:00:00.000000Z",
    "last_seen_at": "2026-10-10T12:30:00.000000Z",
    "expires_at": "2026-10-11T12:00:00.000000Z",
    "current": True,
}

_ADMIN_SESSION_EXAMPLE: dict[str, Any] = {
    "id": "01978c3e-2b8b-7c3a-9c2e-3a2f6b9d4e50",
    "user_id": "01978c3e-2b8b-7c3a-9c2e-3a2f6b9d4e51",
    "username": "alice",
    "display_name": "Alice Example",
    "user_agent": "Mozilla/5.0 (X11; Linux x86_64) Firefox/130.0",
    "client_platform": "Linux",
    "client_mobile": False,
    "client_ip": "192.0.2.1",
    "created_at": "2026-10-10T12:00:00.000000Z",
    "last_seen_at": "2026-10-10T12:30:00.000000Z",
    "expires_at": "2026-10-11T12:00:00.000000Z",
}


class SessionResponse(BaseModel):
    """An active session / device belonging to the current user."""

    model_config = ConfigDict(json_schema_extra={"examples": [_SESSION_EXAMPLE]})

    id: uuid.UUID
    user_agent: str | None = None
    client_platform: str | None = None
    client_mobile: bool | None = None
    client_ip: str | None = None
    created_at: datetime
    last_seen_at: datetime
    expires_at: datetime
    current: bool

    @classmethod
    def from_own_session(cls, own: OwnSession) -> SessionResponse:
        """Build a response from an `OwnSession`."""
        session = own.session
        return cls(
            id=session.id,
            user_agent=session.user_agent,
            client_platform=session.client_platform,
            client_mobile=session.client_mobile,
            client_ip=session.client_ip,
            created_at=session.created_at,
            last_seen_at=session.last_seen_at,
            expires_at=session.expires_at,
            current=own.current,
        )


class AdminSessionResponse(BaseModel):
    """An active session with its owner's identity details, for administrators."""

    model_config = ConfigDict(json_schema_extra={"examples": [_ADMIN_SESSION_EXAMPLE]})

    id: uuid.UUID
    user_id: uuid.UUID
    username: str
    display_name: str | None = None
    user_agent: str | None = None
    client_platform: str | None = None
    client_mobile: bool | None = None
    client_ip: str | None = None
    created_at: datetime
    last_seen_at: datetime
    expires_at: datetime

    @classmethod
    def from_listing(cls, listing: SessionListing) -> AdminSessionResponse:
        """Build a response from a `SessionListing`."""
        session = listing.session
        return cls(
            id=session.id,
            user_id=session.user_id,
            username=listing.username,
            display_name=listing.display_name,
            user_agent=session.user_agent,
            client_platform=session.client_platform,
            client_mobile=session.client_mobile,
            client_ip=session.client_ip,
            created_at=session.created_at,
            last_seen_at=session.last_seen_at,
            expires_at=session.expires_at,
        )


class RevokedSessionsResponse(BaseModel):
    """The number of other sessions that were ended."""

    model_config = ConfigDict(json_schema_extra={"examples": [{"ended": 2}]})

    ended: int


_TOKEN_EXAMPLE: dict[str, Any] = {
    "id": "01978c3e-2b8b-7c3a-9c2e-3a2f6b9d4e60",
    "name": "Backup script",
    "grants": ["graph:item:read"],
    "created_at": "2026-10-10T12:00:00.000000Z",
    "expires_at": "2027-01-08T12:00:00.000000Z",
    "last_used_at": None,
}
_MAX_TOKEN_GRANTS = 64


class CreateApiTokenRequest(RequestModel):
    """Request body for creating a personal access token."""

    model_config = ConfigDict(
        json_schema_extra={
            "examples": [
                {
                    "name": "Backup script",
                    "password": "your current passphrase",
                    "grants": ["graph:item:read"],
                    "expires_in_days": 90,
                }
            ]
        }
    )

    # Loose input guard only; the domain trims and applies the real name length.
    name: str = Field(max_length=MAX_TOKEN_NAME_LENGTH * 4)
    password: str = Field(max_length=_MAX_PASSWORD_INPUT)
    grants: list[str] = Field(
        max_length=_MAX_TOKEN_GRANTS,
        description="Permissions the token holds; see the grants endpoint.",
    )
    expires_in_days: int | None = Field(
        default=None,
        description="Lifetime in days; the server default applies when omitted.",
    )

    def to_command(self, client_ip: str | None = None) -> CreateApiTokenCommand:
        """Convert this request into a `CreateApiTokenCommand`."""
        return CreateApiTokenCommand(
            name=self.name,
            password=self.password,
            grants=frozenset(self.grants),
            expires_in_days=self.expires_in_days,
            client_ip=client_ip,
        )


class RotateApiTokenRequest(RequestModel):
    """Request body for replacing a token with a fresh secret."""

    model_config = ConfigDict(
        json_schema_extra={
            "examples": [{"password": "your current passphrase", "expires_in_days": 90}]
        }
    )

    password: str = Field(max_length=_MAX_PASSWORD_INPUT)
    expires_in_days: int | None = Field(
        default=None,
        description="Lifetime in days; the server default applies when omitted.",
    )

    def to_command(
        self, token_id: uuid.UUID, client_ip: str | None = None
    ) -> RotateApiTokenCommand:
        """Convert this request into a `RotateApiTokenCommand`."""
        return RotateApiTokenCommand(
            token_id=token_id,
            password=self.password,
            expires_in_days=self.expires_in_days,
            client_ip=client_ip,
        )


class ApiTokenResponse(BaseModel):
    """A personal access token's details; never includes its secret."""

    model_config = ConfigDict(json_schema_extra={"examples": [_TOKEN_EXAMPLE]})

    id: uuid.UUID
    name: str
    grants: list[str]
    created_at: datetime
    expires_at: datetime
    last_used_at: datetime | None = Field(
        default=None, description="When the token was last used; null if never."
    )

    @classmethod
    def from_domain(cls, token: ApiToken) -> ApiTokenResponse:
        """Build a response from a token."""
        return cls(
            id=token.id,
            name=token.name,
            grants=sorted(token.grants),
            created_at=token.created_at,
            expires_at=token.expires_at,
            last_used_at=token.last_used_at,
        )


class CreatedApiTokenResponse(ApiTokenResponse):
    """A new token, with its plaintext value, which is shown only once."""

    model_config = ConfigDict(
        json_schema_extra={
            "examples": [{**_TOKEN_EXAMPLE, "token": "mnst_<id>_<secret>"}]
        }
    )

    token: str = Field(description="The token to send as a bearer credential.")

    @classmethod
    def from_created(cls, created: CreatedApiToken) -> CreatedApiTokenResponse:
        """Build a response from a freshly issued token."""
        base = ApiTokenResponse.from_domain(created.token)
        return cls(**base.model_dump(), token=created.plaintext)


class GrantablePermissionsResponse(BaseModel):
    """The permissions the signed-in account may give a token."""

    model_config = ConfigDict(
        json_schema_extra={"examples": [{"permissions": ["graph:item:read"]}]}
    )

    permissions: list[Permission]
