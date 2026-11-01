from typing import TYPE_CHECKING, Any, Protocol

if TYPE_CHECKING:
    import uuid
    from collections.abc import Mapping

    from app.modules.collections.domain.definition_warning import DefinitionWarning
    from app.shared_kernel.content_filter import ContentFilter


class DefinitionChecker(Protocol):
    """Judges a smart collection's definition, which another module understands."""

    async def check(
        self,
        definition: Mapping[str, Any],
        scope: ContentFilter,
        *,
        self_id: uuid.UUID | None = None,
    ) -> list[DefinitionWarning]:
        """Return warnings for parts of `definition` that no longer apply.

        `self_id` is the collection being updated, so a definition that refers
        back to it can be refused.

        Raises:
            InvalidDefinitionError: With the path of the first bad condition, if
                the definition is malformed.
        """
        ...
