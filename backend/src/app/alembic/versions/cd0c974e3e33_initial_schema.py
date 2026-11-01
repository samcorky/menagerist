"""initial schema

The whole schema as of the first release, flattened from the migrations written
during development. Built-in presets are seeded by the next revision.

Revision ID: cd0c974e3e33
Revises:
Create Date: 2026-11-01 18:40:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "cd0c974e3e33"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_JSONB = postgresql.JSONB(astext_type=sa.Text())
_TIMESTAMP = sa.DateTime(timezone=True)

# Tables in dependency order; downgrade drops them in reverse.
_TABLES = (
    "users",
    "sessions",
    "api_tokens",
    "nodes",
    "node_types",
    "edge_types",
    "edges",
    "media_assets",
    "media_attachments",
    "collections",
    "collection_members",
    "presets",
    "example_installations",
    "setting_values",
    "sign_in_attempts",
    "update_checks",
    "job_runs",
    "schedule_cursors",
    "worker_heartbeats",
)


def upgrade() -> None:
    _create_extensions()
    _create_identity_tables()
    _create_graph_tables()
    _create_media_tables()
    _create_collection_tables()
    _create_other_tables()
    _create_scheduling_tables()
    _create_search_indexes()


def downgrade() -> None:
    for table in reversed(_TABLES):
        op.drop_table(table)
    op.execute("DROP FUNCTION IF EXISTS immutable_unaccent(text)")
    # `unaccent` and `pg_trgm` stay installed: they may be shared with other
    # objects in the database, so dropping them here is not provably safe.


def _create_extensions() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS pg_trgm")
    op.execute("CREATE EXTENSION IF NOT EXISTS unaccent")
    # `unaccent` is only STABLE, so it cannot back an index; this wrapper pins
    # the dictionary and is declared IMMUTABLE.
    op.execute(
        """
        CREATE OR REPLACE FUNCTION immutable_unaccent(text) RETURNS text
        AS $$ SELECT public.unaccent('public.unaccent', $1) $$
        LANGUAGE sql IMMUTABLE PARALLEL SAFE STRICT
        """
    )


def _create_identity_tables() -> None:
    op.create_table(
        "users",
        sa.Column("username", sa.String(), nullable=False),
        sa.Column("display_name", sa.String(), nullable=False),
        sa.Column("password_hash", sa.String(), nullable=False),
        sa.Column("role", sa.String(), nullable=False),
        sa.Column("password_expired", sa.Boolean(), nullable=False),
        sa.Column("disabled", sa.Boolean(), nullable=False),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("created_at", _TIMESTAMP, nullable=False),
        sa.Column("updated_at", _TIMESTAMP, nullable=False),
        sa.Column("last_login_at", _TIMESTAMP, nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("username"),
    )
    op.create_table(
        "sessions",
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("token_hash", sa.String(), nullable=False),
        sa.Column("created_at", _TIMESTAMP, nullable=False),
        sa.Column("expires_at", _TIMESTAMP, nullable=False),
        sa.Column("last_seen_at", _TIMESTAMP, nullable=False),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_agent", sa.String(), nullable=True),
        sa.Column("client_ip", sa.String(), nullable=True),
        sa.Column("client_platform", sa.String(), nullable=True),
        sa.Column("client_mobile", sa.Boolean(), nullable=True),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_sessions_expires_at", "sessions", ["expires_at"])
    op.create_index("ix_sessions_token_hash", "sessions", ["token_hash"], unique=True)
    op.create_index("ix_sessions_user_id", "sessions", ["user_id"])
    op.create_table(
        "api_tokens",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("secret_hash", sa.String(), nullable=False),
        sa.Column("grants", _JSONB, nullable=False),
        sa.Column("created_at", _TIMESTAMP, nullable=False),
        sa.Column("expires_at", _TIMESTAMP, nullable=False),
        sa.Column("last_used_at", _TIMESTAMP, nullable=True),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_api_tokens_expires_at", "api_tokens", ["expires_at"])
    op.create_index("ix_api_tokens_user_id", "api_tokens", ["user_id"])
    op.create_table(
        "sign_in_attempts",
        sa.Column("key_type", sa.String(), nullable=False),
        sa.Column("key_hash", sa.String(), nullable=False),
        sa.Column("failure_count", sa.Integer(), nullable=False),
        sa.Column("window_start", _TIMESTAMP, nullable=False),
        sa.Column("locked_until", _TIMESTAMP, nullable=True),
        sa.PrimaryKeyConstraint("key_type", "key_hash"),
    )
    op.create_index(
        "ix_sign_in_attempts_window_start", "sign_in_attempts", ["window_start"]
    )


def _create_graph_tables() -> None:
    op.create_table(
        "nodes",
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("type", sa.String(), nullable=True),
        sa.Column("description", sa.String(), nullable=True),
        sa.Column("attributes", _JSONB, nullable=False),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("deleted_at", _TIMESTAMP, nullable=True),
        sa.Column("created_at", _TIMESTAMP, nullable=False),
        sa.Column("updated_at", _TIMESTAMP, nullable=False),
        sa.Column("favourite", sa.Boolean(), server_default=sa.false(), nullable=False),
        sa.Column(
            "tags", _JSONB, server_default=sa.text("'[]'::jsonb"), nullable=False
        ),
        sa.Column("extra_schema", _JSONB, nullable=True),
        sa.Column("owner_id", sa.Uuid(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_nodes_deleted_at", "nodes", ["deleted_at"])
    op.create_index("ix_nodes_owner_id_id", "nodes", ["owner_id", "id"])
    op.create_index("ix_nodes_type", "nodes", ["type"])
    op.create_table(
        "node_types",
        sa.Column("slug", sa.String(), nullable=False),
        sa.Column("label", sa.String(), nullable=False),
        sa.Column("description", sa.String(), nullable=True),
        sa.Column("attributes_schema", _JSONB, nullable=True),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("deleted_at", _TIMESTAMP, nullable=True),
        sa.Column("created_at", _TIMESTAMP, nullable=False),
        sa.Column("updated_at", _TIMESTAMP, nullable=False),
        sa.Column("icon", sa.String(), nullable=True),
        sa.Column("colour", sa.String(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_node_types_deleted_at", "node_types", ["deleted_at"])
    op.create_index("ix_node_types_slug", "node_types", ["slug"])
    op.create_index(
        "uq_node_types_slug_live",
        "node_types",
        ["slug"],
        unique=True,
        postgresql_where=sa.text("deleted_at IS NULL"),
    )
    op.create_table(
        "edge_types",
        sa.Column("slug", sa.String(), nullable=False),
        sa.Column("label", sa.String(), nullable=False),
        sa.Column("reverse_label", sa.String(), nullable=True),
        sa.Column("description", sa.String(), nullable=True),
        sa.Column(
            "directional", sa.Boolean(), server_default=sa.true(), nullable=False
        ),
        sa.Column("attributes_schema", _JSONB, nullable=True),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("deleted_at", _TIMESTAMP, nullable=True),
        sa.Column("created_at", _TIMESTAMP, nullable=False),
        sa.Column("updated_at", _TIMESTAMP, nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_edge_types_deleted_at", "edge_types", ["deleted_at"])
    op.create_index("ix_edge_types_slug", "edge_types", ["slug"])
    op.create_index(
        "uq_edge_types_slug_live",
        "edge_types",
        ["slug"],
        unique=True,
        postgresql_where=sa.text("deleted_at IS NULL"),
    )
    op.create_table(
        "edges",
        sa.Column("source_id", sa.Uuid(), nullable=False),
        sa.Column("target_id", sa.Uuid(), nullable=False),
        sa.Column("type", sa.String(), nullable=False),
        sa.Column("attributes", _JSONB, nullable=False),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("deleted_at", _TIMESTAMP, nullable=True),
        sa.Column("created_at", _TIMESTAMP, nullable=False),
        sa.Column("updated_at", _TIMESTAMP, nullable=False),
        sa.Column("owner_id", sa.Uuid(), nullable=True),
        sa.ForeignKeyConstraint(["source_id"], ["nodes.id"]),
        sa.ForeignKeyConstraint(["target_id"], ["nodes.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_edges_deleted_at", "edges", ["deleted_at"])
    op.create_index("ix_edges_owner_id_id", "edges", ["owner_id", "id"])
    op.create_index("ix_edges_source_id", "edges", ["source_id"])
    op.create_index("ix_edges_target_id", "edges", ["target_id"])
    op.create_index("ix_edges_type", "edges", ["type"])


def _create_media_tables() -> None:
    op.create_table(
        "media_assets",
        sa.Column("filename", sa.String(), nullable=False),
        sa.Column("content_type", sa.String(), nullable=False),
        sa.Column("size", sa.Integer(), nullable=False),
        sa.Column("sha256", sa.String(), nullable=False),
        sa.Column("status", sa.String(), nullable=False),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("created_at", _TIMESTAMP, nullable=False),
        sa.Column("updated_at", _TIMESTAMP, nullable=False),
        sa.Column(
            "has_thumbnail", sa.Boolean(), server_default=sa.false(), nullable=False
        ),
        sa.Column("thumbnail_sha256", sa.String(), nullable=True),
        sa.Column("owner_id", sa.Uuid(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_media_assets_owner_id_id", "media_assets", ["owner_id", "id"])
    op.create_index("ix_media_assets_status", "media_assets", ["status"])
    op.create_table(
        "media_attachments",
        sa.Column("asset_id", sa.Uuid(), nullable=False),
        sa.Column("target_type", sa.String(), nullable=False),
        sa.Column("target_id", sa.Uuid(), nullable=False),
        sa.Column("attribute_key", sa.String(), nullable=True),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("created_at", _TIMESTAMP, nullable=False),
        sa.Column("updated_at", _TIMESTAMP, nullable=False),
        sa.ForeignKeyConstraint(["asset_id"], ["media_assets.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "asset_id",
            "target_type",
            "target_id",
            "attribute_key",
            name="uq_media_attachment",
        ),
    )
    op.create_index("ix_media_attachments_asset_id", "media_attachments", ["asset_id"])
    op.create_index(
        "ix_media_attachments_target_id", "media_attachments", ["target_id"]
    )
    op.create_index(
        "ix_media_attachments_target_type", "media_attachments", ["target_type"]
    )
    op.create_index(
        "uq_media_attachment_cover",
        "media_attachments",
        ["target_type", "target_id"],
        unique=True,
        postgresql_where=sa.text("attribute_key = 'cover'"),
    )


def _create_collection_tables() -> None:
    op.create_table(
        "collections",
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("slug", sa.String(), nullable=False),
        sa.Column("description", sa.String(), nullable=True),
        sa.Column("kind", sa.String(), nullable=False),
        sa.Column("owner_id", sa.Uuid(), nullable=False),
        sa.Column("visibility", sa.String(), nullable=False),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("created_at", _TIMESTAMP, nullable=False),
        sa.Column("updated_at", _TIMESTAMP, nullable=False),
        sa.Column("deleted_at", _TIMESTAMP, nullable=True),
        sa.Column("definition", _JSONB, nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_collections_deleted_at", "collections", ["deleted_at"])
    op.create_index("ix_collections_owner_id", "collections", ["owner_id"])
    op.create_index(
        "uq_collections_slug_live",
        "collections",
        ["owner_id", "slug"],
        unique=True,
        postgresql_where=sa.text("deleted_at IS NULL"),
    )
    op.create_table(
        "collection_members",
        sa.Column("collection_id", sa.Uuid(), nullable=False),
        sa.Column("item_id", sa.Uuid(), nullable=False),
        sa.Column("added_at", _TIMESTAMP, nullable=False),
        sa.ForeignKeyConstraint(["collection_id"], ["collections.id"]),
        sa.PrimaryKeyConstraint("collection_id", "item_id"),
    )
    op.create_index("ix_collection_members_item_id", "collection_members", ["item_id"])


def _create_other_tables() -> None:
    op.create_table(
        "presets",
        sa.Column("kind", sa.String(), nullable=False),
        sa.Column("label", sa.String(), nullable=False),
        sa.Column("description", sa.String(), nullable=True),
        sa.Column(
            "definition",
            _JSONB,
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
        sa.Column("version", sa.Integer(), server_default="1", nullable=False),
        sa.Column("builtin", sa.Boolean(), server_default=sa.false(), nullable=False),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("deleted_at", _TIMESTAMP, nullable=True),
        sa.Column("created_at", _TIMESTAMP, nullable=False),
        sa.Column("updated_at", _TIMESTAMP, nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_presets_deleted_at", "presets", ["deleted_at"])
    op.create_index("ix_presets_kind", "presets", ["kind"])
    op.create_table(
        "example_installations",
        sa.Column("pack_id", sa.String(), nullable=False),
        sa.Column("status", sa.String(), nullable=False),
        sa.Column(
            "entities",
            _JSONB,
            server_default=sa.text("'[]'::jsonb"),
            nullable=False,
        ),
        sa.Column("installed_at", _TIMESTAMP, nullable=True),
        sa.Column("removed_at", _TIMESTAMP, nullable=True),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("created_at", _TIMESTAMP, nullable=False),
        sa.Column("updated_at", _TIMESTAMP, nullable=False),
        sa.Column("owner_id", sa.Uuid(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_example_installations_owner_id_id",
        "example_installations",
        ["owner_id", "id"],
    )
    op.create_index(
        "ix_example_installations_pack_id", "example_installations", ["pack_id"]
    )
    op.create_index(
        "uq_example_installations_active_pack",
        "example_installations",
        ["pack_id", "owner_id"],
        unique=True,
        postgresql_where=sa.text("status IN ('installing', 'installed')"),
    )
    op.create_table(
        "setting_values",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("scope", sa.String(), nullable=False),
        sa.Column("owner_id", sa.Uuid(), nullable=True),
        sa.Column("key", sa.String(), nullable=False),
        sa.Column("value", _JSONB, nullable=False),
        sa.Column("updated_at", _TIMESTAMP, nullable=False),
        sa.Column("updated_by", sa.Uuid(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "uq_setting_values_instance",
        "setting_values",
        ["scope", "key"],
        unique=True,
        postgresql_where=sa.text("owner_id IS NULL"),
    )
    op.create_index(
        "uq_setting_values_owner",
        "setting_values",
        ["owner_id", "key"],
        unique=True,
        postgresql_where=sa.text("owner_id IS NOT NULL"),
    )
    op.create_table(
        "update_checks",
        sa.Column("key", sa.String(), nullable=False),
        sa.Column("source", sa.String(), nullable=False),
        sa.Column("channel", sa.String(), nullable=False),
        sa.Column("latest_version", sa.String(), nullable=True),
        sa.Column("latest_url", sa.String(), nullable=True),
        sa.Column("latest_published_at", _TIMESTAMP, nullable=True),
        sa.Column("latest_prerelease", sa.Boolean(), nullable=False),
        sa.Column("last_success_at", _TIMESTAMP, nullable=True),
        sa.Column("last_attempt_at", _TIMESTAMP, nullable=False),
        sa.Column("failure", sa.String(), nullable=True),
        sa.PrimaryKeyConstraint("key"),
    )


def _create_scheduling_tables() -> None:
    op.create_table(
        "job_runs",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("job_key", sa.String(), nullable=False),
        sa.Column("scheduled_for", _TIMESTAMP, nullable=False),
        sa.Column("created_at", _TIMESTAMP, nullable=False),
        sa.Column("lane", sa.String(), nullable=False),
        sa.Column("overlap", sa.String(), nullable=False),
        sa.Column("deduplication_key", sa.Uuid(), nullable=True),
        sa.Column("requested_by", sa.Uuid(), nullable=True),
        sa.Column("status", sa.String(), nullable=False),
        sa.Column("worker_id", sa.String(), nullable=True),
        sa.Column("started_at", _TIMESTAMP, nullable=True),
        sa.Column("heartbeat_at", _TIMESTAMP, nullable=True),
        sa.Column("finished_at", _TIMESTAMP, nullable=True),
        sa.Column("error", sa.String(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_job_runs_claim",
        "job_runs",
        ["status", "lane", "scheduled_for", "created_at", "id"],
    )
    op.create_index("ix_job_runs_heartbeat", "job_runs", ["status", "heartbeat_at"])
    op.create_index("ix_job_runs_history", "job_runs", ["job_key", "created_at", "id"])
    op.create_index(
        "uq_job_runs_deduplication_key",
        "job_runs",
        ["deduplication_key"],
        unique=True,
    )
    op.create_index(
        "uq_job_runs_running_job",
        "job_runs",
        ["job_key"],
        unique=True,
        postgresql_where=sa.text("status = 'running'"),
    )
    op.create_table(
        "schedule_cursors",
        sa.Column("job_key", sa.String(), nullable=False),
        sa.Column("expression", sa.String(), nullable=True),
        sa.Column("timezone", sa.String(), nullable=False),
        sa.Column("checked_until", _TIMESTAMP, nullable=False),
        sa.PrimaryKeyConstraint("job_key"),
    )
    op.create_table(
        "worker_heartbeats",
        sa.Column("worker_id", sa.String(), nullable=False),
        sa.Column("heartbeat_at", _TIMESTAMP, nullable=False),
        sa.PrimaryKeyConstraint("worker_id"),
    )


def _create_search_indexes() -> None:
    """Create the node indexes that need expressions or operator classes."""
    # Containment (@>) on attributes and tags.
    op.execute(
        """
        CREATE INDEX ix_nodes_attributes_gin ON nodes
        USING gin (attributes jsonb_path_ops)
        """
    )
    op.execute(
        "CREATE INDEX ix_nodes_tags_gin ON nodes USING gin (tags jsonb_path_ops)"
    )
    # Backs per-item field conditions in query_sql._declares.
    op.execute(
        """
        CREATE INDEX ix_nodes_extra_schema_gin ON nodes
        USING gin (extra_schema jsonb_path_ops)
        WHERE extra_schema IS NOT NULL
        """
    )
    # Accent-folding substring search on name, description and attribute text.
    # The attribute index backs the superset prefilter in search_sql.search_clause.
    for column, expression in (
        ("name", "name"),
        ("description", "description"),
        ("attributes_text", "(attributes)::text"),
    ):
        op.execute(
            f"""
            CREATE INDEX ix_nodes_{column}_trgm ON nodes
            USING gin (immutable_unaccent({expression}) gin_trgm_ops)
            """
        )
    # Match the sort expressions in query_sql.py, so ORDER BY can use them. The ids
    # stay ascending, so a descending name sort needs its own index: a backward scan
    # of the first would flip the id tie-break too. Timestamps rarely tie, so
    # descending reuses the ascending index (backward scan plus an incremental sort
    # of the ties).
    op.execute(
        """
        CREATE INDEX ix_nodes_owner_name_sort ON nodes
        (owner_id, (lower(immutable_unaccent(name)) COLLATE "C"), id)
        WHERE deleted_at IS NULL
        """
    )
    op.execute(
        """
        CREATE INDEX ix_nodes_owner_name_sort_desc ON nodes
        (owner_id, (lower(immutable_unaccent(name)) COLLATE "C") DESC, id)
        WHERE deleted_at IS NULL
        """
    )
    for column in ("created", "updated"):
        epoch = f"CAST(EXTRACT(epoch FROM timezone('UTC', {column}_at)) AS FLOAT)"
        op.execute(
            f"""
            CREATE INDEX ix_nodes_owner_{column}_sort ON nodes
            (owner_id, ({epoch}), id)
            WHERE deleted_at IS NULL
            """
        )
