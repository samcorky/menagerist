import uuid
from typing import Any

from sqlalchemy import ForeignKey, Index, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.platform.database import Base
from app.platform.orm_mixins import IdentifiableMixin, OwnedMixin, SoftDeletableMixin


def _epoch(column: str) -> str:
    """The epoch-seconds index expression as Postgres reflects it."""
    return f"(EXTRACT(epoch FROM timezone('UTC'::text, {column}))::double precision)"


class NodeTypeModel(IdentifiableMixin, SoftDeletableMixin, Base):
    """ORM row for a node type.

    Storage shape kept separate from `domain.NodeType`.
    """

    __tablename__ = "node_types"
    # Only live rows reserve a slug; the use cases check this too, the index backs them.
    __table_args__ = (
        Index(
            "uq_node_types_slug_live",
            "slug",
            unique=True,
            postgresql_where=text("deleted_at IS NULL"),
        ),
    )

    slug: Mapped[str] = mapped_column(index=True)
    label: Mapped[str]
    description: Mapped[str | None]
    attributes_schema: Mapped[dict[str, Any] | None] = mapped_column(
        JSONB, nullable=True
    )


class NodeModel(IdentifiableMixin, OwnedMixin, SoftDeletableMixin, Base):
    """ORM row for a node - the storage shape, kept separate from `domain.Node`."""

    __tablename__ = "nodes"
    __table_args__ = (
        Index("ix_nodes_owner_id_id", "owner_id", "id"),
        Index(
            "ix_nodes_attributes_gin",
            "attributes",
            postgresql_using="gin",
            postgresql_ops={"attributes": "jsonb_path_ops"},
        ),
        Index(
            "ix_nodes_tags_gin",
            "tags",
            postgresql_using="gin",
            postgresql_ops={"tags": "jsonb_path_ops"},
        ),
        # The migration adds COLLATE "C" to both name-sort indexes; Alembic's
        # reflection drops it, so it is left out here to keep the models in sync.
        Index(
            "ix_nodes_owner_name_sort",
            "owner_id",
            text("lower(immutable_unaccent(name))"),
            "id",
            postgresql_where=text("deleted_at IS NULL"),
        ),
        Index(
            "ix_nodes_owner_name_sort_desc",
            "owner_id",
            text("lower(immutable_unaccent(name)) DESC"),
            "id",
            postgresql_where=text("deleted_at IS NULL"),
        ),
        Index(
            "ix_nodes_owner_created_sort",
            "owner_id",
            text(_epoch("created_at")),
            "id",
            postgresql_where=text("deleted_at IS NULL"),
        ),
        Index(
            "ix_nodes_owner_updated_sort",
            "owner_id",
            text(_epoch("updated_at")),
            "id",
            postgresql_where=text("deleted_at IS NULL"),
        ),
        # Backs per-item field conditions (query_sql._declares).
        Index(
            "ix_nodes_extra_schema_gin",
            "extra_schema",
            postgresql_using="gin",
            postgresql_ops={"extra_schema": "jsonb_path_ops"},
            postgresql_where=text("extra_schema IS NOT NULL"),
        ),
        Index(
            "ix_nodes_name_trgm",
            text("immutable_unaccent(name)"),
            postgresql_using="gin",
            postgresql_ops={"immutable_unaccent(name)": "gin_trgm_ops"},
        ),
        Index(
            "ix_nodes_description_trgm",
            text("immutable_unaccent(description)"),
            postgresql_using="gin",
            postgresql_ops={"immutable_unaccent(description)": "gin_trgm_ops"},
        ),
        Index(
            "ix_nodes_attributes_text_trgm",
            text("immutable_unaccent(attributes::text)"),
            postgresql_using="gin",
            postgresql_ops={"immutable_unaccent(attributes::text)": "gin_trgm_ops"},
        ),
    )

    name: Mapped[str]
    type: Mapped[str | None] = mapped_column(index=True, nullable=True)
    description: Mapped[str | None]
    attributes: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)
    favourite: Mapped[bool] = mapped_column(default=False)
    tags: Mapped[list[str]] = mapped_column(JSONB, default=list)
    extra_schema: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)


class EdgeModel(IdentifiableMixin, OwnedMixin, SoftDeletableMixin, Base):
    """ORM row for an edge - the storage shape, kept separate from `domain.Edge`."""

    __tablename__ = "edges"
    __table_args__ = (Index("ix_edges_owner_id_id", "owner_id", "id"),)

    source_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("nodes.id"), index=True)
    target_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("nodes.id"), index=True)
    type: Mapped[str] = mapped_column(index=True)
    attributes: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)


class EdgeTypeModel(IdentifiableMixin, SoftDeletableMixin, Base):
    """ORM row for an edge type."""

    __tablename__ = "edge_types"
    __table_args__ = (
        Index(
            "uq_edge_types_slug_live",
            "slug",
            unique=True,
            postgresql_where=text("deleted_at IS NULL"),
        ),
    )

    slug: Mapped[str] = mapped_column(index=True)
    label: Mapped[str]
    reverse_label: Mapped[str | None]
    description: Mapped[str | None]
    directional: Mapped[bool] = mapped_column(default=True)
    attributes_schema: Mapped[dict[str, Any] | None] = mapped_column(
        JSONB, nullable=True
    )
