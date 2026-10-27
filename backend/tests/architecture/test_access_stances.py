import importlib
import importlib.util
import inspect
import pkgutil
from abc import abstractmethod
from enum import StrEnum
from typing import Any, ClassVar, get_args

import pytest

import app.modules
from app.entrypoints.api.shared.permissions import ALL_PERMISSIONS
from app.shared_kernel.access import (
    Access,
    Content,
    OwnAccount,
    Public,
    Requires,
    System,
)
from app.shared_kernel.cqrs import UseCase
from app.shared_kernel.permission import PermissionEnum

# Pinned by name so widening who can call something needs an edit here.
# Filled in as each module migrates.
EXPECTED_PUBLIC: frozenset[str] = frozenset(
    {
        "backup.RestoreOnFirstRun",
        "identity.AuthenticateApiToken",
        "identity.GetCurrentUser",
        "identity.GetSetupStatus",
        "identity.HasAdministrator",
        "identity.SetupFirstAdmin",
        "identity.SignIn",
        "identity.SignOut",
        "system.GetHealth",
        "system.GetHealthReady",
        "system.GetVersion",
    }
)
EXPECTED_SYSTEM: frozenset[str] = frozenset(
    {
        "collections.ClaimLegacyCollections",
        "collections.PurgeCollection",
        "collections.PurgeExpiredCollections",
        "collections.PurgeItemMemberships",
        "examples.ClaimOrphanedInstallations",
        "graph.ClaimOrphanedItems",
        "graph.PurgeEdge",
        "graph.PurgeExpiredNodes",
        "graph.PurgeNode",
        "media.ClaimOrphanedMedia",
        "media.CleanupExpiredMedia",
        "media.PurgeAttachment",
        "media.RegenerateThumbnails",
        "scheduling.TickSchedules",
        "scheduling.CheckJobExecution",
        "scheduling.HeartbeatJobRun",
        "scheduling.FinishJobRun",
        "scheduling.ClaimJobRun",
        "scheduling.MaintainWorker",
        "scheduling.PruneJobRuns",
        "scheduling.GetWorkerStatus",
        "scheduling.GetJobNextRun",
    }
)
EXPECTED_OWN_ACCOUNT: frozenset[str] = frozenset(
    {
        "identity.ChangePassword",
        "identity.CreateApiToken",
        "identity.ListGrantablePermissions",
        "identity.ListOwnApiTokens",
        "identity.ListOwnSessions",
        "identity.RevokeOtherSessions",
        "identity.RevokeOwnApiToken",
        "identity.RevokeOwnSession",
        "identity.RotateApiToken",
        "identity.SetOwnDisplayName",
    }
)
EXPECTED_CONTENT: frozenset[str] = frozenset(
    {
        "backup.DeleteUserExport",
        "backup.ExportUserData",
        "backup.ImportUserArchive",
        "backup.ImportUserData",
        "backup.ListUserExports",
        "backup.OpenUserExport",
        "collections.AddItemsToCollection",
        "collections.CountCollectionItems",
        "collections.CreateCollection",
        "collections.DeleteCollection",
        "collections.GetCollection",
        "collections.ListCollections",
        "collections.ListDeletedCollections",
        "collections.PurgeDeletedCollection",
        "collections.RemoveItemFromCollection",
        "collections.ResolveCollection",
        "collections.RestoreCollection",
        "collections.UpdateCollection",
        "examples.InstallExamplePack",
        "examples.ListExampleEntities",
        "examples.ListExamplePacks",
        "examples.UninstallExamplePack",
        "graph.CountEdgeTypeAttributeUsage",
        "graph.CountNodeTypeAttributeUsage",
        "graph.CreateEdge",
        "graph.CreateEdges",
        "graph.CountNodes",
        "graph.CreateNode",
        "graph.DeleteEdge",
        "graph.DeleteNode",
        "graph.GetEdge",
        "graph.GetNode",
        "graph.ListAttributeValues",
        "graph.ListEdges",
        "graph.ListItemFields",
        "graph.ListDeletedNodes",
        "graph.ListNodes",
        "graph.PromoteExtraSchemaField",
        "graph.PurgeDeletedNode",
        "graph.SearchNodes",
        "graph.RestoreNode",
        "graph.UpdateEdge",
        "graph.UpdateNode",
        "media.AttachMedia",
        "media.ClearMediaCover",
        "media.DeleteMedia",
        "media.DetachMedia",
        "media.GetMedia",
        "media.ListNodeMedia",
        "media.OrphanMedia",
        "media.PromoteMedia",
        "media.SetMediaCover",
        "media.StageMedia",
        "media.UpdateMedia",
        "media.UploadAndAttachMedia",
    }
)

type UseCaseType = type[UseCase[Any, Any]]

_STANCES = get_args(Access.__value__)


def _use_cases() -> list[UseCaseType]:
    found: list[UseCaseType] = []
    for info in pkgutil.walk_packages(app.modules.__path__, "app.modules."):
        if ".application" not in info.name:
            continue
        module = importlib.import_module(info.name)
        found.extend(
            obj
            for _, obj in inspect.getmembers(module, inspect.isclass)
            if obj.__module__ == module.__name__
            and issubclass(obj, UseCase)
            and not inspect.isabstract(obj)
        )
    return found


def _all_use_cases() -> list[UseCaseType]:
    """Every concrete use case under `app.modules`, wherever it is defined."""
    found: list[UseCaseType] = []
    for info in pkgutil.walk_packages(app.modules.__path__, "app.modules."):
        module = importlib.import_module(info.name)
        found.extend(
            obj
            for _, obj in inspect.getmembers(module, inspect.isclass)
            if obj.__module__ == module.__name__
            and issubclass(obj, UseCase)
            and not inspect.isabstract(obj)
        )
    return found


