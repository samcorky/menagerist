"""The web app manifest that makes an instance installable as an app.

Identity (`id`, `scope`, `start_url`) is the origin root: changing `id` makes browsers
treat the app as a second one. Nothing here may depend on the person asking, as the
manifest is public.
"""

from dataclasses import dataclass

# Colours of the light theme, repeated from the frontend (`THEME_COLOURS`).
_LIGHT = "#ffffff"
_ICONS: tuple[tuple[str, str, str], ...] = (
    ("/icon-192.png", "192x192", "any"),
    ("/icon-512.png", "512x512", "any"),
    ("/icon-maskable-512.png", "512x512", "maskable"),
)
# Name, short name (launchers show it when space is tight, so about 12 characters at
# most), description, route and icon. Each icon is the glyph of the matching button in
# the phone tab bar, drawn by `scripts/generate_pwa_icons.py`.
_SHORTCUTS: tuple[tuple[str, str, str, str, str], ...] = (
    (
        "Add an item",
        "Add item",
        "Add something new to your collection",
        "/items/new",
        "/shortcut-add-item.png",
    ),
    (
        "Browse items",
        "Items",
        "Search and browse everything you own",
        "/items",
        "/shortcut-items.png",
    ),
    (
        "Collections",
        "Collections",
        "Open your collections",
        "/collections",
        "/shortcut-collections.png",
    ),
)
_SHORTCUT_ICON_SIZE = "192x192"
_SCREENSHOTS: tuple[tuple[str, str, str, str], ...] = (
    ("/screenshot-narrow.png", "780x1688", "narrow", "Browse your items on a phone"),
    ("/screenshot-wide.png", "1280x800", "wide", "Browse your items on a desktop"),
)


@dataclass(frozen=True, kw_only=True)
class ManifestIcon:
    """An install icon."""

    src: str
    sizes: str
    purpose: str
    type: str = "image/png"


@dataclass(frozen=True, kw_only=True)
class ManifestShortcut:
    """A launcher shortcut into a route."""

    name: str
    short_name: str
    description: str
    url: str
    icons: tuple[ManifestIcon, ...]


@dataclass(frozen=True, kw_only=True)
class ManifestScreenshot:
    """A store-style screenshot shown by install prompts."""

    src: str
    sizes: str
    form_factor: str
    label: str
    type: str = "image/png"


@dataclass(frozen=True, kw_only=True)
class WebAppManifest:
    """What an instance advertises about itself when installed.

    `origin` is the configured public origin, or `None` to leave every URL relative to
    the manifest, which the browser resolves against the address it was loaded from.
    """

    name: str = "Menagerist"
    short_name: str = "Menagerist"
    description: str
    origin: str | None = None
    display: str = "standalone"
    display_override: tuple[str, ...] = ("standalone", "minimal-ui")
    orientation: str = "any"
    lang: str = "en-GB"
    dir: str = "ltr"
    categories: tuple[str, ...] = ("productivity", "lifestyle")
    background_color: str = _LIGHT
    theme_color: str = _LIGHT

    def url(self, path: str) -> str:
        """Return `path` on the public origin, or as it is when none is set."""
        return f"{(self.origin or '').rstrip('/')}{path}"

    @property
    def id(self) -> str:
        """The app's identity; changing it makes browsers install a second app."""
        return self.url("/")

    @property
    def start_url(self) -> str:
        """Where a launched app opens."""
        return self.url("/")

    @property
    def scope(self) -> str:
        """The URLs that count as part of the app."""
        return self.url("/")

    @property
    def icons(self) -> tuple[ManifestIcon, ...]:
        """Install icons: 192 and 512 for installability, plus a maskable one."""
        return tuple(
            ManifestIcon(src=self.url(src), sizes=sizes, purpose=purpose)
            for src, sizes, purpose in _ICONS
        )

    @property
    def shortcuts(self) -> tuple[ManifestShortcut, ...]:
        """Launcher shortcuts."""
        return tuple(
            ManifestShortcut(
                name=name,
                short_name=short,
                description=description,
                url=self.url(path),
                icons=(
                    ManifestIcon(
                        src=self.url(icon), sizes=_SHORTCUT_ICON_SIZE, purpose="any"
                    ),
                ),
            )
            for name, short, description, path, icon in _SHORTCUTS
        )

    @property
    def screenshots(self) -> tuple[ManifestScreenshot, ...]:
        """One narrow and one wide screenshot."""
        return tuple(
            ManifestScreenshot(
                src=self.url(src), sizes=sizes, form_factor=form_factor, label=label
            )
            for src, sizes, form_factor, label in _SCREENSHOTS
        )
