from typing import TYPE_CHECKING, Protocol

if TYPE_CHECKING:
    from collections.abc import Sequence

    from app.modules.transfer.domain.entity_kind import EntityKind
    from app.modules.transfer.domain.source_link import SourceLink
    from app.shared_kernel.content_filter import ContentFilter


class SourceLinkRepository(Protocol):
    """Access to source links, independent of storage backend."""

    async def add(self, link: SourceLink) -> None:
        """Add a new link."""
        ...

    async def save(self, link: SourceLink) -> None:
        """Persist changes to an existing link."""
        ...

    async def get_by_key(
        self, source: str, kind: EntityKind, key: str, *, scope: ContentFilter
    ) -> SourceLink | None:
        """Return the link for `key` of `kind` in `source`, or `None`."""
        ...

    async def list_by_keys(
        self,
        source: str,
        kind: EntityKind,
        keys: Sequence[str],
        *,
        scope: ContentFilter,
    ) -> list[SourceLink]:
        """Return the links for those of `keys` that have one, in one query."""
        ...

    async def list_for_source(
        self, source: str, *, scope: ContentFilter
    ) -> list[SourceLink]:
        """Return every link of `source`, of every kind."""
        ...
