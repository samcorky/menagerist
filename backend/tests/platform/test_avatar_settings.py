import pytest
from pydantic import ValidationError

from app.platform.config import ALL_SETTINGS, AvatarSettings


def test_defaults_use_cataas() -> None:
    """Random cat asks cataas unless the deployment says otherwise."""
    settings = AvatarSettings()
    assert settings.cat_service_enabled is True
    assert settings.cat_service_url == "https://cataas.com"


def test_reads_the_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    """Both settings come from `MENAGERIST_AVATARS_*`."""
    monkeypatch.setenv("MENAGERIST_AVATARS_CAT_SERVICE_ENABLED", "false")
    monkeypatch.setenv("MENAGERIST_AVATARS_CAT_SERVICE_URL", "http://cats.lan:8080")
    settings = AvatarSettings()
    assert settings.cat_service_enabled is False
    assert settings.cat_service_url == "http://cats.lan:8080"


@pytest.mark.parametrize("url", ["cataas.com", "ftp://cataas.com", "", "https://"])
def test_url_must_be_a_web_address(url: str) -> None:
    """Only an http or https address with a host is accepted."""
    with pytest.raises(ValidationError):
        AvatarSettings(cat_service_url=url)


def test_registered_with_every_setting() -> None:
    """The group appears in the generated settings reference."""
    assert AvatarSettings in ALL_SETTINGS
