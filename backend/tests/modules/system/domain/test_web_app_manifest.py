from app.modules.system.domain.web_app_manifest import WebAppManifest


def test_identity_is_the_origin_root() -> None:
    """The id, scope and start URL stay at `/`, since changing the id forks the app."""
    manifest = WebAppManifest()

    assert manifest.id == manifest.start_url == manifest.scope == "/"
    assert manifest.display == "standalone"


def test_urls_stay_relative_without_a_public_origin() -> None:
    """The browser resolves relative URLs against where it loaded the manifest from."""
    manifest = WebAppManifest()

    assert manifest.icons[0].src == "/icon-192.png"
    assert manifest.shortcuts[0].url == "/items/new"


def test_urls_use_the_public_origin_when_set() -> None:
    """Every URL is built from the configured origin, tolerating a trailing slash."""
    manifest = WebAppManifest(origin="https://menagerist.example.com/")

    assert manifest.id == manifest.scope == "https://menagerist.example.com/"
    urls = [
        *(icon.src for icon in manifest.icons),
        *(shortcut.url for shortcut in manifest.shortcuts),
        *(shot.src for shot in manifest.screenshots),
    ]
    assert all(u.startswith("https://menagerist.example.com/") for u in urls)
    assert not any("//" in u.removeprefix("https://") for u in urls)


def test_installability_needs_192_512_and_maskable_icons() -> None:
    """Chromium's install criteria: a 192 and a 512 icon, plus a maskable one."""
    assert {(i.sizes, i.purpose) for i in WebAppManifest().icons} >= {
        ("192x192", "any"),
        ("512x512", "any"),
        ("512x512", "maskable"),
    }


def test_shortcut_short_name_is_optional() -> None:
    """A shortcut only carries a short name when it has a distinct one."""
    shortcuts = WebAppManifest().shortcuts

    assert shortcuts[0].short_name == "Add item"
    assert shortcuts[-1].short_name is None
