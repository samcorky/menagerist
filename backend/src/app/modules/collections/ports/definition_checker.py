from typing import TYPE_CHECKING, Any, Protocol

if TYPE_CHECKING:
    from collections.abc import Mapping

    from app.modules.collections.domain.definition_warning import DefinitionWarning
    from app.shared_kernel.access_scope import AccessScope


class DefinitionChecker(Protocol):
    """Judges a smart collection's definition, which another module understands."""

    async def check(
        self, definition: Mapping[str, Any], scope: AccessScope
    ) -> list[DefinitionWarning]:
        """Return warnings for parts of `definition` that no longer apply.

        Raises:
            InvalidDefinitionError: With the path of the first bad condition, if
                the definition is malformed.
        """
        ...
