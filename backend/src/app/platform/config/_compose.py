"""Describe the variables Docker Compose substitutes from `.env`.

Compose reads these, not Menagerist, so no settings class owns them. The names and
defaults come from the `${NAME:-default}` references in the Compose files; only the
descriptions live here. Generating the reference fails when a referenced variable has
no description, or a description names one no Compose file references any more.
"""

import re
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Mapping
    from pathlib import Path

COMPOSE_FILES = ("compose.yaml", "compose.override.yml")
COMPOSE_GROUP = "compose"
COMPOSE_SUMMARY = (
    "Read by Docker Compose from `.env` when it starts the stack, not by Menagerist. "
    + "Recreate the stack after changing one."
)

_REFERENCE = re.compile(r"\$\{([A-Z][A-Z0-9_]*)(?::?-([^}]*))?\}")

DESCRIPTIONS = {
    "MENAGERIST_IMAGE": (
        "Image the app and worker run. Set a version tag to pin a release or to roll "
        + "back (see docs/DEPLOYING.md). The development override "
        + "(compose.override.yml) defaults it to `menagerist:local`."
    ),
    "POSTGRES_PASSWORD": (
        "The database password, given once: the database container is created with "
        + "it and the app and worker connect with it. Change it before the first "
        + "start, as an existing database keeps the password it was created with."
    ),
    "POSTGRES_MEM_LIMIT": (
        "The database container's hard memory cap (Postgres has no limit of its own). "
        + "Raise it together with the memory values below if the database is large."
    ),
    "POSTGRES_SHARED_BUFFERS": (
        "Postgres `shared_buffers` (its own default is 128MB). About a quarter of the "
        + "memory cap; the most useful one to raise on a bigger machine."
    ),
    "POSTGRES_EFFECTIVE_CACHE_SIZE": (
        "Postgres `effective_cache_size` (its own default is 4GB), a planner hint for "
        + "how much data the OS can cache. Keep it near half the memory cap so the "
        + "planner is not too optimistic."
    ),
    "POSTGRES_WORK_MEM": (
        "Postgres `work_mem` (its own default is 4MB), the memory per sort or hash in "
        + "a query. Raise it only if large sorts spill to disk, as it applies to each "
        + "step of each connection."
    ),
    "POSTGRES_MAX_CONNECTIONS": (
        "Postgres `max_connections` (its own default is 100). Each worker process "
        + "keeps a pool of connections: lower it on a very small machine, and keep "
        + "it above the total of all pools."
    ),
}


def read_compose_files(root: Path) -> dict[str, str]:
    """Read each Compose file that exists under `root`."""
    return {
        name: (root / name).read_text(encoding="utf-8")
        for name in COMPOSE_FILES
        if (root / name).is_file()
    }


def compose_defaults(texts: Mapping[str, str]) -> dict[str, str | None]:
    """Map each referenced variable to its default, from the first file giving one.

    Files are read in `COMPOSE_FILES` order, so `compose.yaml` wins over the override.
    A variable with no `:-default` anywhere maps to `None`.
    """
    found: dict[str, str | None] = {}
    for name in COMPOSE_FILES:
        for variable, default in _REFERENCE.findall(texts.get(name, "")):
            found.setdefault(variable, None)
            if found[variable] is None and default:
                found[variable] = default
    return found


def check_descriptions(variables: Mapping[str, str | None]) -> None:
    """Fail when the Compose files and `DESCRIPTIONS` disagree about the variables."""
    undocumented = sorted(set(variables) - set(DESCRIPTIONS))
    stale = sorted(set(DESCRIPTIONS) - set(variables))
    problems = []
    if undocumented:
        problems.append(f"no description for {', '.join(undocumented)}")
    if stale:
        problems.append(f"described but not in a Compose file: {', '.join(stale)}")
    if problems:
        msg = "Compose variables out of step with DESCRIPTIONS: " + "; ".join(problems)
        raise ValueError(msg)
