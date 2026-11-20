import pytest
from pydantic import ValidationError

from app.platform.config import ALL_SETTINGS, INSTANCE_SETTINGS, BrandingSettings
from app.platform.config.branding import get_branding_settings


def test_defaults_are_menagerist() -> None:
    """An instance nobody has branded installs as Menagerist."""
    settings = BrandingSettings()
    assert settings.name == "Menagerist"
    assert settings.short_name == "Menagerist"
    assert settings.description == ""


def test_reads_the_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    """Every field comes from `MENAGERIST_BRANDING_*`."""
    monkeypatch.setenv("MENAGERIST_BRANDING_NAME", "The Hoard")
    monkeypatch.setenv("MENAGERIST_BRANDING_SHORT_NAME", "Hoard")
    monkeypatch.setenv("MENAGERIST_BRANDING_DESCRIPTION", "Our family's things.")
    settings = BrandingSettings()
    assert (settings.name, settings.short_name) == ("The Hoard", "Hoard")
    assert settings.description == "Our family's things."


def test_names_are_trimmed() -> None:
    """Spaces around a name are not part of it."""
    assert BrandingSettings(name="  The Hoard  ").name == "The Hoard"


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("name", " "),
        ("name", "x" * 46),
        ("short_name", ""),
        ("short_name", "x" * 13),
        ("description", "x" * 301),
    ],
)
def test_names_and_description_have_limits(field: str, value: str) -> None:
    """A name cannot be blank, and each text has a length a launcher can show."""
    with pytest.raises(ValidationError):
        BrandingSettings.model_validate({field: value})


def test_registered_with_every_setting() -> None:
    """The group is in the settings reference and describes a running instance."""
    assert BrandingSettings in ALL_SETTINGS
    assert get_branding_settings in INSTANCE_SETTINGS
