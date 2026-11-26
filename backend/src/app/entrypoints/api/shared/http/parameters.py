"""Shared declarations for the path and query parameters that recur across routes.

Each alias carries the parameter's OpenAPI description, so a route declares
`node_id: NodeId` instead of repeating it. Bounds stay with the route that
needs them: `PageLimit` describes `limit` without capping it, and a route with
a cap writes its own `Query(ge=..., le=..., description=PAGE_LIMIT_DESCRIPTION)`.
A route that pages declares `PageParams` or `SearchPageParams` instead.
"""

import uuid
from enum import StrEnum
from typing import Annotated, ClassVar

from fastapi import Header, Path, Query
from pydantic import BaseModel, Field, model_validator

from app.shared_kernel.paging import (
    MAX_SORT_KEYS,
    Cursor,
    SortBy,
    SortOrder,
    decode_cursor,
)

PAGE_AFTER_DESCRIPTION = (
    "Id of the last row of the previous page. Leave it out for the first page;"
    + " the `Link` header of each page carries the next one."
)
PAGE_CURSOR_DESCRIPTION = (
    "Where the previous page ended. Leave it out for the first page; the `Link` header"
    + " of each page carries the next one. Pass it back unchanged, with the same"
    + " `sort` and `order`."
)
PAGE_LIMIT_DESCRIPTION = "Most rows to return on this page."

PAGE_SORT_DESCRIPTION = (
    "What to order the rows by. Repeat it for a second and third key, which break"
    + " ties in the first. Leave it out to order by id, which is creation order."
    + " Ties keep a fixed order."
)
PAGE_ORDER_DESCRIPTION = (
    "`asc` (the default) or `desc`. Repeat it to give each `sort` its own direction,"
    + " in the same order; a key with none is `asc`. With no `sort` it applies to id,"
    + " so `desc` alone lists the newest first."
)
PAGE_NEWEST_FIRST_ORDER_DESCRIPTION = (
    "`desc` (the default) lists the newest first; `asc` the oldest. Repeat it to give"
    + " each `sort` its own direction, in the same order; a key with none is `desc`."
)
PAGE_SEARCH_DESCRIPTION = (
    "Keep the rows whose text contains this, ignoring case and accents."
)


class PageParams[Sort: StrEnum](BaseModel):
    """The paging parameters every list route shares, as one query model.

    A route declares `page: Annotated[PageParams[ItsSort], Query()]`, where
    `ItsSort` is the enum of the keys it can sort by. FastAPI flattens the fields
    into separate query parameters, so the schema reads as if each were declared on
    the route. A route with a different cap subclasses it and overrides `limit`.
    """

    # The direction of a key that `order` leaves out.
    default_order: ClassVar[SortOrder] = SortOrder.ASC

    after: str | None = Field(None, max_length=512, description=PAGE_CURSOR_DESCRIPTION)
    limit: int = Field(50, ge=1, le=100, description=PAGE_LIMIT_DESCRIPTION)
    sort: list[Sort] = Field(
        default_factory=list,
        max_length=MAX_SORT_KEYS,
        description=PAGE_SORT_DESCRIPTION,
    )
    order: list[SortOrder] = Field(
        default_factory=list,
        max_length=MAX_SORT_KEYS,
        description=PAGE_ORDER_DESCRIPTION,
    )

    @model_validator(mode="after")
    def _keys_and_directions_agree(self) -> PageParams[Sort]:
        if len(set(self.sort)) != len(self.sort):
            raise ValueError("`sort` names a key twice")
        if len(self.order) > max(len(self.sort), 1):
            raise ValueError("`order` has more directions than `sort` has keys")
        return self

    @property
    def first_sort(self) -> Sort | None:
        """The key the rows are ordered by first, or None for the default order."""
        return self.sort[0] if self.sort else None

    @property
    def first_order(self) -> SortOrder:
        """The direction of the first key, or of the id when there is no key."""
        return self.order[0] if self.order else self.default_order

    @property
    def then_by(self) -> tuple[SortBy[Sort], ...]:
        """The keys after the first, each in its direction."""
        return tuple(
            SortBy(
                key=key,
                order=self.order[n] if n < len(self.order) else self.default_order,
            )
            for n, key in enumerate(self.sort)
            if n > 0
        )

    @property
    def cursor(self) -> Cursor | None:
        """`after` read as a cursor, or None for the first page.

        Raises:
            InvalidCursorError: `after` is not a cursor.
        """
        return None if self.after is None else decode_cursor(self.after)


class NewestFirstPageParams[Sort: StrEnum](PageParams[Sort]):
    """`PageParams` for a list that runs newest first: `order` defaults to `desc`.

    A route says which key is "newest" (the deletion time, the creation time) by the
    default sort it gives its use case or `page_of`.
    """

    default_order: ClassVar[SortOrder] = SortOrder.DESC

    order: list[SortOrder] = Field(
        default_factory=list,
        max_length=MAX_SORT_KEYS,
        description=PAGE_NEWEST_FIRST_ORDER_DESCRIPTION,
    )


class SearchPageParams[Sort: StrEnum](PageParams[Sort]):
    """`PageParams` for a list with text to search, which adds `q`."""

    q: str | None = Field(None, max_length=200, description=PAGE_SEARCH_DESCRIPTION)


class NewestFirstSearchPageParams[Sort: StrEnum](NewestFirstPageParams[Sort]):
    """`NewestFirstPageParams` for a list with text to search, which adds `q`."""

    q: str | None = Field(None, max_length=200, description=PAGE_SEARCH_DESCRIPTION)


PageAfter = Annotated[uuid.UUID | None, Query(description=PAGE_AFTER_DESCRIPTION)]
PageLimit = Annotated[int, Query(description=PAGE_LIMIT_DESCRIPTION)]

NodeId = Annotated[uuid.UUID, Path(description="The item's id.")]
EdgeId = Annotated[uuid.UUID, Path(description="The connection's id.")]
NodeTypeId = Annotated[uuid.UUID, Path(description="The item type's id.")]
EdgeTypeId = Annotated[uuid.UUID, Path(description="The connection type's id.")]
AssetId = Annotated[uuid.UUID, Path(description="The media asset's id.")]
PresetId = Annotated[uuid.UUID, Path(description="The saved field's id.")]
BackupId = Annotated[uuid.UUID, Path(description="The backup's id.")]
ExportId = Annotated[uuid.UUID, Path(description="The export's id.")]
ImportFileId = Annotated[uuid.UUID, Path(description="The uploaded file's id.")]
UserId = Annotated[uuid.UUID, Path(description="The user's id.")]
SessionId = Annotated[uuid.UUID, Path(description="The session's id.")]
TokenId = Annotated[uuid.UUID, Path(description="The API token's id.")]

FieldKey = Annotated[str, Path(description="The field's key in the item details.")]
SubFieldKey = Annotated[
    str | None,
    Query(
        description=(
            "A column of the table field named by `key`. When given, the"
            + " operation applies to that column in each row, not the whole field."
        )
    ),
]

# Only the ETag forms are declared; `ConditionalRequest` also honours the date forms,
# left out so the contract steers clients to ETags.
IfNoneMatch = Annotated[
    str | None,
    Header(
        alias="If-None-Match",
        description="An ETag from an earlier response; 304 if it still matches.",
    ),
]
IfMatch = Annotated[
    str | None,
    Header(
        alias="If-Match",
        description="The ETag you last read; 412 if the resource has changed.",
    ),
]
