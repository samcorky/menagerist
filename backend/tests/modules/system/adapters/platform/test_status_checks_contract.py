"""Everything the backend can report on the status page is in the shared contract.

The frontend formats each unit, picks an icon and words each state per the contract.
A check, unit or state added here without a contract entry fails this test; the entry
then fails the frontend test until the page can show it.
"""

import ast
import json
import re
from pathlib import Path
from typing import Any, get_args

from app.modules.system.adapters.platform.checks.cors_configuration_check import (
    CorsConfigurationCheck,
)
from app.modules.system.adapters.platform.checks.proxy_configuration_check import (
    ProxyConfigurationCheck,
)
from app.platform.shared_data import shared_data_path
from app.platform.storage_probe import DirectoryState

SRC = Path(__file__).parents[5] / "src" / "app"
_KEY = re.compile(r"^(database|configuration|storage|scheduler|system):")
_WORKER_CHECK = SRC / "entrypoints/api/shared/bridges/scheduler_worker_check.py"


def _contract() -> dict[str, Any]:
    path = shared_data_path("contracts/status-checks.json")
    return json.loads(path.read_text(encoding="utf-8"))  # type: ignore[no-any-return]


def _pattern(node: ast.expr) -> str | None:
    """A check key as written in source; `*` replaces any computed part."""
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value
    if isinstance(node, ast.JoinedStr):
        return "".join(
            str(part.value) if isinstance(part, ast.Constant) else "*"
            for part in node.values
        )
    return None


def _unit_of(call: ast.Call) -> set[str]:
    name = call.func.id if isinstance(call.func, ast.Name) else None
    unit: ast.expr | None = None
    if name == "observation" and len(call.args) > 1:
        unit = call.args[1]
    elif name == "failed_observation" and call.args:
        unit = call.args[0]
    for keyword in call.keywords:
        if keyword.arg == "observed_unit":
            unit = keyword.value
    if isinstance(unit, ast.Constant) and isinstance(unit.value, str):
        return {unit.value}
    return set()


def _scan() -> tuple[set[str], set[str]]:
    """Return the check keys and units written in the backend source."""
    keys: set[str] = set()
    units: set[str] = set()
    for file in SRC.rglob("*.py"):
        for node in ast.walk(ast.parse(file.read_text(encoding="utf-8"))):
            if isinstance(node, ast.Dict):
                keys.update(
                    p
                    for k in node.keys
                    if k is not None and (p := _pattern(k)) and _KEY.match(p)
                )
            elif (
                isinstance(node, ast.Subscript)
                and (p := _pattern(node.slice))
                and _KEY.match(p)
            ):
                keys.add(p)
            elif isinstance(node, ast.Call):
                units.update(_unit_of(node))
    return keys, units


def _worker_states() -> set[str]:
    tree = ast.parse(_WORKER_CHECK.read_text(encoding="utf-8"))
    found: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign) and any(
            isinstance(t, ast.Name) and t.id == "observed_value" for t in node.targets
        ):
            found.update(
                n.value
                for n in ast.walk(node.value)
                if isinstance(n, ast.Constant) and isinstance(n.value, str)
            )
    return found


def test_the_source_scan_finds_the_checks() -> None:
    """Guards the scan itself: an empty result would make the tests below vacuous."""
    keys, units = _scan()

    assert len(keys) >= 8
    assert {"ms", "state", "GiB", "percent"} <= units


def test_every_key_in_source_has_a_contract_entry() -> None:
    """A new check key must be added to `status-checks.json`."""
    listed = {c["key"] for c in _contract()["checks"]}
    keys, _ = _scan()
    # Keys built from a signal name are covered by the live-check test below.
    keys = {k for k in keys if not k.startswith("configuration:proxy*")}

    assert sorted(keys - listed) == []


def test_every_unit_in_source_has_a_contract_entry() -> None:
    """A new unit must appear in the contract so the page can format it."""
    listed = {c["unit"] for c in _contract()["checks"]}
    _, units = _scan()

    assert sorted(units - listed) == []


def test_every_state_in_source_has_a_contract_entry() -> None:
    """A new storage or worker state needs wording on the page."""
    listed = set(_contract()["states"])
    sent = set(get_args(DirectoryState)) | _worker_states()

    assert sorted(sent - listed) == []


async def test_live_proxy_checks_report_listed_keys_with_the_listed_unit() -> None:
    """The proxy keys are built from signal names, so run the check for real."""
    listed = {c["key"]: c["unit"] for c in _contract()["checks"]}

    result = await ProxyConfigurationCheck().run()

    assert result
    for key, observed in result.items():
        assert listed.get(key) == observed.observed_unit, key


async def test_live_cors_check_reports_its_listed_key_and_unit() -> None:
    """The CORS check needs no I/O either."""
    listed = {c["key"]: c["unit"] for c in _contract()["checks"]}

    result = await CorsConfigurationCheck(origins=[]).run()

    assert result
    for key, observed in result.items():
        assert listed.get(key) == observed.observed_unit, key
