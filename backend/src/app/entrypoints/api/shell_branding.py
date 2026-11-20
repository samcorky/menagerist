"""Fill the SPA shell's marked tags with the instance's branding.

`frontend/src/app.html` marks each tag the server fills in with `data-branding`, and
keeps a working default in its `content`, so the page is complete without the server
(the Vite dev server, `vite preview`). The marker names the value:

* `name`, `description`: the instance's branding, as an administrator set it
* `absolute-url`: the tag's own path, on the public origin when one is configured
* `page-url`: the requested page on the public origin; dropped when there is none

The shell is parsed once with the standard library's HTML parser, so the rewrite does
not depend on how a tag is formatted, and the page is rendered by joining its text with
the filled-in tags. Everything outside a marked tag is passed through unchanged.
"""

import html
from dataclasses import dataclass
from html.parser import HTMLParser
from typing import TYPE_CHECKING, Literal, get_args

from app.shared_kernel.errors import InfrastructureError

if TYPE_CHECKING:
    from app.modules.system.domain.branding import Branding

type Field = Literal["name", "description", "absolute-url", "page-url"]
MARKER = "data-branding"
_FIELDS: frozenset[str] = frozenset(get_args(Field.__value__))


class UnknownBrandingFieldError(InfrastructureError):
    """A tag in the shell names a `data-branding` value the server does not fill."""


@dataclass(frozen=True, kw_only=True)
class _MarkedTag:
    """A start tag to fill in, with its attributes in order and the marker removed."""

    name: str
    attrs: tuple[tuple[str, str | None], ...]
    field: Field
    self_closing: bool


@dataclass(frozen=True, kw_only=True)
class _Found:
    line: int
    column: int
    length: int
    tag: _MarkedTag


class _MarkedTagFinder(HTMLParser):
    """Collects every start tag carrying the marker, with where it sits in the text."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.found: list[_Found] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        self._collect(tag, attrs, self_closing=False)

    def handle_startendtag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        self._collect(tag, attrs, self_closing=True)

    def _collect(
        self, tag: str, attrs: list[tuple[str, str | None]], *, self_closing: bool
    ) -> None:
        field = dict(attrs).get(MARKER)
        if field is None:
            return
        if field not in _FIELDS:
            msg = f"unknown {MARKER} value in the app shell: {field!r}"
            raise UnknownBrandingFieldError(msg)
        line, column = self.getpos()
        raw = self.get_starttag_text() or ""
        kept = tuple((key, value) for key, value in attrs if key != MARKER)
        marked = _MarkedTag(
            name=tag,
            attrs=kept,
            field=field,  # type: ignore[arg-type]  # checked against _FIELDS above
            self_closing=self_closing,
        )
        self.found.append(_Found(line=line, column=column, length=len(raw), tag=marked))


class ShellTemplate:
    """The SPA shell, split into fixed text and the tags branding fills in."""

    def __init__(self, text: str) -> None:
        finder = _MarkedTagFinder()
        finder.feed(text)
        finder.close()
        line_starts = [0, *(i + 1 for i, c in enumerate(text) if c == "\n")]
        segments: list[str | _MarkedTag] = []
        position = 0
        for found in finder.found:
            start = line_starts[found.line - 1] + found.column
            segments.extend((text[position:start], found.tag))
            position = start + found.length
        segments.append(text[position:])
        self._segments = tuple(segments)

    @property
    def fields(self) -> frozenset[Field]:
        """The markers the shell uses, so a test can tell none went missing."""
        return frozenset(s.field for s in self._segments if isinstance(s, _MarkedTag))

    def render(self, branding: Branding, *, origin: str | None, path: str) -> str:
        """The shell with every marked tag filled in for this instance and page."""
        base = origin.rstrip("/") if origin else None
        return "".join(
            segment
            if isinstance(segment, str)
            else _render(segment, branding, base=base, path=path)
            for segment in self._segments
        )


def _render(tag: _MarkedTag, branding: Branding, *, base: str | None, path: str) -> str:
    """One marked tag with its `content` filled in, or nothing if it is dropped."""
    current = dict(tag.attrs).get("content") or ""
    match tag.field:
        case "name":
            value = branding.name
        case "description":
            value = branding.description
        case "absolute-url":
            value = f"{base}{current}" if base and current.startswith("/") else current
        case "page-url":
            if base is None:
                return ""
            value = f"{base}{path}"
    attrs = [(k, value if k == "content" else v) for k, v in tag.attrs]
    if all(k != "content" for k, _ in attrs):
        attrs.append(("content", value))
    parts = [
        tag.name,
        *(k if v is None else f'{k}="{html.escape(v)}"' for k, v in attrs),
    ]
    return f"<{' '.join(parts)}{' /' if tag.self_closing else ''}>"
