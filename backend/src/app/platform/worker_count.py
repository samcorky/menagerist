"""Pick the web worker count: `auto` is a worker per core, or one in a container."""

import os
from pathlib import Path
from typing import TYPE_CHECKING, Final, Literal

from app.platform.config.server import MAX_WORKERS
from app.platform.connection_budget import validate_workers

if TYPE_CHECKING:
    from collections.abc import Callable, Mapping

Workers = int | Literal["auto"]

_MARKER_FILES: Final = ("/.dockerenv", "/run/.containerenv")
_CGROUP_WORDS: Final = ("docker", "kubepods", "containerd", "libpod")


def _read_cgroup() -> str:
    try:
        return Path("/proc/self/cgroup").read_text(encoding="utf-8")
    except OSError:
        return ""


def in_container(
    configured: bool | None,
    *,
    environ: Mapping[str, str] = os.environ,
    exists: Callable[[str], bool] = os.path.exists,
    read_cgroup: Callable[[], str] = _read_cgroup,
) -> bool:
    """Whether this process runs inside a container.

    `configured` (`ServerSettings.in_container`) decides when set, either way, as
    the image sets it; otherwise Docker's and Podman's marker files, Kubernetes'
    environment and the runtime named in the cgroup path are looked for.
    """
    if configured is not None:
        return configured
    if "KUBERNETES_SERVICE_HOST" in environ:
        return True
    if any(exists(path) for path in _MARKER_FILES):
        return True
    cgroup = read_cgroup()
    return any(word in cgroup for word in _CGROUP_WORDS)


def resolve_workers(value: Workers, *, container: bool, cpus: int | None) -> int:
    """Turn the setting into a worker count.

    A number is checked and returned. `auto` is one in a container, where
    Granian advises one worker per container and scaling by running more of them,
    and otherwise one per CPU core, between 1 and the supported maximum.
    """
    if value != "auto":
        return validate_workers(value)
    if container or cpus is None:
        return 1
    return max(1, min(cpus, MAX_WORKERS))


def available_cpus() -> int | None:
    """The cores this process may use, or `None` if Python cannot tell."""
    return os.process_cpu_count()
