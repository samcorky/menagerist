"""The rules that keep a type's parent to one level, free of clashing fields.

A type may be a subtype of one top-level type. The parent is named by slug, so these
checks need the other types and live here rather than in the domain.
"""

from dataclasses import replace
from typing import TYPE_CHECKING, Any

from app.modules.graph.application.choice_lists import resolve_choice_lists
from app.modules.graph.application.schema_meta import effective_schema
from app.modules.graph.domain.errors import (
    InvalidParentTypeError,
    NodeTypeHasSubtypesError,
)

if TYPE_CHECKING:
    from app.modules.graph.domain.node_type import NodeType
    from app.modules.graph.ports.choice_list_source import ChoiceListSource
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
) -> NodeType:
    """Return the parent type, or raise `InvalidParentTypeError`.

    `slug` may be a subtype of `parent` only if the parent exists and is top-level,
    the type itself has no subtypes, and its fields (`schema`) do not reuse a key the
    parent defines.
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
    return parent_type


async def type_view(
    repos: GraphRepos,
    node_type: NodeType,
    *,
    scope: ContentFilter,
    choice_lists: ChoiceListSource | None,
) -> NodeType:
    """`node_type` as the API shows it.

    Linked choice-list options are filled in both in what the type defines and in what
    it uses, and the effective schema and the parent's last change are reported.
    """
    inherited = await with_inherited(repos, node_type, scope=scope)
    own = await resolve_choice_lists(inherited.attributes_schema, choice_lists)
    used = await resolve_choice_lists(inherited.effective_schema, choice_lists)
    if own is inherited.attributes_schema and used is inherited.effective_schema:
        return inherited
    return replace(inherited, attributes_schema=own, effective_schema=used)


def parent_properties(parent: NodeType | None) -> dict[str, Any] | None:
    """The fields a parent type defines, for a subtype's own checks."""
    properties = (parent.attributes_schema or {}).get("properties") if parent else None
    return properties if isinstance(properties, dict) else None


async def _parent_of(
    repos: GraphRepos, node_type: NodeType, scope: ContentFilter
) -> NodeType | None:
    if node_type.parent is None:
        return None
    return await repos.node_types.get_by_slug(node_type.parent, scope=scope)


async def resolve_effective_schema(
    repos: GraphRepos, node_type: NodeType, *, scope: ContentFilter
) -> dict[str, Any] | None:
    """The fields an item of `node_type` is checked against and shown with."""
    parent = await _parent_of(repos, node_type, scope)
    return effective_schema(
        parent.attributes_schema if parent else None, node_type.attributes_schema
    )


async def with_inherited(
    repos: GraphRepos, node_type: NodeType, *, scope: ContentFilter
) -> NodeType:
    """`node_type` reporting its effective schema and its parent's last change.

    A type with no parent inherits nothing, so it comes back as it is and the API
    answers with its own schema. A subtype comes back as a copy carrying them.
    """
    if node_type.parent is None:
        return node_type
    parent = await _parent_of(repos, node_type, scope)
    return replace(
        node_type,
        effective_schema=effective_schema(
            parent.attributes_schema if parent else None, node_type.attributes_schema
        ),
        parent_updated_at=parent.updated_at if parent else None,
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
