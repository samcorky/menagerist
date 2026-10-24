"""Pins which permission every permissioned use case requires."""

import importlib
import inspect
import pkgutil
from typing import Any

import pytest

import app.modules
from app.entrypoints.api.shared.authorisation import (
    ADMIN_ONLY_ACTIONS,
    MEMBER_PERMISSIONS,
)
from app.entrypoints.api.shared.permissions import ALL_PERMISSIONS
from app.shared_kernel.access import Content, Requires
from app.shared_kernel.cqrs import UseCase

EXPECTED_PERMISSIONS: dict[str, str] = {
    "backup.CreateBackup": "backup:archive:create",
    "backup.DeleteBackup": "backup:archive:delete",
    "backup.DeleteUserExport": "backup:own_data:export",
    "backup.ExportUserData": "backup:own_data:export",
    "backup.ImportUserArchive": "backup:own_data:import",
    "backup.ImportUserData": "backup:own_data:import",
    "backup.ListBackups": "backup:archive:read",
    "backup.OpenBackup": "backup:archive:read",
    "backup.ListUserExports": "backup:own_data:export",
    "backup.OpenUserExport": "backup:own_data:export",
    "backup.PruneBackups": "backup:archive:delete",
    "backup.RestoreBackup": "backup:archive:restore",
    "backup.UploadBackup": "backup:archive:create",
    "backup.VerifyBackup": "backup:archive:read",
    "collections.AddItemsToCollection": "collections:collection:write",
    "collections.CountCollectionItems": "collections:collection:read",
    "collections.CreateCollection": "collections:collection:write",
    "collections.DeleteCollection": "collections:collection:write",
    "collections.GetCollection": "collections:collection:read",
    "collections.ListCollections": "collections:collection:read",
    "collections.RemoveItemFromCollection": "collections:collection:write",
    "collections.ResolveCollection": "collections:collection:read",
    "collections.UpdateCollection": "collections:collection:write",
    "examples.InstallExamplePack": "examples:pack:install",
    "examples.ListExampleEntities": "examples:pack:read",
    "examples.ListExamplePacks": "examples:pack:read",
    "examples.UninstallExamplePack": "examples:pack:install",
    "graph.CountEdgeTypeAttributeUsage": "graph:item:read",
    "graph.CountNodeTypeAttributeUsage": "graph:item:read",
    "graph.CreateEdge": "graph:item:write",
    "graph.CreateEdgeType": "graph:type:write",
    "graph.CreateEdges": "graph:item:write",
    "graph.CreateNode": "graph:item:write",
    "graph.CreateNodeType": "graph:type:write",
    "graph.DeleteEdge": "graph:item:write",
    "graph.DeleteEdgeType": "graph:edge_type:delete",
    "graph.DeleteNode": "graph:item:write",
    "graph.DeleteNodeType": "graph:node_type:delete",
    "graph.DeleteUnusedNodeType": "graph:node_type:delete",
    "graph.GetEdge": "graph:item:read",
    "graph.GetEdgeType": "graph:type:read",
    "graph.GetNode": "graph:item:read",
    "graph.GetNodeType": "graph:type:read",
    "graph.ListAttributeValues": "graph:item:read",
    "graph.ListEdgeTypes": "graph:type:read",
    "graph.ListEdges": "graph:item:read",
    "graph.ListItemFields": "graph:item:read",
    "graph.ListNodeTypes": "graph:type:read",
    "graph.ListNodes": "graph:item:read",
    "graph.PromoteExtraSchemaField": "graph:type:write",
    "graph.PurgeEdgeTypeAttribute": "graph:edge_type:purge_attribute",
    "graph.PurgeNodeTypeAttribute": "graph:node_type:purge_attribute",
    "graph.SearchNodes": "graph:item:read",
    "graph.UpdateEdge": "graph:item:write",
    "graph.UpdateEdgeType": "graph:type:write",
    "graph.UpdateNode": "graph:item:write",
    "graph.UpdateNodeType": "graph:type:write",
    "graph.ValidateQuery": "graph:type:read",
    "identity.CreateUser": "identity:user:create",
    "identity.ListSessions": "identity:session:list",
    "identity.ListUsers": "identity:user:list",
    "identity.ResetPassword": "identity:user:reset_password",
    "identity.RevokeSession": "identity:session:revoke",
    "identity.UnlockUser": "identity:user:unlock",
    "identity.UpdateUser": "identity:user:update",
    "media.AttachMedia": "media:item:write",
    "media.ClearMediaCover": "media:item:write",
    "media.DeleteMedia": "media:item:write",
    "media.DetachMedia": "media:item:write",
    "media.GetMedia": "media:item:read",
    "media.ListNodeMedia": "media:item:read",
    "media.OrphanMedia": "media:item:write",
    "media.PromoteMedia": "media:item:write",
    "media.SetMediaCover": "media:item:write",
    "media.StageMedia": "media:item:write",
    "media.UpdateMedia": "media:item:write",
    "media.UploadAndAttachMedia": "media:item:write",
    "presets.CreatePreset": "presets:preset:write",
    "presets.DeletePreset": "presets:preset:write",
    "presets.ExportPresets": "presets:preset:read",
    "presets.GetPreset": "presets:preset:read",
    "presets.ImportPresets": "presets:preset:write",
    "presets.ListPresets": "presets:preset:read",
    "presets.UpdatePreset": "presets:preset:write",
    "system.GetHealthReadyDetail": "system:diagnostics:read",
    "system.GetVersionDetail": "system:diagnostics:read",
    "system.RunBrowserCheck": "system:diagnostics:read",
}

