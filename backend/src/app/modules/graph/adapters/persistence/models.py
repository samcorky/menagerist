import uuid
from typing import Any

from sqlalchemy import ForeignKey
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.platform.database import Base
from app.platform.orm_mixins import IdentifiableMixin, SoftDeletableMixin


class NodeTypeModel(IdentifiableMixin, SoftDeletableMixin, Base):
    """ORM row for a node type.

    Storage shape kept separate from `domain.NodeType`.
    """

    __tablename__ = "node_types"

    slug: Mapped[str] = mapped_column(unique=True, index=True)
    label: Mapped[str]
    description: Mapped[str | None]
    attributes_schema: Mapped[dict[str, Any] | None] = mapped_column(
        JSONB, nullable=True
    )


class NodeModel(IdentifiableMixin, SoftDeletableMixin, Base):
    """ORM row for a node - the storage shape, kept separate from `domain.Node`."""

    __tablename__ = "nodes"

    name: Mapped[str]
    type: Mapped[str | None] = mapped_column(index=True, nullable=True)
    description: Mapped[str | None]
    attributes: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)
    favourite: Mapped[bool] = mapped_column(default=False)


class EdgeModel(IdentifiableMixin, SoftDeletableMixin, Base):
    """ORM row for an edge - the storage shape, kept separate from `domain.Edge`."""

    __tablename__ = "edges"

    source_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("nodes.id"), index=True)
    target_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("nodes.id"), index=True)
    type: Mapped[str] = mapped_column(index=True)
    attributes: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)


class EdgeTypeModel(IdentifiableMixin, SoftDeletableMixin, Base):
    """ORM row for an edge type."""

    __tablename__ = "edge_types"

    slug: Mapped[str] = mapped_column(unique=True, index=True)
    label: Mapped[str]
    reverse_label: Mapped[str | None]
    description: Mapped[str | None]
    directional: Mapped[bool] = mapped_column(default=True)
    attributes_schema: Mapped[dict[str, Any] | None] = mapped_column(
        JSONB, nullable=True
    )
