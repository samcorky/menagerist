import uuid
from datetime import datetime
from typing import TYPE_CHECKING, Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from app.modules.graph.application.create_node_type import CreateNodeTypeCommand
from app.modules.graph.application.plan_parent_change import PlanParentChangeQuery
from app.modules.graph.application.update_node_type import UpdateNodeTypeCommand
from app.modules.graph.domain.node_type import TYPE_COLOURS
from app.platform.request_model import RequestModel

if TYPE_CHECKING:
    from app.modules.graph.application.plan_parent_change import ParentChangePlan
    from app.modules.graph.application.subtype_fields import SharedField
    from app.modules.graph.domain.node_type import NodeType

NODE_TYPE_EXAMPLE: dict[str, Any] = {
    "id": "01978c3e-2b8b-7c3a-9c2e-3a2f6b9d4e20",
    "slug": "film",
    "label": "Film",
    "description": "A motion picture.",
    "attributes_schema": None,
    "effective_schema": None,
    "icon": "clapperboard",
    "colour": "red",
    "parent": None,
    "created_at": "2026-08-23T10:14:44.465954Z",
    "updated_at": "2026-08-23T10:14:44.465954Z",
}


_ICON_DESCRIPTION = (
    "A Lucide icon name in lower-case words joined by dashes, such as `film`."
)
_COLOUR_DESCRIPTION = (
    f"One of: {', '.join(TYPE_COLOURS)}. A colour name, not a free colour, so "
    + "every client can draw it with the right contrast."
)
_ON_CLASH_DESCRIPTION = (
    "What to do when the new parent defines a field key the type does. `refuse` "
    + "(the default) stops the change; `merge` uses the parent's definition, widening "
    + "its choices to every option either lists, when both are the same kind of field."
)
_ON_DETACH_DESCRIPTION = (
    "What to do with the fields the type inherited when it loses its parent. `keep` "
    + "(the default) copies them onto the type; `drop` archives them, so values stay "
    + "and the fields can be restored."
)
_PARENT_DESCRIPTION = (
    "The slug of the top-level type this is a subtype of, such as `memorabilia`; "
    + "null for a type with no parent. A type with subtypes cannot have a parent."
)


class CreateNodeTypeRequest(RequestModel):
    """Request body for creating a node type."""

    model_config = ConfigDict(
        json_schema_extra={
            "examples": [
                {
                    "slug": "film",
                    "label": "Film",
                    "description": "A motion picture.",
                    "icon": "clapperboard",
                    "colour": "red",
                }
            ]
        }
    )

    slug: str = Field(
        description="Its short name, unique among yours; items refer to it."
    )
    label: str = Field(description="Its name, for people.")
    description: str | None = Field(description="Free text about it.", default=None)
    attributes_schema: dict[str, Any] | None = Field(
        description="Its fields, as a JSON Schema.", default=None
    )
    icon: str | None = Field(default=None, description=_ICON_DESCRIPTION)
    colour: str | None = Field(default=None, description=_COLOUR_DESCRIPTION)
    parent: str | None = Field(default=None, description=_PARENT_DESCRIPTION)

    def to_command(self) -> CreateNodeTypeCommand:
        """Convert this request into a `CreateNodeTypeCommand`."""
        return CreateNodeTypeCommand(
            slug=self.slug,
            label=self.label,
            description=self.description,
            attributes_schema=self.attributes_schema,
            icon=self.icon,
            colour=self.colour,
            parent=self.parent,
        )


