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
from app.modules.identity.domain.device import MAX_DEVICE_NAME_LENGTH
from app.modules.identity.domain.session import DisplayMode
from app.modules.identity.domain.user import (
    MAX_DISPLAY_NAME_LENGTH,
    MAX_USERNAME_LENGTH,
    Role,
)
from app.platform.request_model import RequestModel

if TYPE_CHECKING:
    from app.modules.identity.application.client_device import ClientDevice
    from app.modules.identity.application.list_own_devices import OwnDevice
    from app.modules.identity.application.list_own_sessions import OwnSession
    from app.modules.identity.application.session_listing import SessionListing
    from app.modules.identity.application.setup_first_admin import SetupFirstAdminResult
    from app.modules.identity.application.user_listing import UserListing
    from app.modules.identity.domain.api_token import ApiToken
    from app.modules.identity.domain.device import Device
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

    username: str = Field(
        description="The administrator's sign-in name.", max_length=MAX_USERNAME_LENGTH
    )
    display_name: str = Field(
        description="The name shown to people.", max_length=MAX_DISPLAY_NAME_LENGTH
    )
    password: str = Field(
        description="The administrator's passphrase.", max_length=_MAX_PASSWORD_INPUT
    )

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

    username: str = Field(
        description="The account's sign-in name.", max_length=MAX_USERNAME_LENGTH
    )
    password: str = Field(
        description="The account's passphrase.", max_length=_MAX_PASSWORD_INPUT
    )

    def to_command(
        self,
        client_ip: str | None = None,
        device: ClientDevice | None = None,
        device_token: str | None = None,
    ) -> SignInCommand:
        """Convert this request into a `SignInCommand`."""
        return SignInCommand(
            username=self.username,
            password=self.password,
            client_ip=client_ip,
            device=device,
            device_token=device_token,
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

    current_password: str = Field(
        description="Your passphrase now.", max_length=_MAX_PASSWORD_INPUT
    )
    new_password: str = Field(
        description="The passphrase to change to.", max_length=_MAX_PASSWORD_INPUT
    )

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

    display_name: str = Field(
        description="The name shown to people.", max_length=MAX_DISPLAY_NAME_LENGTH
    )

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

    username: str = Field(
        description="The sign-in name.", max_length=MAX_USERNAME_LENGTH
    )
    display_name: str = Field(
        description="The name shown to people.", max_length=MAX_DISPLAY_NAME_LENGTH
    )
    password: str = Field(
        description="An initial passphrase, to change at first sign-in.",
        max_length=_MAX_PASSWORD_INPUT,
    )
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

    display_name: str | None = Field(
        description="The name shown to people.",
        default=None,
        max_length=MAX_DISPLAY_NAME_LENGTH,
    )
    role: Role | None = Field(default=None, description="The account's role.")
    disabled: bool | None = Field(
        default=None, description="Whether the account is blocked from signing in."
    )

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

    password: str = Field(
        description="A new initial passphrase, to change at next sign-in.",
        max_length=_MAX_PASSWORD_INPUT,
    )

    def to_command(self, user_id: uuid.UUID) -> ResetPasswordCommand:
        """Convert this request into a `ResetPasswordCommand`."""
        return ResetPasswordCommand(user_id=user_id, password=self.password)


class AuthStatusResponse(BaseModel):
    """Whether first-run setup is still to be done."""

    model_config = ConfigDict(
        json_schema_extra={"examples": [{"setup_required": True}]}
    )

    setup_required: bool = Field(
        description="Whether the first administrator still has to be created."
    )


class UserResponse(BaseModel):
    """An account as returned by the API; never includes credentials."""

    model_config = ConfigDict(json_schema_extra={"examples": [_USER_EXAMPLE]})

    id: uuid.UUID = Field(description="The account's id.")
    username: str = Field(description="The sign-in name.")
    display_name: str = Field(description="The name shown to people.")
    role: Role
    password_expired: bool = Field(
        description="Whether the passphrase must be changed at the next sign-in."
    )
    disabled: bool = Field(
        description="Whether the account is blocked from signing in."
    )
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
    created_at: datetime = Field(description="When the account was created.")
    updated_at: datetime = Field(description="When the account last changed.")

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
    "device_id": "01978c3e-2b8b-7c3a-9c2e-3a2f6b9d4e52",
    "display_mode": "standalone",
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
    "device_id": "01978c3e-2b8b-7c3a-9c2e-3a2f6b9d4e52",
    "device_name": "Alice's laptop",
    "display_mode": "browser",
}

