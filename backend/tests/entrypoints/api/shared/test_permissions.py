from typing import Self

from app.entrypoints.api.shared.permissions import ALL_PERMISSIONS, expand
from app.modules.backup.application.permissions import BackupPermission
from app.modules.collections.application.permissions import CollectionPermission
from app.modules.examples.application.permissions import ExamplePermission
from app.modules.graph.application.permissions import GraphPermission
from app.modules.identity.application.permissions import IdentityPermission
from app.modules.media.application.permissions import MediaPermission
from app.modules.presets.application.permissions import PresetPermission
from app.modules.system.application.permissions import SystemPermission
from app.shared_kernel.permission import PermissionEnum


class _Chain(PermissionEnum):
    A = "test:chain:a"
    B = "test:chain:b"
    C = "test:chain:c"
    D = "test:chain:d"

    def implied(self) -> frozenset[Self]:
        cls = type(self)
        if self is cls.A:
            return frozenset({cls.B})
        if self is cls.B:
            return frozenset({cls.C})
        return frozenset()


class _Cycle(PermissionEnum):
    A = "test:cycle:a"
    B = "test:cycle:b"

    def implied(self) -> frozenset[Self]:
        cls = type(self)
        return frozenset({cls.B if self is cls.A else cls.A})


def test_expand_without_implications_returns_the_grant() -> None:
    """A member with no implications adds nothing."""
    assert expand({_Chain.D}) == frozenset({_Chain.D})
    assert expand(set()) == frozenset()


def test_expand_follows_implications_transitively() -> None:
    """A implies B and B implies C, so A grants all three."""
    a, b, c, d = _Chain.A, _Chain.B, _Chain.C, _Chain.D
    assert expand({a}) == frozenset({a, b, c})
    assert expand({b}) == frozenset({b, c})
    assert d not in expand({a})


def test_expand_terminates_on_a_cycle() -> None:
    """A cyclic implication still closes without looping."""
    assert expand({_Cycle.A}) == frozenset({_Cycle.A, _Cycle.B})


def test_the_real_catalogue_is_the_union_of_every_modules_enum() -> None:
    """The aggregate catalogue is the union of every module's enum."""
    assert (
        frozenset(BackupPermission)
        | frozenset(CollectionPermission)
        | frozenset(ExamplePermission)
        | frozenset(GraphPermission)
        | frozenset(IdentityPermission)
        | frozenset(MediaPermission)
        | frozenset(PresetPermission)
        | frozenset(SystemPermission)
    ) == ALL_PERMISSIONS


def test_managing_users_implies_listing_them() -> None:
    """Create, update, reset and unlock each grant list as well."""
    for permission in (
        IdentityPermission.CREATE_USER,
        IdentityPermission.UPDATE_USER,
        IdentityPermission.RESET_USER_PASSWORD,
        IdentityPermission.UNLOCK_USER,
    ):
        assert IdentityPermission.LIST_USERS in expand({permission})
    assert expand({IdentityPermission.LIST_USERS}) == {IdentityPermission.LIST_USERS}


def test_revoking_sessions_implies_listing_them() -> None:
    """Revoking sessions grants listing them as well."""
    assert IdentityPermission.LIST_SESSIONS in expand(
        {IdentityPermission.REVOKE_SESSION}
    )
    assert expand({IdentityPermission.LIST_SESSIONS}) == {
        IdentityPermission.LIST_SESSIONS
    }


def test_the_real_catalogue_has_no_cycles() -> None:
    """No permission transitively implies itself."""
    for permission in ALL_PERMISSIONS:
        reached: set[PermissionEnum] = set()
        frontier = set(permission.implied())
        while frontier:
            current = frontier.pop()
            assert current != permission
            if current not in reached:
                reached.add(current)
                frontier |= current.implied()
