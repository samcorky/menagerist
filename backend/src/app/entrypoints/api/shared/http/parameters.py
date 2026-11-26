"""Shared declarations for the path and query parameters that recur across routes.

Each alias carries the parameter's OpenAPI description, so a route declares
`node_id: NodeId` instead of repeating it. Bounds stay with the route that
needs them: `PageLimit` describes `limit` without capping it, and a route with
a cap writes its own `Query(ge=..., le=..., description=PAGE_LIMIT_DESCRIPTION)`.
A route that pages declares `PageParams` or `SearchPageParams` instead.
"""

import uuid
from enum import StrEnum
from typing import Annotated

from fastapi import Header, Path, Query
from pydantic import BaseModel, Field

from app.shared_kernel.paging import SortOrder

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
    "What to order the rows by. Leave it out to order by id, which is creation order."
    + " Ties keep a fixed order."
)
PAGE_ORDER_DESCRIPTION = (
    "`asc` (the default) or `desc`. It applies to `sort`, or to id when `sort` is"
    + " left out, so `desc` alone lists the newest first."
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

    after: str | None = Field(None, max_length=512, description=PAGE_CURSOR_DESCRIPTION)
    limit: int = Field(50, ge=1, le=100, description=PAGE_LIMIT_DESCRIPTION)
    sort: Sort | None = Field(None, description=PAGE_SORT_DESCRIPTION)
    order: SortOrder = Field(SortOrder.ASC, description=PAGE_ORDER_DESCRIPTION)


class SearchPageParams[Sort: StrEnum](PageParams[Sort]):
    """`PageParams` for a list with text to search, which adds `q`."""

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
