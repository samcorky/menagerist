"""What importing a spreadsheet needs to know: limits, fields, mappings, problems."""

from dataclasses import dataclass

MAX_IMPORT_BYTES = 10 * 1024 * 1024
MAX_IMPORT_ROWS = 5000
# Problems a preview lists by name; the rest are counted.
MAX_LISTED_PROBLEMS = 20


@dataclass(kw_only=True, frozen=True, eq=False)
class FieldSpec:
    """One field of an item type, as an import needs to fill it.

    `json_type` is the schema's `type` and `kind` the field's kind (such as
    `partialdate`). `options` are the allowed choices, and `multiple` is set when a
    cell may hold several of them. A field the import cannot fill is not
    `importable`, and `reason` says why.
    """

    key: str
    title: str
    json_type: str | None
    kind: str | None
    options: tuple[str, ...] | None
    multiple: bool = False
    importable: bool = True
    reason: str | None = None


@dataclass(kw_only=True, frozen=True)
class ColumnMapping:
    """Where one column of the file goes.

    `target` is `name`, `description`, `tags`, a field key, or `None` to ignore it.
    """

    column: str
    target: str | None


@dataclass(kw_only=True, frozen=True)
class CellProblem:
    """A value in the file that cannot be imported, by spreadsheet row and field."""

    row: int
    field: str
    message: str
