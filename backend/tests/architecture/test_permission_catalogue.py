import importlib
import inspect
import pkgutil

import app.modules
from app.entrypoints.api.shared.authorisation import MEMBER_PERMISSIONS
from app.entrypoints.api.shared.permissions import ALL_PERMISSIONS, expand
from app.modules.backup.application.permissions import BackupPermission
from app.modules.collections.application.permissions import CollectionPermission
from app.modules.examples.application.permissions import ExamplePermission
from app.modules.graph.application.permissions import GraphPermission
from app.modules.media.application.permissions import MediaPermission
from app.modules.presets.application.permissions import PresetPermission
from app.shared_kernel.access import Requires
from app.shared_kernel.cqrs import UseCase
from app.shared_kernel.permission import PermissionEnum


def _use_cases() -> list[type]:
    found: list[type] = []
    for info in pkgutil.walk_packages(app.modules.__path__, "app.modules."):
        if ".application" not in info.name:
            continue
        module = importlib.import_module(info.name)
        found.extend(
            obj
            for _, obj in inspect.getmembers(module, inspect.isclass)
            if obj.__module__ == module.__name__ and issubclass(obj, UseCase)
        )
    return found


def test_every_required_permission_is_in_the_catalogue() -> None:
    """A use case cannot declare a permission the catalogue does not know."""
    declared = {
        cls: cls.__dict__["access"].permission
        for cls in _use_cases()
        if isinstance(cls.__dict__.get("access"), Requires)
    }
    assert declared
    for cls, permission in declared.items():
        assert permission in ALL_PERMISSIONS, cls.__name__


def test_backup_archive_permissions_are_admin_only_and_own_data_is_member() -> None:
    """Instance archives are admin-only; a member may move their own data."""
    assert set(BackupPermission) <= ALL_PERMISSIONS
    archive = {
        BackupPermission.CREATE,
        BackupPermission.READ,
        BackupPermission.RESTORE,
        BackupPermission.DELETE,
    }
    own_data = {BackupPermission.EXPORT_OWN_DATA, BackupPermission.IMPORT_OWN_DATA}
    assert set(BackupPermission) == archive | own_data
    assert not archive & MEMBER_PERMISSIONS
    assert own_data <= MEMBER_PERMISSIONS
    for permission in (BackupPermission.CREATE, BackupPermission.RESTORE):
        assert expand({permission}) == {permission, BackupPermission.READ}
    assert expand({BackupPermission.READ}) == {BackupPermission.READ}
    assert expand({BackupPermission.DELETE}) == {BackupPermission.DELETE}


def test_write_permissions_imply_their_read_counterpart() -> None:
    """Each content write permission grants the matching read."""
    pairs = [
        (GraphPermission.ITEM_WRITE, GraphPermission.ITEM_READ),
        (GraphPermission.TYPE_WRITE, GraphPermission.TYPE_READ),
        (MediaPermission.ITEM_WRITE, MediaPermission.ITEM_READ),
        (CollectionPermission.COLLECTION_WRITE, CollectionPermission.COLLECTION_READ),
        (PresetPermission.PRESET_WRITE, PresetPermission.PRESET_READ),
        (ExamplePermission.PACK_INSTALL, ExamplePermission.PACK_READ),
    ]
    for write, read in pairs:
        assert write.implied() == {read}
        assert read.implied() == frozenset()
    assert GraphPermission.DELETE_NODE_TYPE.implied() == frozenset()
    assert BackupPermission.EXPORT_OWN_DATA.implied() == frozenset()


def test_every_catalogued_permission_declares_its_implications() -> None:
    """Each permission is a `PermissionEnum` whose implications are catalogued."""
    for permission in ALL_PERMISSIONS:
        assert isinstance(permission, PermissionEnum)
        assert permission.implied() <= ALL_PERMISSIONS
