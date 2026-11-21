from typing import TYPE_CHECKING, Any

from pydantic import BaseModel, ConfigDict, Field

from app.modules.transfer.domain.bundle import NameLookup
from app.modules.transfer.domain.entity_kind import EntityKind
from app.modules.transfer.domain.tabular import (
    ColumnMapping,
    ConnectionColumn,
    ConnectionEnd,
    CsvEncoding,
    DayMonthOrder,
    ExtraField,
    ExtraFieldKind,
)
from app.platform.request_model import RequestModel

if TYPE_CHECKING:
    from app.modules.transfer.application.item_import import ItemImportInspection
    from app.modules.transfer.application.pipeline import AppliedBundle

INSPECT_EXAMPLE: dict[str, Any] = {
    "headers": ["title", "signed_on", "authenticated"],
    "sample_rows": [
        {"title": "Alien #1", "signed_on": "2019-08", "authenticated": "yes"}
    ],
    "row_count": 1204,
    "fields": [
        {
            "key": "signed_on",
            "title": "Signed on",
            "kind": "partialdate",
            "options": None,
            "multiple": False,
            "importable": True,
            "reason": None,
        }
    ],
    "suggested_mapping": [
        {"column": "title", "target": "name"},
        {"column": "signed_on", "target": "signed_on"},
        {"column": "authenticated", "target": None},
    ],
    "encoding": "utf_8",
    "day_month_order": None,
    "day_month_order_certain": False,
    "column_kinds": {
        "title": "text",
        "signed_on": "partialdate",
        "authenticated": "boolean",
    },
}


class ExtraFieldEntry(RequestModel):
    """A field each imported item gets for itself, filled from the column."""

    model_config = ConfigDict(
        extra="forbid",
        json_schema_extra={
            "examples": [{"key": "paper", "title": "Paper", "kind": "choice"}]
        },
    )

    key: str = Field(
        description="The field's key: lowercase letters, digits and `_`, not one the "
        + "item type has.",
        max_length=64,
    )
    title: str = Field(
        description="The field's name, as people see it.", max_length=200
    )
    kind: ExtraFieldKind = Field(
        description="What sort of value it holds. A `choice` offers each different "
        + "value in the column, up to 50."
    )


class ColumnMappingEntry(RequestModel):
    """Where one column of the file goes."""

    model_config = ConfigDict(
        extra="forbid",
        json_schema_extra={
            "examples": [{"column": "signed_on", "target": "signed_on"}]
        },
    )

    column: str = Field(description="The column's name in the file's header row.")
    target: str | None = Field(
        default=None,
        description="`name`, `description`, `tags`, a field's key, or null to ignore "
        + "the column.",
    )
    extra: ExtraFieldEntry | None = Field(
        default=None,
        description="Keep the column as each item's own field instead; `target` must "
        + "then be null. An item gets the field only when its cell has a value.",
    )

    def to_domain(self) -> ColumnMapping:
        """The mapping entry the import reads."""
        extra = self.extra
        return ColumnMapping(
            column=self.column,
            target=self.target,
            extra=None
            if extra is None
            else ExtraField(key=extra.key, title=extra.title, kind=extra.kind),
        )


class ConnectionColumnEntry(RequestModel):
    """A column naming, on each row, another item the row's item connects to."""

    model_config = ConfigDict(
        extra="forbid",
        json_schema_extra={
            "examples": [
                {
                    "column": "signer",
                    "relationship_type": "signed",
                    "item_type": "person",
                    "row_end": "target",
                    "on_missing": "create",
                }
            ]
        },
    )

    column: str = Field(description="The column's name in the file's header row.")
    relationship_type: str = Field(
        description="The slug of the relationship type that joins them."
    )
    item_type: str = Field(
        description="The slug of the other item's type. Its name is looked up "
        + "within this type, ignoring case and spacing."
    )
    row_end: ConnectionEnd = Field(
        description="Which end of the connection the row's own item is."
    )
    on_missing: NameLookup = Field(
        default=NameLookup.CREATE,
        description="What to do when you have no item of that name: `create` one "
        + "with just the name, or `skip` the connection.",
    )

    def to_domain(self) -> ConnectionColumn:
        """The connection column the import reads."""
        return ConnectionColumn(
            column=self.column,
            relationship_type=self.relationship_type,
            item_type=self.item_type,
            row_end=self.row_end,
            on_missing=self.on_missing,
        )