def _module_of(cls: type) -> str:
    return cls.__module__.split(".")[2]


def _name(cls: type) -> str:
    return f"{_module_of(cls)}.{cls.__name__}"


def _declared(cls: type) -> object:
    """Return the `access` set below `UseCase`, or None."""
    for base in cls.__mro__:
        if base is UseCase:
            break
        if "access" in vars(base):
            return vars(base)["access"]
    return None


def _without_access(classes: list[UseCaseType]) -> list[str]:
    return [_name(c) for c in classes if not isinstance(_declared(c), _STANCES)]


def _overriding_handle(classes: list[UseCaseType]) -> list[str]:
    """Classes with `handle` defined anywhere between them and `UseCase`."""
    return [
        _name(c)
        for c in classes
        if any("handle" in vars(b) for b in c.__mro__[: c.__mro__.index(UseCase)])
    ]


def _misplaced(classes: list[UseCaseType]) -> list[str]:
    """Use cases defined outside an `application` package."""
    return [_name(c) for c in classes if ".application" not in c.__module__]


def _bad_permissions(classes: list[UseCaseType]) -> list[str]:
    bad: list[str] = []
    for cls in classes:
        access = _declared(cls)
        if not isinstance(access, Requires):
            continue
        if access.permission not in ALL_PERMISSIONS:
            bad.append(_name(cls))
            continue
        permissions = importlib.import_module(
            f"app.modules.{_module_of(cls)}.application.permissions"
        )
        owned = {
            member
            for _, enum in inspect.getmembers(permissions, inspect.isclass)
            if issubclass(enum, StrEnum) and enum.__module__ == permissions.__name__
            for member in enum
        }
        if access.permission not in owned:
            bad.append(_name(cls))
    return bad


def _with_stance(classes: list[UseCaseType], stance: type) -> frozenset[str]:
    return frozenset(_name(c) for c in classes if isinstance(_declared(c), stance))


def test_every_use_case_declares_an_access_stance() -> None:
    """A concrete use case without `access` is a forgotten check."""
    assert _without_access(_use_cases()) == []


def test_no_use_case_overrides_handle() -> None:
    """`handle` is final: use cases implement `_handle`."""
    assert _overriding_handle(_use_cases()) == []


def test_use_cases_live_in_application_packages() -> None:
    """No use case hides in an adapter, where the stance checks never look."""
    assert _misplaced(_all_use_cases()) == []


def test_required_permissions_belong_to_the_use_cases_module() -> None:
    """A `Requires` permission is catalogued and from the module's own enum."""
    assert _bad_permissions(_use_cases()) == []


@pytest.mark.parametrize(
    ("stance", "expected"),
    [
        (Public, EXPECTED_PUBLIC),
        (System, EXPECTED_SYSTEM),
        (OwnAccount, EXPECTED_OWN_ACCOUNT),
        (Content, EXPECTED_CONTENT),
    ],
)
def test_stance_sets_are_pinned_by_name(stance: type, expected: frozenset[str]) -> None:
    """Adding a use case to a stance means editing the pin."""
    assert _with_stance(_use_cases(), stance) == expected


def _fake[T: type](cls: T) -> T:
    """Give a test class a module path like a real use case."""
    cls.__module__ = "app.modules.demo.application.fake"
    return cls


@_fake
class _NoAccess(UseCase[str, str]):
    async def _handle(self, request: str, actor: object) -> str:
        return request


@_fake
class _Open(_NoAccess):
    access: ClassVar[Access] = Public()


@_fake
class _Overrides(_Open):
    async def handle(self, request: str, actor: object) -> str:  # type: ignore[misc]
        return request


@_fake
class _AbstractOverrides(_Open):
    """An abstract middle layer that replaces the final `handle`."""

    async def handle(self, request: str, actor: object) -> str:  # type: ignore[misc]
        return request

    @abstractmethod
    def extra(self) -> None: ...


@_fake
class _ChildOfOverride(_AbstractOverrides):
    def extra(self) -> None:
        return None


@_fake
class _InAdapter(_Open):
    """Pretends to live in an adapter package."""


_InAdapter.__module__ = "app.modules.demo.adapters.api.router"


class _ForeignPermission(PermissionEnum):
    NOPE = "nope:nothing:read"


@_fake
class _Gated(_NoAccess):
    access: ClassVar[Access] = Requires(_ForeignPermission.NOPE)


def test_the_checks_catch_bad_use_cases() -> None:
    """The checks above bite: each flags a deliberately wrong class."""
    assert _without_access([_NoAccess, _Open]) == [_name(_NoAccess)]
    assert _overriding_handle([_Open, _Overrides]) == [_name(_Overrides)]
    assert _overriding_handle([_ChildOfOverride]) == [_name(_ChildOfOverride)]
    assert _misplaced([_Open, _InAdapter]) == [_name(_InAdapter)]
    assert _bad_permissions([_Open, _Gated]) == [_name(_Gated)]
    assert _with_stance([_Open, _Gated], Public) == {_name(_Open)}


def test_no_legacy_bases() -> None:
    """The scoped and authorised bases are gone: access is a declared stance."""
    import app.shared_kernel.cqrs as cqrs

    legacy = [n for n in dir(cqrs) if n.startswith(("Scoped", "Authorised", "_Policy"))]
    assert legacy == []
    assert importlib.util.find_spec("app.shared_kernel.access_policy") is None
    assert importlib.util.find_spec("app.shared_kernel.guarded") is None
