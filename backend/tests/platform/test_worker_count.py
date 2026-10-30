"""`workers=auto`: a worker per CPU core on a host, one in a container."""

import pytest

from app.platform.config.server import MAX_WORKERS
from app.platform.worker_count import in_container, resolve_workers


def _detect(
    configured: bool | None = None,
    *,
    environ: dict[str, str] | None = None,
    files: set[str] | None = None,
    cgroup: str = "",
) -> bool:
    present = files or set()
    return in_container(
        configured,
        environ=environ or {},
        exists=lambda path: path in present,
        read_cgroup=lambda: cgroup,
    )


def test_a_plain_host_is_not_a_container() -> None:
    """No marker anywhere means a host."""
    assert _detect(cgroup="0::/user.slice/user-1000.slice/session-2.scope") is False


def test_the_setting_forces_yes_whatever_else_is_visible() -> None:
    """The image sets `server.in_container`, so detection is not needed."""
    assert _detect(True) is True


def test_the_setting_can_say_no_despite_markers() -> None:
    """A host with a stray marker file can say it is not a container."""
    assert _detect(False, files={"/.dockerenv"}, cgroup="1:cpu:/docker/x") is False


def test_docker_and_podman_marker_files() -> None:
    """The files the runtimes create inside every container."""
    assert _detect(files={"/.dockerenv"}) is True
    assert _detect(files={"/run/.containerenv"}) is True


def test_kubernetes_is_detected_from_its_environment() -> None:
    """Kubernetes injects its service host into every pod."""
    assert _detect(environ={"KUBERNETES_SERVICE_HOST": "10.0.0.1"}) is True


@pytest.mark.parametrize("word", ["docker", "kubepods", "containerd", "libpod"])
def test_the_cgroup_path_names_the_runtime(word: str) -> None:
    """Older setups only show the runtime in the process's cgroup path."""
    assert _detect(cgroup=f"12:cpu:/{word}/abc123") is True


def test_a_number_is_returned_unchanged() -> None:
    """An explicit count is the person's choice, container or not."""
    assert resolve_workers(4, container=True, cpus=16) == 4
    assert resolve_workers(1, container=False, cpus=16) == 1


def test_auto_in_a_container_is_one() -> None:
    """Granian's advice: one worker per container; scale by running more containers."""
    assert resolve_workers("auto", container=True, cpus=16) == 1


def test_auto_on_a_host_is_one_worker_per_core() -> None:
    """On bare metal, match the cores."""
    assert resolve_workers("auto", container=False, cpus=8) == 8


def test_auto_is_capped_at_the_supported_maximum() -> None:
    """A very large machine still stays inside the supported range."""
    assert resolve_workers("auto", container=False, cpus=128) == MAX_WORKERS


def test_auto_falls_back_to_one_when_the_core_count_is_unknown() -> None:
    """If Python cannot say how many cores there are, do not guess high."""
    assert resolve_workers("auto", container=False, cpus=None) == 1


def test_a_number_out_of_range_is_still_refused() -> None:
    """Resolution does not bypass the range check."""
    with pytest.raises(ValueError, match="between 1 and"):
        resolve_workers(0, container=False, cpus=4)