class UpdateNodeTypeRequest(RequestModel):
    """Request body for updating a node type.

    `slug` is immutable. Omitted fields are left unchanged. Send `null` for
    `icon`, `colour` or `parent` to remove it.
    """

    model_config = ConfigDict(
        json_schema_extra={
            "examples": [
                {
                    "label": "Motion Picture",
                    "description": "A film or movie.",
                }
            ]
        }
    )

    label: str | None = Field(description="Its name, for people.", default=None)
    description: str | None = Field(description="Free text about it.", default=None)
    attributes_schema: dict[str, Any] | None = Field(
        description="Its fields, as a JSON Schema; replaces them all.", default=None
    )
    icon: str | None = Field(default=None, description=_ICON_DESCRIPTION)
    colour: str | None = Field(default=None, description=_COLOUR_DESCRIPTION)
    parent: str | None = Field(default=None, description=_PARENT_DESCRIPTION)
    on_clash: Literal["refuse", "merge"] = Field(
        default="refuse", description=_ON_CLASH_DESCRIPTION
    )
    on_detach: Literal["keep", "drop"] = Field(
        default="keep", description=_ON_DETACH_DESCRIPTION
    )

    def to_command(self, node_type_id: uuid.UUID) -> UpdateNodeTypeCommand:
        """Convert this request into an `UpdateNodeTypeCommand` for `node_type_id`."""
        return UpdateNodeTypeCommand(
            node_type_id=node_type_id,
            label=self.label,
            description=self.description,
            attributes_schema=self.attributes_schema,
            icon=self.icon,
            colour=self.colour,
            parent=self.parent,
            clear_icon="icon" in self.model_fields_set and self.icon is None,
            clear_colour="colour" in self.model_fields_set and self.colour is None,
            clear_parent="parent" in self.model_fields_set and self.parent is None,
            on_clash=self.on_clash,
            on_detach=self.on_detach,
        )


class ParentChangeRequest(RequestModel):
    """Request body for previewing a change of a type's parent."""

    model_config = ConfigDict(
        json_schema_extra={
            "examples": [{"parent": "memorabilia", "on_clash": "merge"}],
        }
    )

    parent: str | None = Field(
        default=None,
        description=(
            "The slug of the parent the type would have, or null for none. "
            + "The parent it already has is no change."
        ),
    )
    on_clash: Literal["refuse", "merge"] = Field(
        default="refuse", description=_ON_CLASH_DESCRIPTION
    )
    on_detach: Literal["keep", "drop"] = Field(
        default="keep", description=_ON_DETACH_DESCRIPTION
    )

    def to_query(self, node_type_id: uuid.UUID) -> PlanParentChangeQuery:
        """Convert this request into a `PlanParentChangeQuery` for `node_type_id`."""
        return PlanParentChangeQuery(
            node_type_id=node_type_id,
            parent=self.parent,
            on_clash=self.on_clash,
            on_detach=self.on_detach,
        )


class ParentChangePlanResponse(BaseModel):
    """What a change of a type's parent would do, without having done it."""

    model_config = ConfigDict(
        json_schema_extra={
            "examples": [
                {
                    "parent": "memorabilia",
                    "previous": None,
                    "allowed": True,
                    "reason": None,
                    "clashes": ["condition"],
                    "merged": ["condition"],
                    "conflicts": [],
                    "kept": [],
                    "archived": [],
                    "items": 12,
                }
            ]
        }
    )

    parent: str | None = Field(
        default=None, description="The parent the type would have, or null."
    )
    previous: str | None = Field(
        default=None, description="The parent it has now, or null."
    )
    allowed: bool = Field(description="Whether the change could be made as asked.")
    reason: str | None = Field(
        default=None, description="Why it could not, when it could not."
    )
    clashes: list[str] = Field(
        description="Field keys both the type and the new parent define."
    )
    merged: list[str] = Field(
        description="Keys whose own definition would give way to the parent's."
    )
    conflicts: list[str] = Field(
        description="Keys defined as different kinds of field, which cannot merge."
    )
    kept: list[str] = Field(
        description="The old parent's keys that would be copied onto the type."
    )
    archived: list[str] = Field(
        description="The old parent's keys that would be archived on the type."
    )
    items: int = Field(
        description="How many items of the type there are; none of their values change."
    )

    @classmethod
    def from_domain(cls, plan: ParentChangePlan) -> ParentChangePlanResponse:
        """Build a response from a `ParentChangePlan`."""
        result = plan.result
        return cls(
            parent=plan.parent,
            previous=plan.previous,
            allowed=plan.allowed,
            reason=plan.reason,
            clashes=list(result.clashes),
            merged=list(result.merged),
            conflicts=list(result.conflicts),
            kept=list(result.kept),
            archived=list(result.archived),
            items=plan.items,
        )