DEVICE_EXAMPLE: dict[str, Any] = {
    "id": "01978c3e-2b8b-7c3a-9c2e-3a2f6b9d4e52",
    "name": "Alice's laptop",
    "user_agent": "Mozilla/5.0 (X11; Linux x86_64) Firefox/130.0",
    "platform": "Linux",
    "mobile": False,
    "first_seen_at": "2026-09-01T08:00:00.000000Z",
    "last_seen_at": "2026-10-10T12:30:00.000000Z",
    "current": True,
    "sessions": [_SESSION_EXAMPLE],
}


class SessionResponse(BaseModel):
    """An active session / device belonging to the current user."""

    model_config = ConfigDict(json_schema_extra={"examples": [_SESSION_EXAMPLE]})

    id: uuid.UUID = Field(description="The session's id.")
    user_agent: str | None = Field(
        default=None, description="The browser's user agent when it signed in."
    )
    client_platform: str | None = Field(
        default=None, description="The platform the browser reported, if any."
    )
    client_mobile: bool | None = Field(
        default=None, description="Whether the browser reported a mobile device."
    )
    client_ip: str | None = Field(
        default=None, description="The address the session signed in from."
    )
    created_at: datetime = Field(description="When the session started.")
    last_seen_at: datetime = Field(description="The session's latest request.")
    expires_at: datetime = Field(description="When the session ends unless used.")
    device_id: uuid.UUID | None = Field(
        default=None,
        description="The remembered browser this session was started in, if any.",
    )
    display_mode: DisplayMode | None = Field(
        default=None,
        description=(
            "Whether the session was started in a browser tab or the installed app,"
            + " as the app reported it; absent for older sessions."
        ),
    )
    current: bool = Field(description="Whether this is the session making the request.")

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
            device_id=session.device_id,
            display_mode=session.display_mode,
            current=own.current,
        )


class OwnDeviceResponse(BaseModel):
    """A browser the current user is signed in on, with its active sessions.

    `id` is null for a session started before browsers were remembered; it is
    then the only session listed, and is ended through `DELETE /me/sessions/{id}`.
    """

    model_config = ConfigDict(json_schema_extra={"examples": [DEVICE_EXAMPLE]})

    id: uuid.UUID | None = Field(
        default=None,
        description="The device's id; null for a session from before devices.",
    )
    name: str | None = Field(
        default=None,
        description="The name its owner gave the browser; null when it has none.",
    )
    user_agent: str | None = Field(
        default=None, description="The browser's user agent at its last sign-in."
    )
    platform: str | None = Field(
        default=None, description="The platform the browser reported, if any."
    )
    mobile: bool | None = Field(
        default=None, description="Whether the browser reported a mobile device."
    )
    first_seen_at: datetime = Field(
        description="When this browser was first remembered for the account."
    )
    last_seen_at: datetime = Field(
        description="The latest activity of the browser or any of its sessions."
    )
    current: bool = Field(description="Whether this is the browser making the request.")
    sessions: list[SessionResponse] = Field(
        description="The browser's active sessions, newest first."
    )

    @classmethod
    def from_own_device(cls, own: OwnDevice) -> OwnDeviceResponse:
        """Build a response from an `OwnDevice`."""
        sessions = [SessionResponse.from_own_session(s) for s in own.sessions]
        latest = max(s.last_seen_at for s in sessions)
        device = own.device
        if device is None:
            only = own.sessions[0].session
            return cls(
                user_agent=only.user_agent,
                platform=only.client_platform,
                mobile=only.client_mobile,
                first_seen_at=only.created_at,
                last_seen_at=latest,
                current=own.current,
                sessions=sessions,
            )
        return cls(
            id=device.id,
            name=device.name,
            user_agent=device.user_agent,
            platform=device.platform,
            mobile=device.mobile,
            first_seen_at=device.created_at,
            last_seen_at=max(latest, device.last_seen_at),
            current=own.current,
            sessions=sessions,
        )


