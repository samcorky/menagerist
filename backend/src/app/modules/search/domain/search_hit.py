"""What a search finds, and how well each find matches."""

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any

from app.shared_kernel.text import fold


class SearchKind(StrEnum):
    """The kinds of thing the search can find, in the order ties are shown."""

    ITEM = "item"
    COLLECTION = "collection"
    ITEM_TYPE = "item_type"
    SETTING = "setting"
    SCHEDULED_TASK = "scheduled_task"


# How well a hit matches, best first. A description never beats a title.
EXACT = 100
PREFIX = 80
WORD_PREFIX = 60
CONTAINS = 40
DESCRIPTION = 20
ELSEWHERE = 10
# Added to an item in the collection being viewed, so it beats the same match elsewhere.
IN_COLLECTION_BONUS = 5


def _words(text: str) -> list[str]:
    return "".join(c if c.isalnum() else " " for c in text).split()


def score(query: str, title: str, description: str | None = None) -> int:
    """Rate how well `title` and `description` match `query`; 0 means no match.

    Matching ignores case and accents. Anything other than the title and the
    description (an item's field values, say) is not scored here: a source that
    matched on it reports `ELSEWHERE` itself.
    """
    needle = fold(query.strip())
    if not needle:
        return 0
    folded = fold(title)
    if folded == needle:
        return EXACT
    if folded.startswith(needle):
        return PREFIX
    if any(word.startswith(needle) for word in _words(folded)):
        return WORD_PREFIX
    if needle in folded:
        return CONTAINS
    if description and needle in fold(description):
        return DESCRIPTION
    return 0


@dataclass(frozen=True, kw_only=True)
class SearchHit:
    """One thing found, with enough to show it and to open it.

    `ref` is what the owner calls it: an id for items and collections, a slug
    for item types, a key for settings and scheduled tasks.
    """

    kind: SearchKind
    ref: str
    title: str
    description: str | None = None
    # Where it lives or what it is: an item's type slug, a setting's group.
    group: str | None = None
    # A collection's address segment and live item count.
    slug: str | None = None
    item_count: int | None = None
    # An item's field values, which the client uses to say why it matched.
    attributes: dict[str, Any] | None = field(default=None, hash=False)
    # An item that belongs to the collection the search was asked about.
    in_collection: bool = False
    score: int = 0

    def rated(self, value: int) -> SearchHit:
        """Return this hit with its score set."""
        return SearchHit(
            kind=self.kind,
            ref=self.ref,
            title=self.title,
            description=self.description,
            group=self.group,
            slug=self.slug,
            item_count=self.item_count,
            attributes=self.attributes,
            in_collection=self.in_collection,
            score=value,
        )


@dataclass(frozen=True, kw_only=True)
class SearchOutcome:
    """Ranked hits, and the kinds whose source could not answer."""

    hits: list[SearchHit]
    failed: list[SearchKind]
