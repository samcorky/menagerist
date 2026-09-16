from unittest.mock import patch

from app.entrypoints.api import create_app
from app.platform.app_info import AppInfo
from app.platform.build_info import BuildInfo
from app.platform.project_info import ProjectInfo


def test_license_url_none_when_repository_url_missing() -> None:
    """Return None when build metadata lacks a repository URL."""
    app_info = AppInfo(
        project=ProjectInfo(name="menagerist", version="1.0.0", license="Apache-2.0"),
        build=BuildInfo(repository_url=None, commit_sha="abcdef123456"),
    )
    assert app_info.license_url is None


def test_license_url_fallback_to_main_when_commit_sha_missing() -> None:
    """Fall back to main branch when commit SHA is absent."""
    app_info = AppInfo(
        project=ProjectInfo(name="menagerist", version="1.0.0", license="Apache-2.0"),
        build=BuildInfo(
            repository_url="https://github.com/example/menagerist",
            commit_sha=None,
        ),
    )
    assert (
        app_info.license_url
        == "https://github.com/example/menagerist/blob/main/LICENSE"
    )


def test_license_url_pinned_to_commit_sha() -> None:
    """Pin license URL to the exact commit SHA when present."""
    app_info = AppInfo(
        project=ProjectInfo(name="menagerist", version="1.0.0", license="Apache-2.0"),
        build=BuildInfo(
            repository_url="https://github.com/example/menagerist/",
            commit_sha="abcdef123456",
        ),
    )
    assert (
        app_info.license_url
        == "https://github.com/example/menagerist/blob/abcdef123456/LICENSE"
    )


def test_app_properties() -> None:
    """Proxy name and version properties to project metadata."""
    app_info = AppInfo(
        project=ProjectInfo(name="menagerist", version="1.2.3"),
        build=BuildInfo(),
    )
    assert app_info.name == "menagerist"
    assert app_info.version == "1.2.3"
    assert app_info.license_url is None


def test_create_app_with_license_url() -> None:
    """Include license URL in OpenAPI schema when available."""
    mock_app_info = AppInfo(
        project=ProjectInfo(name="menagerist", version="1.0.0", license="Apache-2.0"),
        build=BuildInfo(
            repository_url="https://github.com/example/menagerist",
            commit_sha="abcdef1",
        ),
    )
    with patch("app.entrypoints.api.load_app_info", return_value=mock_app_info):
        app = create_app()
        schema = app.openapi()
        assert schema["info"]["license"] == {
            "name": "Apache-2.0",
            "url": "https://github.com/example/menagerist/blob/abcdef1/LICENSE",
        }


def test_create_app_without_license_url() -> None:
    """Omit license URL in OpenAPI schema when repository URL is absent."""
    mock_app_info = AppInfo(
        project=ProjectInfo(name="menagerist", version="1.0.0", license="Apache-2.0"),
        build=BuildInfo(repository_url=None, commit_sha=None),
    )
    with patch("app.entrypoints.api.load_app_info", return_value=mock_app_info):
        app = create_app()
        schema = app.openapi()
        assert schema["info"]["license"] == {
            "name": "Apache-2.0",
        }


def test_create_app_without_license_name() -> None:
    """Omit license in OpenAPI schema when license name is absent."""
    mock_app_info = AppInfo(
        project=ProjectInfo(name="menagerist", version="1.0.0", license=None),
        build=BuildInfo(repository_url=None, commit_sha=None),
    )
    with patch("app.entrypoints.api.load_app_info", return_value=mock_app_info):
        app = create_app()
        schema = app.openapi()
        assert "license" not in schema["info"]
