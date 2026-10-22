from dataclasses import dataclass

from app.shared_kernel.permission import PermissionEnum


@dataclass(frozen=True)
class Public:
    """Anyone may call this, including the anonymous actor."""


@dataclass(frozen=True)
class System:
    """Only the system actor may call this."""


@dataclass(frozen=True)
class OwnAccount:
    """A signed-in session actor acting on themselves."""


@dataclass(frozen=True)
class Shared:
    """Shared catalogue: any signed-in actor, system included."""


@dataclass(frozen=True)
class Content:
    """Owned content: as `Shared`, and the use case may call `scope()`.

    `permission` is transitional: when set, the actor's role must grant it.
    """

    permission: PermissionEnum | None = None


@dataclass(frozen=True)
class Requires:
    """An actor whose role grants `permission`."""

    permission: PermissionEnum


type Access = Public | System | OwnAccount | Shared | Content | Requires