# Permissions are never renamed: a grant stored under a name must keep meaning
# the same thing. A permission is only ever split, with the old one implying the
# new ones through `implied()`.
EXPECTED_CATALOGUE: frozenset[str] = frozenset(
    {
        "backup:archive:create",
        "backup:archive:delete",
        "backup:archive:read",
        "backup:archive:restore",
        "backup:own_data:export",
        "backup:own_data:import",
        "collections:collection:read",
        "collections:collection:write",
        "examples:pack:install",
        "examples:pack:read",
        "graph:edge_type:delete",
        "graph:edge_type:purge_attribute",
        "graph:item:read",
        "graph:item:write",
        "graph:node_type:delete",
        "graph:node_type:purge_attribute",
        "graph:type:read",
        "graph:type:write",
        "identity:session:list",
        "identity:session:revoke",
        "identity:user:create",
        "identity:user:list",
        "identity:user:reset_password",
        "identity:user:unlock",
        "identity:user:update",
        "media:item:read",
        "media:item:write",
        "presets:preset:read",
        "presets:preset:write",
        "system:diagnostics:read",
    }
)


def _permissioned() -> dict[str, str]:
    live: dict[str, str] = {}
    for info in pkgutil.walk_packages(app.modules.__path__, "app.modules."):
        if ".application" not in info.name:
            continue
        module = importlib.import_module(info.name)
        for _, cls in inspect.getmembers(module, inspect.isclass):
            if (
                cls.__module__ != module.__name__
                or not issubclass(cls, UseCase)
                or inspect.isabstract(cls)
            ):
                continue
            access: Any = getattr(cls, "access", None)
            if isinstance(access, Content | Requires):
                live[f"{cls.__module__.split('.')[2]}.{cls.__name__}"] = (
                    access.permission.value
                )
    return live


def test_every_use_case_permission_is_pinned() -> None:
    """Changing who may call a use case means editing the pin."""
    assert _permissioned() == EXPECTED_PERMISSIONS


@pytest.mark.parametrize("name", sorted(EXPECTED_PERMISSIONS))
def test_every_non_admin_permission_is_a_member_permission(name: str) -> None:
    """Members lose nothing: every non-admin permission is in the member grant."""
    value = EXPECTED_PERMISSIONS[name]
    admin = {p.value for p in ADMIN_ONLY_ACTIONS}
    member = {p.value for p in MEMBER_PERMISSIONS}
    assert value in admin or value in member


def test_catalogue_is_pinned() -> None:
    """The permission catalogue (16 admin, 14 member) only changes deliberately."""
    assert {p.value for p in ALL_PERMISSIONS} == EXPECTED_CATALOGUE
    assert len(EXPECTED_CATALOGUE) == 30
