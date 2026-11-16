"""Shared declarations for the path and query parameters that recur across routes.

Each alias carries the parameter's OpenAPI description, so a route declares
`node_id: NodeId` instead of repeating it. Bounds stay with the route that
needs them: `PageLimit` describes `limit` without capping it, and a route with
a cap writes its own `Query(ge=..., le=..., description=PAGE_LIMIT_DESCRIPTION)`.
"""

import uuid
from typing import Annotated

from fastapi import Header, Path, Query

PAGE_AFTER_DESCRIPTION = (
    "Id of the last row of the previous page. Leave it out for the first page;"
    + " the `Link` header of each page carries the next one."
)
PAGE_LIMIT_DESCRIPTION = "Most rows to return on this page."

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
