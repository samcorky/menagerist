"""Every setting the code reads live must be a tunable the settings module serves."""

import ast
from pathlib import Path

import app
from app.modules.backup.adapters.scheduling.jobs import LIVE_SCHEDULES
from app.modules.backup.application.setting_keys import KEEP_LAST, USER_EXPORT_TTL_HOURS
from app.modules.scheduling.application.setting_keys import RUN_HISTORY_PER_JOB
from app.platform.config import SETTING_GROUPS
from app.platform.config._discovery import discover

CODE_KEYS = {
    RUN_HISTORY_PER_JOB.key,
    KEEP_LAST.key,
    USER_EXPORT_TTL_HOURS.key,
    *LIVE_SCHEDULES,
}


def test_every_key_the_code_reads_is_a_tunable_setting() -> None:
    """A renamed field or a dropped marker would otherwise fail only at runtime."""
    tunable = {spec.key for spec in discover(SETTING_GROUPS) if spec.tunable}
    assert tunable >= CODE_KEYS


def test_live_schedules_are_cron_settings() -> None:
    """A live schedule key is a cron string, which turns the job off when empty."""
    specs = {spec.key: spec for spec in discover(SETTING_GROUPS)}
    for key in LIVE_SCHEDULES:
        assert specs[key].schema["x-menagerist"] == {"kind": "cron"}


def _declared_keys() -> dict[str, str]:
    """Each `NAME = SettingKey[T]("key")` in a module's `setting_keys.py`: key to T.

    `T` is erased at runtime, so it is read from the source.
    """
    root = Path(app.__file__).parent / "modules"
    declared: dict[str, str] = {}
    for path in sorted(root.glob("*/application/setting_keys.py")):
        for node in ast.walk(ast.parse(path.read_text())):
            if not (isinstance(node, ast.Assign) and isinstance(node.value, ast.Call)):
                continue
            target = node.value.func
            if not (
                isinstance(target, ast.Subscript)
                and isinstance(target.value, ast.Name)
                and target.value.id == "SettingKey"
                and isinstance(target.slice, ast.Name)
            ):
                continue
            argument = node.value.args[0]
            assert isinstance(argument, ast.Constant), f"{path}: key must be a literal"
            declared[str(argument.value)] = target.slice.id
    return declared


_JSON_TYPES = {"int": "integer", "str": "string", "bool": "boolean", "float": "number"}


def test_the_declared_type_of_every_key_matches_its_setting() -> None:
    """`SettingKey[int]` for a string setting would type-check and fail at runtime."""
    declared = _declared_keys()
    specs = {spec.key: spec for spec in discover(SETTING_GROUPS)}
    assert declared.keys() >= CODE_KEYS - set(LIVE_SCHEDULES), "found no declarations"
    for key, python_type in declared.items():
        assert _JSON_TYPES[python_type] == specs[key].schema["type"], key