class AdminSessionResponse(BaseModel):
    """An active session with its owner's identity details, for administrators."""

    model_config = ConfigDict(json_schema_extra={"examples": [_ADMIN_SESSION_EXAMPLE]})

    id: uuid.UUID = Field(description="The session's id.")
    user_id: uuid.UUID = Field(description="The id of the account it belongs to.")
    username: str = Field(description="That account's sign-in name.")
    display_name: str | None = Field(
        default=None, description="That account's display name."
    )
    user_agent: str | None = Field(
        default=None, description="The browser's user agent when it signed in."
    )
    client_platform: str | None = Field(
        default=None, description="The platform the browser reported, if any."
    )
    client_mobile: bool | None = Field(
        default=None, description="Whether the browser reported a mobile device."
    )
    client_ip: str | None = Field(
        default=None, description="The address the session signed in from."
    )
    created_at: datetime = Field(description="When the session started.")
    last_seen_at: datetime = Field(description="The session's latest request.")
    expires_at: datetime = Field(description="When the session ends unless used.")
    device_id: uuid.UUID | None = Field(
        default=None,
        description="The remembered browser this session was started in, if any.",
    )
    device_name: str | None = Field(
        default=None,
        description="The name its owner gave that browser, if it has one.",
    )
    display_mode: DisplayMode | None = Field(
        default=None,
        description=(
            "Whether the session was started in a browser tab or the installed app,"
            + " as the app reported it; absent for older sessions."
        ),
    )

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
            device_id=session.device_id,
            device_name=listing.device_name,
            display_mode=session.display_mode,
        )


DEVICE_NAME_EXAMPLE: dict[str, Any] = {
    "id": "01978c3e-2b8b-7c3a-9c2e-3a2f6b9d4e52",
    "name": "Alice's laptop",
}
DEVICE_NAME_SUGGESTION_EXAMPLE: dict[str, Any] = {
    **DEVICE_NAME_EXAMPLE,
    "user_agent": "Mozilla/5.0 (X11; Linux x86_64) Firefox/130.0",
    "platform": "Linux",
    "last_seen_at": "2026-10-10T12:30:00.000000Z",
}


class RenameDeviceRequest(RequestModel):
    """Request body for naming a device, or clearing its name."""

    model_config = ConfigDict(
        json_schema_extra={"examples": [{"name": "Alice's laptop"}]}
    )

    name: str | None = Field(
        description=(
            f"The name to give the device, at most {MAX_DEVICE_NAME_LENGTH}"
            + " characters once trimmed. Null or blank clears it."
        ),
    )


class DeviceNameResponse(BaseModel):
    """A device and the name it now has."""

    model_config = ConfigDict(json_schema_extra={"examples": [DEVICE_NAME_EXAMPLE]})

    id: uuid.UUID = Field(description="The device's id.")
    name: str | None = Field(description="Its name; null when it has none.")

    @classmethod
    def from_domain(cls, device: Device) -> DeviceNameResponse:
        """Build a response from a `Device`."""
        return cls(id=device.id, name=device.name)


class DeviceNameSuggestionResponse(BaseModel):
    """An older device of yours whose name this browser could take."""

    model_config = ConfigDict(
        json_schema_extra={"examples": [DEVICE_NAME_SUGGESTION_EXAMPLE]}
    )

    id: uuid.UUID = Field(description="The older device's id.")
    name: str = Field(description="The name it would give this browser.")
    user_agent: str | None = Field(
        default=None, description="The older browser's user agent at its last sign-in."
    )
    platform: str | None = Field(
        default=None, description="The platform the older browser reported."
    )
    last_seen_at: datetime = Field(description="When the older device was last used.")

    @classmethod
    def from_domain(cls, device: Device) -> DeviceNameSuggestionResponse:
        """Build a response from a named `Device`."""
        return cls(
            id=device.id,
            name=device.name or "",
            user_agent=device.user_agent,
            platform=device.platform,
            last_seen_at=device.last_seen_at,
        )


class RevokedSessionsResponse(BaseModel):
    """The number of other sessions that were ended."""

    model_config = ConfigDict(json_schema_extra={"examples": [{"ended": 2}]})

    ended: int = Field(description="How many other sessions were ended.")


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
    name: str = Field(
        description="A label to recognise the token by.",
        max_length=MAX_TOKEN_NAME_LENGTH * 4,
    )
    password: str = Field(
        description="Your current passphrase, to confirm it is you.",
        max_length=_MAX_PASSWORD_INPUT,
    )
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

    password: str = Field(
        description="Your current passphrase, to confirm it is you.",
        max_length=_MAX_PASSWORD_INPUT,
    )
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

    id: uuid.UUID = Field(description="The token's id.")
    name: str = Field(description="Its label.")
    grants: list[str] = Field(description="The permissions it holds.")
    created_at: datetime = Field(description="When it was created.")
    expires_at: datetime = Field(description="When it stops working.")
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

    permissions: list[Permission] = Field(
        description="Permissions a token of yours may hold."
    )
