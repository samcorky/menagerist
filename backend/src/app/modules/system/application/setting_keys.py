"""The tunable settings this module reads."""

from app.shared_kernel.settings import SettingKey

RELEASE_CHANNEL = SettingKey[str]("release.channel")
