from typing import TYPE_CHECKING, Any

from app.modules.collections.domain.errors import InvalidDefinitionError

if TYPE_CHECKING:
    import uuid
    from collections.abc import Mapping

    from app.modules.collections.domain.definition_warning import DefinitionWarning
    from app.shared_kernel.content_filter import ContentFilter


class InMemoryDefinitionChecker:
    """`DefinitionChecker` for tests.

    It only requires `where` to be absent or an object, and returns whatever is
    set in `warnings`. It does not understand conditions.
    """

    def __init__(self, warnings: list[DefinitionWarning] | None = None) -> None:
        self.warnings: list[DefinitionWarning] = list(warnings or ())

    async def check(
        self,
        definition: Mapping[str, Any],
        scope: ContentFilter,
        *,
        self_id: uuid.UUID | None = None,
    ) -> list[DefinitionWarning]:
        """Return the configured warnings, or raise if `where` is not an object."""
        where = definition.get("where")
        if where is not None and not isinstance(where, dict):
            raise InvalidDefinitionError("Expected an object.", path="where")
        return list(self.warnings)
