"""Settings provenance and startup source labels."""

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from pathlib import Path

import pytest
from pydantic import AliasChoices, Field, ValidationError
from pydantic_settings import (
    BaseSettings,
    PydanticBaseSettingsSource,
    SettingsConfigDict,
)
from structlog.testing import capture_logs

from app.entrypoints.api import startup
from app.platform.config import BackupSettings, MenageristBaseSettings


class Settings(MenageristBaseSettings):
    """A small settings group with both alias styles."""

    count: int = 1
    timezone: str = Field(
        default="UTC", validation_alias=AliasChoices("MENAGERIST_TIMEZONE", "TZ")
    )


def test_precedence_and_labels(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """Record the winning source without changing settings behaviour."""
    dotenv = tmp_path / ".env"
    dotenv.write_text("MENAGERIST_COUNT=2\nTZ=Europe/London\n")
    secret = tmp_path / "menagerist_count"
    secret.write_text("3")
    settings = Settings(_env_file=dotenv, _secrets_dir=tmp_path)
    assert settings.count == 2
    assert settings.source_of("count") == "dotenv"
    assert settings.source_of("timezone") == "dotenv"
    assert settings.is_pinned("count")
    monkeypatch.setenv("MENAGERIST_COUNT", "4")
    assert Settings(_env_file=dotenv).source_of("count") == "env"
    settings = Settings(count=5, _env_file=dotenv)
    assert settings.count == 5
    assert settings.source_of("count") == "init"
    assert not settings.is_pinned("count")
    monkeypatch.delenv("MENAGERIST_COUNT")
    assert Settings(_secrets_dir=tmp_path).source_of("count") == "secret_file"
    assert Settings().source_of("count") == "default"
    assert settings.source_of("count") == "init"
    copied = settings.sources()
    copied["count"] = "changed"
    assert settings.source_of("count") == "init"
    assert "_sources" not in settings.model_dump()
    assert "_sources" not in repr(settings)
    with pytest.raises(ValidationError):
        settings.count = 0  # type: ignore[misc]
    with pytest.raises(ValidationError):
        type(
            "InvalidDefault",
            (Settings,),
            {"__annotations__": {"count": int}, "count": "bad"},
        )()


def test_full_alias(monkeypatch: pytest.MonkeyPatch) -> None:
    """Translate full environment aliases back to field names."""
    monkeypatch.setenv("MENAGERIST_BACKUP_BEFORE_MIGRATE", "false")
    settings = BackupSettings()
    assert not settings.before_migrate
    assert settings.source_of("before_migrate") == "env"


class CustomSource(PydanticBaseSettingsSource):
    """A labelled source added by subclass customisation."""

    source_label = "custom"

    def get_field_value(
        self, field: object, field_name: str
    ) -> tuple[object, str, bool]:
        """Unused by this dictionary source."""
        return None, field_name, False

    def __call__(self) -> dict[str, object]:
        """Supply a custom count."""
        return {"count": 9}


class Replaced(Settings):
    """Replace the standard source order."""

    @classmethod
    def settings_customise_sources(
        cls,
        settings_cls: type[BaseSettings],
        init_settings: PydanticBaseSettingsSource,
        env_settings: PydanticBaseSettingsSource,
        dotenv_settings: PydanticBaseSettingsSource,
        file_secret_settings: PydanticBaseSettingsSource,
    ) -> tuple[PydanticBaseSettingsSource, ...]:
        """Choose the sources for this group."""
        return (CustomSource(settings_cls), env_settings, init_settings)


class Extended(Settings):
    """Extend the tracked standard sources."""

    @classmethod
    def settings_customise_sources(
        cls,
        settings_cls: type[BaseSettings],
        init_settings: PydanticBaseSettingsSource,
        env_settings: PydanticBaseSettingsSource,
        dotenv_settings: PydanticBaseSettingsSource,
        file_secret_settings: PydanticBaseSettingsSource,
    ) -> tuple[PydanticBaseSettingsSource, ...]:
        """Choose the sources for this group."""
        return (
            *super().settings_customise_sources(
                settings_cls,
                init_settings,
                env_settings,
                dotenv_settings,
                file_secret_settings,
            ),
            CustomSource(settings_cls),
        )


class Inherited(Replaced):
    """Inherit an already tracked override."""

    pass


@pytest.mark.parametrize("settings_cls", [Replaced, Inherited, Extended])
def test_overrides(settings_cls: type[Settings], tmp_path: Path) -> None:
    """Track replaced, extended and inherited source customisations."""
    dotenv = tmp_path / ".env"
    dotenv.write_text("MENAGERIST_COUNT=2")
    settings = settings_cls(_env_file=dotenv)
    assert settings.count == (2 if settings_cls is Extended else 9)
    assert settings.source_of("count") == (
        "dotenv" if settings_cls is Extended else "custom"
    )


def test_log_sources(monkeypatch: pytest.MonkeyPatch) -> None:
    """Log defaults and supplied sources beside JSON values."""
    monkeypatch.setattr(startup, "INSTANCE_SETTINGS", (lambda: Settings(count=3),))
    with capture_logs() as logs:
        startup.log_instance_settings()
    assert logs[0]["sources"] == {"count": "init", "timezone": "default"}
    assert logs[0]["values"]["count"] == 3


@pytest.mark.parametrize("env_name", ["MENAGERIST_TIMEZONE", "TZ"])
def test_alias_choices(monkeypatch: pytest.MonkeyPatch, env_name: str) -> None:
    """Both environment aliases report the Python field name."""
    monkeypatch.delenv("MENAGERIST_TIMEZONE", raising=False)
    monkeypatch.delenv("TZ", raising=False)
    monkeypatch.setenv(env_name, "Europe/London")
    settings = Settings()
    assert settings.timezone == "Europe/London"
    assert settings.source_of("timezone") == "env"


def test_reordered_sources(monkeypatch: pytest.MonkeyPatch) -> None:
    """The returned order, rather than a hard-coded priority, determines provenance."""

    class EnvFirst(Settings):
        @classmethod
        def settings_customise_sources(
            cls,
            settings_cls: type[BaseSettings],
            init_settings: PydanticBaseSettingsSource,
            env_settings: PydanticBaseSettingsSource,
            dotenv_settings: PydanticBaseSettingsSource,
            file_secret_settings: PydanticBaseSettingsSource,
        ) -> tuple[PydanticBaseSettingsSource, ...]:
            return env_settings, init_settings

    monkeypatch.setenv("MENAGERIST_COUNT", "7")
    settings = EnvFirst(count=5)
    assert settings.count == 7
    assert settings.source_of("count") == "env"


def test_custom_fallback_label_and_source_state() -> None:
    """Custom sources retain state and class-name labels, even after super calls."""

    class StateSource(PydanticBaseSettingsSource):
        def get_field_value(
            self, field: object, field_name: str
        ) -> tuple[object, str, bool]:
            return None, field_name, False

        def __call__(self) -> dict[str, object]:
            assert self.current_state["count"] == 4
            assert self.settings_sources_data["InitSettingsSource"]["count"] == 4
            return {"MENAGERIST_TIMEZONE": "Europe/London"}

    class StateSettings(Settings):
        @classmethod
        def settings_customise_sources(
            cls,
            settings_cls: type[BaseSettings],
            init_settings: PydanticBaseSettingsSource,
            env_settings: PydanticBaseSettingsSource,
            dotenv_settings: PydanticBaseSettingsSource,
            file_secret_settings: PydanticBaseSettingsSource,
        ) -> tuple[PydanticBaseSettingsSource, ...]:
            sources = super().settings_customise_sources(
                settings_cls,
                init_settings,
                env_settings,
                dotenv_settings,
                file_secret_settings,
            )
            return *sources, StateSource(settings_cls)

    settings = StateSettings(count=4)
    assert settings.count == 4
    assert settings.source_of("count") == "init"
    assert settings.source_of("timezone") == "StateSource"


def test_collector_restored_after_nested_and_failed_construction() -> None:
    """Nested settings and validation failures cannot overwrite another source map."""

    class NestedSource(CustomSource):
        def __call__(self) -> dict[str, object]:
            assert Settings(count=6).source_of("count") == "init"
            with pytest.raises(ValidationError):
                Settings(count="bad")
            return {"count": 9}

    class Nested(Settings):
        @classmethod
        def settings_customise_sources(
            cls,
            settings_cls: type[BaseSettings],
            init_settings: PydanticBaseSettingsSource,
            env_settings: PydanticBaseSettingsSource,
            dotenv_settings: PydanticBaseSettingsSource,
            file_secret_settings: PydanticBaseSettingsSource,
        ) -> tuple[PydanticBaseSettingsSource, ...]:
            return (NestedSource(settings_cls),)

    assert Nested().source_of("count") == "custom"
    assert Settings().source_of("count") == "default"
    with pytest.raises(KeyError):
        Settings().source_of("missing")


def test_preferred_alias_from_later_source_is_the_effective_source(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Provenance follows Pydantic's alias choice across custom source keys."""

    class AliasSource(CustomSource):
        def __call__(self) -> dict[str, object]:
            return {"TZ": "Europe/London"}

    class AliasSettings(Settings):
        model_config = SettingsConfigDict(extra="ignore")

        @classmethod
        def settings_customise_sources(
            cls,
            settings_cls: type[BaseSettings],
            init_settings: PydanticBaseSettingsSource,
            env_settings: PydanticBaseSettingsSource,
            dotenv_settings: PydanticBaseSettingsSource,
            file_secret_settings: PydanticBaseSettingsSource,
        ) -> tuple[PydanticBaseSettingsSource, ...]:
            return AliasSource(settings_cls), env_settings

    monkeypatch.setenv("MENAGERIST_TIMEZONE", "UTC")
    settings = AliasSettings()
    assert settings.timezone == "UTC"
    assert settings.source_of("timezone") == "env"
    assert settings.is_pinned("timezone")


def test_super_override_does_not_wrap_recorders_twice() -> None:
    """An override calling super preserves the existing recorder instances."""
    from app.platform.config._tracking import _Recorder

    settings = Extended()
    sources = Extended.settings_customise_sources(
        Extended,
        CustomSource(Extended),
        CustomSource(Extended),
        CustomSource(Extended),
        CustomSource(Extended),
    )
    assert len(sources) == 5
    assert all(isinstance(source, _Recorder) for source in sources)
    assert all(
        not isinstance(source.source, _Recorder)
        for source in sources
        if isinstance(source, _Recorder)
    )
    assert settings.source_of("count") == "custom"
