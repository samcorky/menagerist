"""What a personal access token may be granted, and what it costs to use."""

from typing import Any

import pytest

from app.entrypoints.api.shared.authorisation import (
    ADMIN_ONLY_ACTIONS,
    MEMBER_PERMISSIONS,
    TOKEN_GRANTABLE_PERMISSIONS,
)
from app.entrypoints.api.shared.permissions import expand
from app.modules.backup.application.import_user_archive import ImportUserArchive
from app.modules.backup.application.import_user_data import ImportUserData
from app.modules.backup.application.permissions import BackupPermission
from app.modules.graph.application.promote_extra_schema_field import (
    PromoteExtraSchemaField,
)
from app.modules.graph.application.update_node import UpdateNode
from app.modules.graph.application.update_node_type import UpdateNodeType
from app.modules.media.application.attach_media import AttachMedia
from app.modules.media.application.stage_media import StageMedia
from app.modules.media.application.upload_and_attach_media import UploadAndAttachMedia
from app.shared_kernel.access import Content, Requires

type UseCaseType = type[Any]

# Composites call inner use cases with the same actor, so a token needs every
# inner permission (R8). Inner classes are read from the source, not retyped.
COMPOSITES: dict[UseCaseType, tuple[tuple[UseCaseType, ...], frozenset[str]]] = {
    UploadAndAttachMedia: (
        (StageMedia, AttachMedia),
        frozenset({"media:item:write"}),
    ),
    PromoteExtraSchemaField: (
        (UpdateNodeType, UpdateNode),
        frozenset({"graph:type:write", "graph:item:write"}),
    ),
    ImportUserArchive: ((ImportUserData,), frozenset({"backup:own_data:import"})),
}


def _needs(use_case: UseCaseType) -> str:
    access = use_case.access
    assert isinstance(access, Content | Requires)
    return str(access.permission)


def test_grantable_set_is_member_content_minus_backups() -> None:
    """Tokens get content permissions, never admin or backup ones."""
    assert TOKEN_GRANTABLE_PERMISSIONS <= MEMBER_PERMISSIONS
    assert not TOKEN_GRANTABLE_PERMISSIONS & ADMIN_ONLY_ACTIONS
    assert not any(isinstance(p, BackupPermission) for p in TOKEN_GRANTABLE_PERMISSIONS)
    assert (
        MEMBER_PERMISSIONS
        - {
            BackupPermission.EXPORT_OWN_DATA,
            BackupPermission.IMPORT_OWN_DATA,
        }
        == TOKEN_GRANTABLE_PERMISSIONS
    )


def test_every_grantable_permission_implies_only_grantable_ones() -> None:
    """Granting a permission never smuggles in one that cannot be granted."""
    assert expand(TOKEN_GRANTABLE_PERMISSIONS) == TOKEN_GRANTABLE_PERMISSIONS


@pytest.mark.parametrize("composite", list(COMPOSITES), ids=lambda c: c.__name__)
def test_composites_need_every_inner_permission(composite: UseCaseType) -> None:
    """The table agrees with the declared stances of the use case and its parts."""
    inner, expected = COMPOSITES[composite]
    declared = {_needs(composite), *(_needs(part) for part in inner)}
    assert declared == expected
