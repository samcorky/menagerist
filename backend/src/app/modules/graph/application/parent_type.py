"""The rules that keep a type's parent to one level, free of clashing fields.

A type may be a subtype of one top-level type. The parent is named by slug, so these
checks need the other types and live here rather than in the domain.
"""

from typing import TYPE_CHECKING, Any

from app.modules.graph.domain.errors import (
    InvalidParentTypeError,
    NodeTypeHasSubtypesError,
)

if TYPE_CHECKING:
    from app.modules.graph.domain.node_type import NodeType
    from app.modules.graph.ports.unit_of_work import GraphRepos
    from app.shared_kernel.content_filter import ContentFilter


def field_keys(schema: dict[str, Any] | None) -> set[str]:
    """The keys of the fields a type's schema defines."""
    properties = (schema or {}).get("properties")
    return set(properties) if isinstance(properties, dict) else set()


def _names(keys: set[str]) -> str:
    return ", ".join(sorted(keys))


async def check_can_be_subtype(
    repos: GraphRepos,
    *,
    slug: str,
    schema: dict[str, Any] | None,
    parent: str,
    scope: ContentFilter,
) -> None:
    """Raise `InvalidParentTypeError` unless `slug` may be a subtype of `parent`.

    The parent must exist and be top-level, the type must not itself have subtypes,
    and its fields (`schema`) must not reuse a key the parent defines.
    """
    if parent == slug:
        raise InvalidParentTypeError("a type cannot be its own parent")
    parent_type = await repos.node_types.get_by_slug(parent, scope=scope)
    if parent_type is None:
        raise InvalidParentTypeError(f"Parent type '{parent}' not found")
    if parent_type.parent is not None:
        raise InvalidParentTypeError(
            f"'{parent}' is a subtype of '{parent_type.parent}'; "
            + "only one level of parent types is supported"
        )
    if await repos.node_types.list_subtypes(slug, scope=scope):
        raise InvalidParentTypeError(
            f"'{slug}' has subtypes, so it cannot be a subtype itself"
        )
    clash = field_keys(schema) & field_keys(parent_type.attributes_schema)
    if clash:
        raise InvalidParentTypeError(
            f"'{slug}' has fields its parent type '{parent}' already has: "
            + _names(clash)
        )


async def check_subtypes_keep_their_keys(
    repos: GraphRepos,
    *,
    parent: NodeType,
    schema: dict[str, Any] | None,
    scope: ContentFilter,
) -> None:
    """Raise `InvalidParentTypeError` if a new `schema` reuses a subtype's key."""
    keys = field_keys(schema)
    for subtype in await repos.node_types.list_subtypes(str(parent.slug), scope=scope):
        clash = keys & field_keys(subtype.attributes_schema)
        if clash:
            raise InvalidParentTypeError(
                f"Its subtype '{subtype.slug}' already has fields: {_names(clash)}"
            )


async def check_has_no_subtypes(
    repos: GraphRepos, node_type: NodeType, *, scope: ContentFilter
) -> None:
    """Raise `NodeTypeHasSubtypesError` naming the subtypes, if there are any."""
    subtypes = await repos.node_types.list_subtypes(str(node_type.slug), scope=scope)
    if subtypes:
        names = ", ".join(str(s.slug) for s in subtypes)
        raise NodeTypeHasSubtypesError(
            f"Item type '{node_type.slug}' still has subtypes: {names}"
        )