class NodeTypeResponse(BaseModel):
    """A node type as returned by the API."""

    model_config = ConfigDict(json_schema_extra={"examples": [NODE_TYPE_EXAMPLE]})

    id: uuid.UUID = Field(description="The item type's id.")
    slug: str = Field(description="Its short name; items refer to it.")
    label: str = Field(description="Its name, for people.")
    description: str | None = Field(description="Free text about it.", default=None)
    attributes_schema: dict[str, Any] | None = Field(
        description="Its fields, as a JSON Schema.", default=None
    )
    effective_schema: dict[str, Any] | None = Field(
        description=(
            "The fields items of this type use, as a JSON Schema: its parent's "
            + "followed by its own. The same as `attributes_schema` for a type with "
            + "no parent. Read-only; edit `attributes_schema`."
        ),
        default=None,
    )
    icon: str | None = Field(default=None, description=_ICON_DESCRIPTION)
    colour: str | None = Field(default=None, description=_COLOUR_DESCRIPTION)
    parent: str | None = Field(default=None, description=_PARENT_DESCRIPTION)
    created_at: datetime = Field(description="When it was created.")
    updated_at: datetime = Field(description="When it last changed.")

    @classmethod
    def from_domain(cls, node_type: NodeType) -> NodeTypeResponse:
        """Build a response from a domain `NodeType`."""
        return cls(
            id=node_type.id,
            slug=str(node_type.slug),
            label=node_type.label,
            description=node_type.description,
            attributes_schema=node_type.attributes_schema,
            effective_schema=(
                node_type.effective_schema
                if node_type.effective_schema is not None
                else node_type.attributes_schema
            ),
            icon=node_type.icon,
            colour=node_type.colour,
            parent=node_type.parent,
            created_at=node_type.created_at,
            updated_at=node_type.updated_at,
        )


class SharedSubtypeFieldResponse(BaseModel):
    """A field several subtypes of an item type each define the same way."""

    model_config = ConfigDict(
        json_schema_extra={
            "examples": [
                {
                    "key": "condition",
                    "label": "Condition",
                    "kind": "choice",
                    "subtypes": ["poster", "photo-print"],
                    "differing": [],
                }
            ]
        }
    )

    key: str = Field(description="The field's key.")
    label: str = Field(description="Its name, from the definition most subtypes share.")
    kind: str | None = Field(
        default=None, description="The field kind, such as `text` or `choice`."
    )
    subtypes: list[str] = Field(
        description="The slugs of the subtypes that define it as that kind."
    )
    differing: list[str] = Field(
        description=(
            "The slugs of subtypes that keep the key as another kind of field. "
            + "While there are any, the field cannot be moved up."
        )
    )

    @classmethod
    def from_domain(cls, field: SharedField) -> SharedSubtypeFieldResponse:
        """Build a response from a `SharedField`."""
        return cls(
            key=field.key,
            label=field.label,
            kind=field.kind,
            subtypes=list(field.subtypes),
            differing=list(field.differing),
        )


class PromotedSubtypeFieldResponse(BaseModel):
    """What moving a field from the subtypes up to their parent changed."""

    model_config = ConfigDict(
        json_schema_extra={
            "examples": [{"subtypes": 2, "node_type": NODE_TYPE_EXAMPLE}]
        }
    )

    subtypes: int = Field(description="How many subtypes the field moved off.")
    node_type: NodeTypeResponse = Field(
        description="The parent item type, with the field."
    )


class AttributeValueCountResponse(BaseModel):
    """A previously-used attribute value and how many nodes hold it."""

    model_config = ConfigDict(
        json_schema_extra={"examples": [{"value": "Draft", "count": 12}]}
    )

    value: str = Field(description="A value the field has held.")
    count: int = Field(description="How many items hold it.")
