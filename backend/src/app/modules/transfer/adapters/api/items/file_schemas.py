"""Bodies and responses for CSV files uploaded once and imported by id."""

from datetime import datetime
from typing import TYPE_CHECKING, Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.entrypoints.api.shared.progress_schemas import (
    SNAPSHOT_EXAMPLE,
    ProgressSnapshotResponse,
)
from app.modules.transfer.adapters.api.items.schemas import (
    ColumnMappingEntry,
    ConnectionColumnEntry,
    ItemImportResultResponse,
)
from app.modules.transfer.domain.item_import import ImportOptions, ImportStatus
from app.modules.transfer.domain.tabular import DayMonthOrder
from app.platform.request_model import RequestModel

if TYPE_CHECKING:
    from app.modules.transfer.application.stored_imports import ItemImportView

ITEM_IMPORT_EXAMPLE: dict[str, Any] = {
    "id": "01978c3e-2b8b-7c3a-9c2e-3a2f6b9d4e40",
    "filename": "autographs.csv",
    "size": 48213,
    "status": "running",
    "ahead": None,
    "progress": SNAPSHOT_EXAMPLE,
    "result": None,
    "failure": None,
    "created_at": "2026-11-24T12:00:00Z",
    "queued_at": "2026-11-24T12:01:10Z",
    "started_at": "2026-11-24T12:01:12Z",
    "finished_at": None,
    "expires_at": "2026-11-25T12:00:00Z",
}


class InspectImportFileBody(RequestModel):
    """The item type to read an uploaded file against."""

    model_config = ConfigDict(
        extra="forbid", json_schema_extra={"examples": [{"item_type": "autograph"}]}
    )

    item_type: str = Field(description="The slug of the item type the rows become.")


class ImportOptionsBody(RequestModel):
    """How to import an uploaded file: its item type and where each column goes."""

    model_config = ConfigDict(
        extra="forbid",
        json_schema_extra={
            "examples": [
                {
                    "item_type": "autograph",
                    "mapping": [
                        {"column": "title", "target": "name"},
                        {"column": "signed_on", "target": "signed_on"},
                    ],
                    "key_field": "name",
                }
            ]
        },
    )

    item_type: str = Field(description="The slug of the item type the rows become.")
    mapping: list[ColumnMappingEntry] = Field(
        description="Where each column goes: a `target`, or `extra` to keep the "
        + "column as each item's own field."
    )
    list_separator: str = Field(
        default=",", description="What separates several choices or tags in one cell."
    )
    day_month_order: DayMonthOrder = Field(
        default=DayMonthOrder.DAY_FIRST,
        description="Which number of a date written as `03/04/2019` is the day.",
    )
    key_field: str | None = Field(
        default=None,
        description="The field or kept detail that recognises rows imported before. "
        + "Without it, every row is imported.",
    )
    restore: list[str] = Field(
        default_factory=list,
        description="Keys of rows and connections deleted after an earlier import "
        + "that are to be created again.",
    )
    connections: list[ConnectionColumnEntry] = Field(
        default_factory=list,
        description="Columns that connect each row to another item, found by its "
        + "name; at most 5.",
    )

    def to_domain(self) -> ImportOptions:
        """The options the import reads."""
        return ImportOptions(
            item_type=self.item_type,
            mapping=tuple(m.to_domain() for m in self.mapping),
            list_separator=self.list_separator,
            day_month_order=self.day_month_order,
            key_field=self.key_field,
            restore=tuple(self.restore),
            connections=tuple(c.to_domain() for c in self.connections),
        )


class ItemImportResponse(BaseModel):
    """An uploaded CSV file and what has become of its import."""

    model_config = ConfigDict(json_schema_extra={"examples": [ITEM_IMPORT_EXAMPLE]})

    id: UUID = Field(description="The uploaded file's id.")
    filename: str = Field(description="The file's name as uploaded.")
    size: int = Field(description="The file's size in bytes.")
    status: ImportStatus = Field(
        description="`uploaded` until it is imported, then `queued`, `running`, and "
        + "`succeeded` or `failed`."
    )
    ahead: int | None = Field(
        default=None,
        description="While `queued`, how many imports will run before this one; "
        + "otherwise null.",
    )
    progress: ProgressSnapshotResponse | None = Field(
        default=None, description="How far the import has got, once it has started."
    )
    result: ItemImportResultResponse | None = Field(
        default=None, description="What the import added, once it has succeeded."
    )
    failure: str | None = Field(
        default=None, description="Why the import failed, if it did."
    )
    created_at: datetime = Field(description="When the file was uploaded.")
    queued_at: datetime | None = Field(
        default=None, description="When the import was asked for."
    )
    started_at: datetime | None = Field(
        default=None, description="When the import started."
    )
    finished_at: datetime | None = Field(
        default=None, description="When the import ended."
    )
    expires_at: datetime = Field(
        description="When the file and this record are removed, if not before."
    )

    @classmethod
    def from_domain(cls, view: ItemImportView) -> ItemImportResponse:
        """Build from an import and its place in the queue."""
        item = view.item
        outcome = item.outcome
        return cls(
            id=item.id,
            filename=item.filename,
            size=item.size,
            status=item.status,
            ahead=view.ahead,
            progress=(
                None
                if item.progress is None
                else ProgressSnapshotResponse.model_validate(item.progress)
            ),
            result=(
                None
                if outcome is None
                else ItemImportResultResponse(
                    items_added=outcome.items_added,
                    connections_added=outcome.connections_added,
                )
            ),
            failure=item.failure,
            created_at=item.created_at,
            queued_at=item.queued_at,
            started_at=item.started_at,
            finished_at=item.finished_at,
            expires_at=item.expires_at,
        )
