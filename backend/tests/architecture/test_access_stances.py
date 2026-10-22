import importlib
import inspect
import pkgutil
from enum import StrEnum
from typing import Any, ClassVar, get_args

import pytest

import app.modules
from app.entrypoints.api.shared.permissions import ALL_PERMISSIONS
from app.shared_kernel.access import Access, Content, Public, Requires, Shared, System
from app.shared_kernel.guarded import GuardedUseCase

# Pinned by name so widening who can call something needs an edit here.
# Filled in as each module migrates.
EXPECTED_PUBLIC: frozenset[str] = frozenset(
    {
        "backup.RestoreOnFirstRun",
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
EXPECTED_SYSTEM: frozenset[str] = frozenset()
EXPECTED_SHARED: frozenset[str] = frozenset(
    {
        "presets.CreatePreset",
        "presets.DeletePreset",
        "presets.ExportPresets",
        "presets.GetPreset",
        "presets.ImportPresets",
        "presets.ListPresets",
        "presets.UpdatePreset",
    }
)
EXPECTED_CONTENT: frozenset[str] = frozenset(
    {
        "backup.ExportUserData",
        "backup.ImportUserArchive",
        "backup.ImportUserData",
        "backup.OpenUserExport",
    }
)

type UseCaseType = type[GuardedUseCase[Any, Any]]

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
            and issubclass(obj, GuardedUseCase)
            and not inspect.isabstract(obj)
        )
    return found


def _module_of(cls: type) -> str:
    return cls.__module__.split(".")[2]


def _name(cls: type) -> str:
    return f"{_module_of(cls)}.{cls.__name__}"


def _declared(cls: type) -> object:
    """Return the `access` set below `GuardedUseCase`, or None."""
    for base in cls.__mro__:
        if base is GuardedUseCase:
            break
        if "access" in vars(base):
            return vars(base)["access"]
    return None


def _without_access(classes: list[UseCaseType]) -> list[str]:
    return [_name(c) for c in classes if not isinstance(_declared(c), _STANCES)]


def _overriding_handle(classes: list[UseCaseType]) -> list[str]:
    return [_name(c) for c in classes if "handle" in vars(c)]


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


def test_required_permissions_belong_to_the_use_cases_module() -> None:
    """A `Requires` permission is catalogued and from the module's own enum."""
    assert _bad_permissions(_use_cases()) == []


@pytest.mark.parametrize(
    ("stance", "expected"),
    [
        (Public, EXPECTED_PUBLIC),
        (System, EXPECTED_SYSTEM),
        (Shared, EXPECTED_SHARED),
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
class _NoAccess(GuardedUseCase[str, str]):
    async def _handle(self, request: str, actor: object) -> str:
        return request


@_fake
class _Open(_NoAccess):
    access: ClassVar[Access] = Public()


@_fake
class _Overrides(_Open):
    async def handle(self, request: str, actor: object) -> str:  # type: ignore[misc]
        return request


class _ForeignPermission(StrEnum):
    NOPE = "nope:nothing:read"


@_fake
class _Gated(_NoAccess):
    access: ClassVar[Access] = Requires(_ForeignPermission.NOPE)


def test_the_checks_catch_bad_use_cases() -> None:
    """The checks above bite: each flags a deliberately wrong class."""
    assert _without_access([_NoAccess, _Open]) == [_name(_NoAccess)]
    assert _overriding_handle([_Open, _Overrides]) == [_name(_Overrides)]
    assert _bad_permissions([_Open, _Gated]) == [_name(_Gated)]
    assert _with_stance([_Open, _Gated], Public) == {_name(_Open)}
