import importlib
import inspect
import pkgutil

import app.modules
from app.entrypoints.api.shared.authorisation import MEMBER_PERMISSIONS
from app.entrypoints.api.shared.permissions import ALL_PERMISSIONS, expand
from app.modules.backup.application.permissions import BackupPermission
from app.shared_kernel.cqrs import UseCase


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


def test_every_declared_required_permission_is_in_the_catalogue() -> None:
    """A use case cannot declare a permission the catalogue does not know."""
    declared = {
        cls: cls.__dict__["required_permission"]
        for cls in _use_cases()
        if "required_permission" in cls.__dict__
        and not isinstance(cls.__dict__["required_permission"], property)
    }
    assert declared
    for cls, permission in declared.items():
        assert permission in ALL_PERMISSIONS, cls.__name__


def test_backup_permissions_are_catalogued_and_admin_only() -> None:
    """Instance archives are visible only to administrators and system jobs."""
    assert set(BackupPermission) <= ALL_PERMISSIONS
    assert not set(BackupPermission) & MEMBER_PERMISSIONS
    for permission in (BackupPermission.CREATE, BackupPermission.RESTORE):
        assert expand({permission}) == {permission, BackupPermission.READ}
    assert expand({BackupPermission.READ}) == {BackupPermission.READ}
    assert expand({BackupPermission.DELETE}) == {BackupPermission.DELETE}
