"""Request and response bodies for the settings API."""

from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field

from app.modules.settings.application.update_my_settings import UpdateMySettingsCommand
from app.modules.settings.application.update_settings import UpdateSettingsCommand
from app.modules.settings.domain.setting import ResolvedSetting  # noqa: TC001
from app.platform.request_model import RequestModel

type SettingJson = Annotated[
    bool | int | float | str | list[str],
    Field(description="A setting's value: a flag, number, text or list of text."),
]


class SettingResponse(BaseModel):
    """One setting with its effective value and where that value came from."""

    model_config = ConfigDict(
        json_schema_extra={
            "examples": [
                {
                    "key": "backup.keep_last",
                    "group": "backup",
                    "title": "Backups to keep",
                    "description": "Minimum number of ordinary backups to retain.",
                    "value": 12,
                    "source": "instance",
                    "locked": False,
                    "env_name": "MENAGERIST_BACKUP_KEEP_LAST",
                    "restart_required": False,
                    "stored_invalid": False,
                    "hidden": False,
                }
            ]
        }
    )

    key: str = Field(description="Stable name of the setting, `group.field`.")
    group: str = Field(description="The part of the app the setting belongs to.")
    title: str = Field(description="The setting's name, for people.")
    description: str | None = Field(
        description="What it does; null if the title says enough."
    )
    value: SettingJson = Field(description="The effective value.")
    source: Literal["default", "env_default", "instance", "user", "env"] = Field(
        description=(
            "Which layer supplied the value. `env_default` is a per-person "
            + "setting's default that the deployment sets through `env_name`."
        )
    )
    locked: bool = Field(
        description="True when the deployment sets the value, so it cannot be changed."
    )
    env_name: str | None = Field(
        description="The environment variable that sets this value, if any."
    )
    restart_required: bool = Field(
        description="True when a change only takes effect after a restart."
    )
    stored_invalid: bool = Field(
        description="True when a saved value no longer validates and is being ignored."
    )
    hidden: bool = Field(
        description=(
            "True for a per-person setting changed elsewhere in the app, so not "
            + "offered on a settings form."
        )
    )

    @classmethod
    def from_domain(cls, resolved: ResolvedSetting) -> SettingResponse:
        """Build the response for a resolved setting."""
        descriptor = resolved.descriptor
        return cls(
            key=descriptor.key,
            group=descriptor.group,
            title=descriptor.title,
            description=descriptor.description,
            value=resolved.value,
            source=resolved.source.value,
            locked=resolved.locked,
            env_name=resolved.env_name,
            restart_required=descriptor.restart_required,
            stored_invalid=resolved.stored_invalid,
            hidden=descriptor.hidden,
        )


class UpdateSettingsRequest(RequestModel):
    """The settings to change, by key. Settings not named are left alone."""

    model_config = ConfigDict(
        json_schema_extra={
            "examples": [
                {"values": {"backup.keep_last": 12, "backup.schedule": "0 4 * * *"}}
            ]
        }
    )

    values: dict[str, SettingJson] = Field(
        description="New value for each setting to change, keyed by setting key."
    )

    def to_command(self) -> UpdateSettingsCommand:
        """Convert to the use case's command."""
        return UpdateSettingsCommand(values=self.values)

    def to_own_command(self) -> UpdateMySettingsCommand:
        """Convert to the per-person use case's command."""
        return UpdateMySettingsCommand(values=self.values)
