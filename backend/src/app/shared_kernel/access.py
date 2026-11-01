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
class Content:
    """Owned content: the actor's role must grant `permission`.

    The use case may also call `scope()`.
    """

    permission: PermissionEnum


@dataclass(frozen=True)
class Requires:
    """An actor whose role grants `permission`."""

    permission: PermissionEnum


type Access = Public | System | OwnAccount | Content | Requires
