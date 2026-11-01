from typing import TYPE_CHECKING

from app.modules.backup.domain.errors import CorruptBackupError

if TYPE_CHECKING:
    from collections.abc import Mapping


class InMemoryUserImportValidator:
    """Record imported rows and optionally reject selected tables in tests."""

    def __init__(self, *, rejected_table: str | None = None) -> None:
        self.rows: list[tuple[str, dict[str, object]]] = []
        self.rejected_table = rejected_table

    async def validate(self, table: str, row: Mapping[str, object]) -> None:
        """Expose validation calls and simulate a domain validation failure."""
        if table == self.rejected_table:
            raise CorruptBackupError("The imported row violates domain invariants.")
        self.rows.append((table, dict(row)))
