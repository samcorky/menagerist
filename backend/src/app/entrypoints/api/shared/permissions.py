from itertools import chain
from typing import TYPE_CHECKING

from app.modules.backup.application.permissions import BackupPermission
from app.modules.collections.application.permissions import CollectionPermission
from app.modules.examples.application.permissions import ExamplePermission
from app.modules.graph.application.permissions import GraphPermission
from app.modules.identity.application.permissions import IdentityPermission
from app.modules.media.application.permissions import MediaPermission
from app.modules.presets.application.permissions import PresetPermission
from app.modules.scheduling.application.permissions import SchedulingPermission
from app.modules.settings.application.permissions import SettingsPermission
from app.modules.system.application.permissions import SystemPermission

if TYPE_CHECKING:
    from collections.abc import Iterable

    from app.shared_kernel.permission import PermissionEnum

Permission = (
    BackupPermission
    | CollectionPermission
    | ExamplePermission
    | GraphPermission
    | IdentityPermission
    | MediaPermission
    | PresetPermission
    | SystemPermission
    | SchedulingPermission
    | SettingsPermission
)

ALL_PERMISSIONS: frozenset[Permission] = frozenset(
    chain(
        BackupPermission,
        CollectionPermission,
        ExamplePermission,
        GraphPermission,
        IdentityPermission,
        MediaPermission,
        PresetPermission,
        SystemPermission,
        SchedulingPermission,
        SettingsPermission,
    )
)


def expand[P: PermissionEnum](granted: Iterable[P]) -> frozenset[P]:
    """Return `granted` plus everything it transitively implies."""
    result = set(granted)
    pending = list(result)
    while pending:
        for implied in pending.pop().implied():
            if implied not in result:
                result.add(implied)
                pending.append(implied)
    return frozenset(result)
