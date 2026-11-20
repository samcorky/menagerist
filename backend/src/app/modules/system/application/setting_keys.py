"""The tunable settings this module reads."""

from app.shared_kernel.settings import SettingKey

RELEASE_CHANNEL = SettingKey[str]("release.channel")
BRANDING_NAME = SettingKey[str]("branding.name")
BRANDING_SHORT_NAME = SettingKey[str]("branding.short_name")
BRANDING_DESCRIPTION = SettingKey[str]("branding.description")
