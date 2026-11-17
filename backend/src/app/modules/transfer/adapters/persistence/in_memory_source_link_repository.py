from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import uuid
    from collections.abc import Sequence

    from app.modules.transfer.domain.entity_kind import EntityKind
    from app.modules.transfer.domain.source_link import SourceLink
    from app.shared_kernel.content_filter import ContentFilter


class InMemorySourceLinkRepository:
    """Dict-backed `SourceLinkRepository` for tests."""

    def __init__(self) -> None:
        self._links: dict[uuid.UUID, SourceLink] = {}

    async def add(self, link: SourceLink) -> None:
        """Add a new link."""
        self._links[link.id] = link

    async def save(self, link: SourceLink) -> None:
        """Persist changes to an existing link."""
        self._links[link.id] = link

    async def get_by_key(
        self, source: str, kind: EntityKind, key: str, *, scope: ContentFilter
    ) -> SourceLink | None:
        """Return the link for `key` of `kind` in `source`, or `None`."""
        return next(
            (
                link
                for link in self._links.values()
                if (link.source, link.kind, link.key) == (source, kind, key)
                and scope.covers(link.owner_id)
            ),
            None,
        )

    async def list_by_keys(
        self,
        source: str,
        kind: EntityKind,
        keys: Sequence[str],
        *,
        scope: ContentFilter,
    ) -> list[SourceLink]:
        """Return the links for those of `keys` that have one."""
        wanted = set(keys)
        return [
            link
            for link in self._links.values()
            if link.source == source
            and link.kind is kind
            and link.key in wanted
            and scope.covers(link.owner_id)
        ]

    async def list_for_source(
        self, source: str, *, scope: ContentFilter
    ) -> list[SourceLink]:
        """Return every link of `source`, of every kind."""
        return [
            link
            for link in self._links.values()
            if link.source == source and scope.covers(link.owner_id)
        ]