class ItemImportFieldResponse(BaseModel):
    """One field of the item type, as an import can fill it."""

    model_config = ConfigDict(
        json_schema_extra={"examples": [INSPECT_EXAMPLE["fields"][0]]}
    )

    key: str = Field(description="The field's key, used as a mapping target.")
    title: str = Field(description="The field's name, as people see it.")
    kind: str | None = Field(
        default=None, description="What sort of value it holds, such as `date`."
    )
    options: list[str] | None = Field(
        default=None, description="The choices it allows, for a choice field."
    )
    multiple: bool = Field(description="Whether a cell may hold several choices.")
    importable: bool = Field(description="Whether an import can fill it yet.")
    reason: str | None = Field(
        default=None, description="Why it cannot be filled, if it cannot."
    )


class ItemImportInspectionResponse(BaseModel):
    """What is in a CSV file, the item type's fields, and a mapping to start from."""

    model_config = ConfigDict(json_schema_extra={"examples": [INSPECT_EXAMPLE]})

    headers: list[str] = Field(description="The file's column names, in order.")
    sample_rows: list[dict[str, str]] = Field(
        description="The first few rows as written, each keyed by column name."
    )
    row_count: int = Field(description="How many rows the file has.")
    fields: list[ItemImportFieldResponse] = Field(description="The item type's fields.")
    suggested_mapping: list[ColumnMappingEntry] = Field(
        description="A first guess, matching each column to a field by name."
    )
    encoding: CsvEncoding = Field(description="What the file was read as.")
    day_month_order: DayMonthOrder | None = Field(
        default=None,
        description="Which number of a date written as `03/04/2019` is the day, "
        + "suggested from the values; null when no value is written that way.",
    )
    day_month_order_certain: bool = Field(
        description="Whether the values prove the suggested order, or it is a guess."
    )
    column_kinds: dict[str, ExtraFieldKind] = Field(
        default_factory=dict,
        description="For each column, the kind its values suggest should it be kept "
        + "as an extra field: the first of number, yes/no, date and partial date "
        + "that takes every value, else text.",
    )

    @classmethod
    def from_domain(cls, found: ItemImportInspection) -> ItemImportInspectionResponse:
        """Build from what inspecting the file found."""
        guess = found.day_month_order
        return cls(
            headers=list(found.headers),
            sample_rows=[
                dict(zip(found.headers, row, strict=True)) for row in found.sample_rows
            ],
            row_count=found.row_count,
            fields=[
                ItemImportFieldResponse(
                    key=f.key,
                    title=f.title,
                    kind=f.kind,
                    options=None if f.options is None else list(f.options),
                    multiple=f.multiple,
                    importable=f.importable,
                    reason=f.reason,
                )
                for f in found.fields
            ],
            suggested_mapping=[
                ColumnMappingEntry(column=m.column, target=m.target)
                for m in found.suggested_mapping
            ],
            encoding=found.encoding,
            day_month_order=guess.order if guess else None,
            day_month_order_certain=guess.certain if guess else False,
            column_kinds={c.column: c.kind for c in found.column_kinds},
        )


class ItemImportResultResponse(BaseModel):
    """What running an import created."""

    model_config = ConfigDict(
        json_schema_extra={
            "examples": [{"items_added": 1204, "connections_added": 980}]
        }
    )

    items_added: int = Field(
        description="How many items were added: the rows, and the items their "
        + "connection columns named that you did not have."
    )
    connections_added: int = Field(description="How many connections were added.")

    @classmethod
    def from_domain(cls, applied: AppliedBundle) -> ItemImportResultResponse:
        """Build from what applying the import did."""
        return cls(
            items_added=applied.created.get(EntityKind.ITEM, 0),
            connections_added=applied.created.get(EntityKind.CONNECTION, 0),
        )
