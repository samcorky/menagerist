"""The rules that keep a type's parent to one level, free of clashing fields.

A type may be a subtype of one top-level type. The parent is named by slug, so these
checks need the other types and live here rather than in the domain.
"""

from dataclasses import dataclass, replace
from typing import TYPE_CHECKING, Any

from app.modules.graph.application.choice_lists import resolve_choice_lists
from app.modules.graph.application.parent_change import plan_parent_change
from app.modules.graph.application.schema_meta import check_meta_shape, effective_schema
from app.modules.graph.domain.errors import (
    InvalidParentTypeError,
    NodeTypeHasSubtypesError,
)
from app.modules.graph.domain.node_type import NodeType
from app.shared_kernel.slug import slugify

if TYPE_CHECKING:
    from app.modules.graph.application.parent_change import ParentChange
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
    check_keys: bool = True,
) -> NodeType:
    """Return the parent type, or raise `InvalidParentTypeError`.

    `slug` may be a subtype of `parent` only if the parent exists and is top-level,
    the type itself has no subtypes, and its fields (`schema`) do not reuse a key the
    parent defines. A change that may merge such keys passes `check_keys=False` and
    deals with them itself.
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
    if check_keys and clash:
        raise InvalidParentTypeError(
            f"'{slug}' has fields its parent type '{parent}' already has: "
            + _names(clash)
        )
    return parent_type


@dataclass(frozen=True, eq=False)
class TypeUpdatePlan:
    """What updating a type's schema and parent comes to, before anything is saved.

    `schema` is what the type's own schema becomes (`None` leaves it). When the new
    parent's choices were widened by a merge, `parent_type` is that parent and
    `parent_schema` its new schema; otherwise both are `None`.
    """

    schema: dict[str, Any] | None
    parent_type: NodeType | None = None
    parent_schema: dict[str, Any] | None = None


def blocked_message(
    slug: str, parent: str, keys: tuple[str, ...], change: ParentChange
) -> str:
    """Why a parent change cannot be made, naming the fields in the way."""
    names = _names(set(keys))
    if change.on_clash == "merge":
        return (
            f"'{slug}' has fields its parent type '{parent}' has as a different kind "
            + f"of field: {names}. Change one to match first."
        )
    return f"'{slug}' has fields its parent type '{parent}' already has: {names}"


async def plan_type_update(
    repos: GraphRepos,
    node_type: NodeType,
    *,
    parent: str | None,
    clear_parent: bool,
    new_schema: dict[str, Any] | None,
    change: ParentChange,
    scope: ContentFilter,
) -> TypeUpdatePlan:
    """Check an update of a type's schema and parent, and work out what it changes.

    A new schema is also checked for its highlights, which may name a field the
    type inherits. Nothing is changed here, so a refused update leaves every type
    as it was. Moving to another parent (or none) goes through `plan_parent_change`,
    so a clash is merged or refused as asked and the fields a type loses are kept or
    archived.

    Raises:
        InvalidParentTypeError: When the parent cannot be used or a clash blocks.
    """
    slug = str(node_type.slug)
    target = slugify(parent) if parent is not None else None
    if target is None and not clear_parent:
        target = node_type.parent
    own = new_schema if new_schema is not None else node_type.attributes_schema

    if target == node_type.parent:
        inherited = None
        if target is not None and new_schema is not None:
            parent_type = await check_can_be_subtype(
                repos, slug=slug, schema=own, parent=target, scope=scope
            )
            inherited = parent_properties(parent_type)
        if new_schema is not None:
            check_meta_shape(new_schema, inherited=inherited)
            await check_subtypes_keep_their_keys(
                repos, parent=node_type, schema=new_schema, scope=scope
            )
        return TypeUpdatePlan(schema=new_schema)

    old = await parent_of(repos, node_type, scope)
    new = (
        await check_can_be_subtype(
            repos, slug=slug, schema=own, parent=target, scope=scope, check_keys=False
        )
        if target is not None
        else None
    )
    result = plan_parent_change(
        old_slug=node_type.parent,
        old_parent=old.attributes_schema if old else None,
        new_slug=target,
        new_parent=new.attributes_schema if new else None,
        own=own,
        change=change,
    )
    if result.blocked_by and target is not None:
        raise InvalidParentTypeError(
            blocked_message(slug, target, result.blocked_by, change)
        )
    if result.own_schema is not None:
        widened = result.parent_schema or (new.attributes_schema if new else None)
        properties = (widened or {}).get("properties")
        check_meta_shape(
            result.own_schema,
            inherited=properties if isinstance(properties, dict) else None,
        )
    return TypeUpdatePlan(
        schema=result.own_schema,
        parent_type=new if result.parent_schema is not None else None,
        parent_schema=result.parent_schema,
    )


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


async def parent_of(
    repos: GraphRepos, node_type: NodeType, scope: ContentFilter
) -> NodeType | None:
    """The parent type `node_type` points at, or `None` for none or one gone."""
    if node_type.parent is None:
        return None
    return await repos.node_types.get_by_slug(node_type.parent, scope=scope)


async def resolve_effective_schema(
    repos: GraphRepos, node_type: NodeType, *, scope: ContentFilter
) -> dict[str, Any] | None:
    """The fields an item of `node_type` is checked against and shown with."""
    parent = await parent_of(repos, node_type, scope)
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
    parent = await parent_of(repos, node_type, scope)
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
