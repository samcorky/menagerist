from pathlib import Path

from app.modules.system.domain.web_app_manifest import WebAppManifest


def test_identity_is_the_origin_root() -> None:
    """The id, scope and start URL stay at `/`, since changing the id forks the app."""
    manifest = WebAppManifest(description="An app.")

    assert manifest.id == manifest.start_url == manifest.scope == "/"
    assert manifest.display == "standalone"


def test_urls_stay_relative_without_a_public_origin() -> None:
    """The browser resolves relative URLs against where it loaded the manifest from."""
    manifest = WebAppManifest(description="An app.")

    assert manifest.icons[0].src == "/icon-192.png"
    assert manifest.shortcuts[0].url == "/items/new"


def test_urls_use_the_public_origin_when_set() -> None:
    """Every URL is built from the configured origin, tolerating a trailing slash."""
    manifest = WebAppManifest(
        description="An app.", origin="https://menagerist.example.com/"
    )

    assert manifest.id == manifest.scope == "https://menagerist.example.com/"
    urls = [
        *(icon.src for icon in manifest.icons),
        *(shortcut.url for shortcut in manifest.shortcuts),
        *(icon.src for shortcut in manifest.shortcuts for icon in shortcut.icons),
        *(shot.src for shot in manifest.screenshots),
    ]
    assert all(u.startswith("https://menagerist.example.com/") for u in urls)
    assert not any("//" in u.removeprefix("https://") for u in urls)


def test_installability_needs_192_512_and_maskable_icons() -> None:
    """Chromium's install criteria: a 192 and a 512 icon, plus a maskable one."""
    assert {
        (i.sizes, i.purpose) for i in WebAppManifest(description="An app.").icons
    } >= {
        ("192x192", "any"),
        ("512x512", "any"),
        ("512x512", "maskable"),
    }


def test_every_shortcut_has_a_short_name_a_description_and_an_icon() -> None:
    """Launchers show the short name when space is tight, so it stays short."""
    shortcuts = WebAppManifest(description="An app.").shortcuts

    assert [s.url for s in shortcuts] == ["/items/new", "/items", "/collections"]
    for shortcut in shortcuts:
        assert 0 < len(shortcut.short_name) <= 12
        assert shortcut.description
        assert [(i.sizes, i.type) for i in shortcut.icons] == [("192x192", "image/png")]


def test_shortcut_icons_use_the_public_origin_when_set() -> None:
    """An icon address is built like every other one."""
    manifest = WebAppManifest(
        description="An app.", origin="https://menagerist.example.com"
    )

    assert manifest.shortcuts[0].icons[0].src == (
        "https://menagerist.example.com/shortcut-add-item.png"
    )


def test_every_image_the_manifest_names_exists_in_the_frontend_static_folder() -> None:
    """A renamed or forgotten icon would 404 in the launcher with no other sign."""
    static = Path(__file__).resolve().parents[5] / "frontend" / "static"
    manifest = WebAppManifest(description="An app.")
    names = [
        *(icon.src for icon in manifest.icons),
        *(icon.src for shortcut in manifest.shortcuts for icon in shortcut.icons),
        *(shot.src for shot in manifest.screenshots),
    ]

    assert names
    assert [n for n in names if not (static / n.removeprefix("/")).is_file()] == []
